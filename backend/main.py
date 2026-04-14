"""
Voice Support Agent — FastAPI backend

Pipeline per request:
  1. STT   : Mistral voxtral-mini-2507  (REST)
  2. Sentiment : rule-based (sentiment.py)
  3. RAG   : keyword retrieval (rag.py)
  4. LLM   : mistral-small-latest, streaming (EventStream iteration)
  5. TTS   : Mistral voxtral-mini-tts-2603 (SDK)

All steps are streamed back to the browser as SSE events.

Run:
  cd backend
  python3 -m uvicorn main:app --reload --port 8000
"""

import base64
import json
import logging
import os
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import requests
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from mistralai import Mistral
from starlette.concurrency import iterate_in_threadpool

from rag import retrieve
from sentiment import detect_sentiment

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("voice-agent")

# ── Configuration ──────────────────────────────────────────────────────────────
API_KEY = os.getenv("MISTRAL_API_KEY")
if not API_KEY:
    raise RuntimeError("MISTRAL_API_KEY environment variable is not set")

# Path to the frontend directory (one level up from backend/)
FRONTEND_DIR = str(Path(__file__).parent.parent / "frontend")

client = Mistral(api_key=API_KEY)

# ── Voice mapping ──────────────────────────────────────────────────────────────
# en_paul_sad: soft, measured, empathetic tone — good for both moods in a
# support context. Once you know other valid voice IDs from the Mistral docs,
# set NEUTRAL_VOICE to a more upbeat one.
VOICE_MAP = {
    "angry":   "en_paul_sad",   # calm & empathetic when user is upset
    "neutral": "en_paul_sad",   # replace with a livelier voice ID if available
}

# ── System prompts ─────────────────────────────────────────────────────────────
SYSTEM_PROMPTS = {
    "angry": (
        "You are a warm, empathetic customer support agent. "
        "The customer is clearly upset or frustrated. "
        "Open by sincerely acknowledging their frustration and apologising for the inconvenience. "
        "Remain calm, patient, and reassuring throughout your response. "
        "Keep your answer to 3–4 sentences maximum. "
        "Use ONLY the knowledge-base context provided to answer. "
        "If the answer is not in the context, apologise and offer to escalate to a senior agent."
    ),
    "neutral": (
        "You are a professional, helpful customer support agent. "
        "Answer clearly and concisely using ONLY the provided knowledge-base context. "
        "Keep your response to 3–4 sentences. "
        "If the answer is not in the context, say so politely and offer further assistance."
    ),
}

# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(title="Voice Support Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ────────────────────────────────────────────────────────────────────
def sse_event(name: str, data: dict) -> str:
    """Format a single SSE event block."""
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def _mime_for(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "webm": "audio/webm",
        "ogg":  "audio/ogg",
        "wav":  "audio/wav",
        "mp3":  "audio/mpeg",
        "m4a":  "audio/mp4",
        "flac": "audio/flac",
    }.get(ext, "audio/webm")


def transcribe(audio_bytes: bytes, filename: str) -> str:
    """Call Mistral STT REST endpoint; return transcription text."""
    mime = _mime_for(filename)
    log.debug("[STT] Sending %d bytes, filename=%s, mime=%s", len(audio_bytes), filename, mime)
    t0 = time.time()
    resp = requests.post(
        "https://api.mistral.ai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        files={"file": (filename, audio_bytes, mime)},
        data={"model": "voxtral-mini-2507"},
        timeout=30,
    )
    log.debug("[STT] Response status=%d in %.2fs", resp.status_code, time.time() - t0)
    if resp.status_code != 200:
        log.error("[STT] Failed: %s", resp.text)
        raise RuntimeError(f"STT failed ({resp.status_code}): {resp.text}")
    text = resp.json().get("text", "").strip()
    log.info("[STT] Transcription: %r", text)
    return text


def synthesize(text: str, voice_id: str) -> str:
    """Call Mistral TTS REST API; return base64-encoded WAV string."""
    log.debug("[TTS] Synthesizing %d chars with voice_id=%s", len(text), voice_id)
    t0 = time.time()
    resp = requests.post(
        "https://api.mistral.ai/v1/audio/speech",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "voxtral-mini-tts-2603",
            "input": text,
            "voice_id": voice_id,
            "response_format": "wav",
        },
        timeout=60,
    )
    log.debug("[TTS] Response status=%d in %.2fs", resp.status_code, time.time() - t0)
    if resp.status_code != 200:
        log.error("[TTS] Failed: %s", resp.text)
        raise RuntimeError(f"TTS failed ({resp.status_code}): {resp.text}")
    audio_b64 = resp.json()["audio_data"]
    log.info("[TTS] Done in %.2fs, audio_data length=%d", time.time() - t0, len(audio_b64))
    return audio_b64


# ── SSE generator (synchronous — run via iterate_in_threadpool) ────────────────
def _sse_generator(audio_bytes: bytes, filename: str):
    """
    Sync generator that yields SSE-formatted strings.
    Wrapped in iterate_in_threadpool so all blocking Mistral
    calls run in a worker thread, not the event loop.
    """
    log.info("=== New request: filename=%s, size=%d bytes ===", filename, len(audio_bytes))
    try:
        # ── Step 1: Speech-to-Text ─────────────────────────────────────────
        log.info("[STEP 1] Starting STT...")
        transcription = transcribe(audio_bytes, filename)
        if not transcription:
            log.warning("[STEP 1] Empty transcription returned")
            yield sse_event("error", {"message": "Could not understand audio. Please try again."})
            return
        log.info("[STEP 1] STT complete: %r", transcription)
        yield sse_event("transcription", {"text": transcription})
        log.debug("[SSE] Emitted: transcription")

        # ── Step 2: Sentiment ──────────────────────────────────────────────
        log.info("[STEP 2] Detecting sentiment...")
        sentiment = detect_sentiment(transcription)
        log.info("[STEP 2] Sentiment: %s", sentiment)
        yield sse_event("sentiment", {"value": sentiment})
        log.debug("[SSE] Emitted: sentiment")

        # ── Step 3: RAG retrieval ──────────────────────────────────────────
        log.info("[STEP 3] RAG retrieval...")
        chunks = retrieve(transcription, top_k=2)
        log.info("[STEP 3] Retrieved %d chunks: %s", len(chunks), [c["topic"] for c in chunks])
        context = "\n\n".join(chunk["text"] for chunk in chunks)

        # ── Step 4: LLM — collect full response silently ───────────────────
        log.info("[STEP 4] Collecting LLM response (sentiment=%s)...", sentiment)
        system_prompt = SYSTEM_PROMPTS.get(sentiment, SYSTEM_PROMPTS["neutral"])
        user_message = (
            f"Knowledge base:\n{context}\n\n"
            f"Customer: {transcription}"
        )

        full_response = ""
        token_count = 0
        t0 = time.time()
        stream = client.chat.stream(
            model="mistral-small-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.4,
            max_tokens=300,
        )
        for event in stream:
            delta = event.data.choices[0].delta.content
            if delta:
                full_response += delta
                token_count += 1
        log.info("[STEP 4] LLM done: %d tokens in %.2fs. Response: %r",
                 token_count, time.time() - t0, full_response[:80])

        if not full_response:
            log.warning("[STEP 4] Empty LLM response — aborting")
            return

        # ── Step 5: TTS in background + stream text simultaneously ─────────
        # Fire TTS in a background thread the moment LLM finishes.
        # While TTS generates, stream the text tokens to the browser.
        # By the time the last word appears, audio is ready (or nearly so).
        voice_id = VOICE_MAP.get(sentiment, "en_paul_sad")
        log.info("[STEP 5] Firing TTS in background (voice_id=%s) while streaming text...", voice_id)

        audio_result: list = [None]
        tts_error:    list = [None]
        tts_done = threading.Event()

        def _tts_worker():
            try:
                audio_result[0] = synthesize(full_response, voice_id)
                log.info("[TTS] Background synthesis complete")
            except Exception as exc:
                tts_error[0] = exc
                log.error("[TTS] Background synthesis failed: %s", exc)
            finally:
                tts_done.set()

        threading.Thread(target=_tts_worker, daemon=True).start()

        # Stream text word-by-word while TTS runs in background
        words = full_response.split()
        for i, word in enumerate(words):
            token = word if i == 0 else f" {word}"
            yield sse_event("token", {"text": token})
            time.sleep(0.045)          # ~22 words/sec — natural reading pace
        log.debug("[SSE] Emitted: %d token events", len(words))

        # Wait for TTS to finish (it had a head-start during text streaming)
        log.info("[STEP 5] Text stream done — waiting for TTS...")
        tts_done.wait(timeout=60)
        if tts_error[0]:
            raise tts_error[0]
        yield sse_event("audio", {"data": audio_result[0]})
        log.debug("[SSE] Emitted: audio")

    except Exception as exc:  # noqa: BLE001
        log.exception("[ERROR] Pipeline failed: %s", exc)
        yield sse_event("error", {"message": str(exc)})
    finally:
        log.info("=== Request done ===")
        yield sse_event("done", {})
        log.debug("[SSE] Emitted: done")


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.post("/api/voice-chat")
async def voice_chat(audio: UploadFile = File(...)):
    """
    Accepts an audio file (multipart/form-data).
    Returns a text/event-stream with events:
      transcription | sentiment | token (×N) | audio | done | error
    """
    audio_bytes = await audio.read()
    filename    = audio.filename or "recording.webm"
    log.info("[ENDPOINT] POST /api/voice-chat  filename=%s  size=%d bytes  content_type=%s",
             filename, len(audio_bytes), audio.content_type)

    return StreamingResponse(
        iterate_in_threadpool(_sse_generator(audio_bytes, filename)),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


@app.get("/health")
def health():
    return {"status": "ok"}


# ── Frontend static serving (must be declared after all API routes) ─────────────
@app.get("/")
def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="frontend")
