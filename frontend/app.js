/**
 * Voice Support Agent — Frontend
 *
 * Flow:
 *  1. User clicks mic  → MediaRecorder starts
 *  2. User clicks stop → audio blob sent to POST /api/voice-chat
 *  3. Server streams SSE events:
 *       transcription → show what user said
 *       sentiment     → show badge, update agent tone note
 *       token         → stream agent response text live
 *       audio         → decode base64 WAV and auto-play
 *       done / error  → reset UI
 */

"use strict";

// ── DOM refs ──────────────────────────────────────────────────────────────────
const micBtn          = document.getElementById("micBtn");
const micWrap         = document.getElementById("micWrap");
const statusLine      = document.getElementById("statusLine");
const conversation    = document.getElementById("conversation");
const userMsg         = document.getElementById("userMsg");
const transcriptionEl = document.getElementById("transcriptionText");
const sentimentBadge  = document.getElementById("sentimentBadge");
const agentMsg        = document.getElementById("agentMsg");
const responseEl      = document.getElementById("responseText");
const audioPlayingEl  = document.getElementById("audioPlaying");

// ── State ─────────────────────────────────────────────────────────────────────
let mediaRecorder  = null;
let audioChunks    = [];
let isRecording    = false;
let isProcessing   = false;

// ── UI helpers ─────────────────────────────────────────────────────────────────
function setStatus(text, type = "") {
  statusLine.textContent = text;
  statusLine.className = "status-line" + (type ? ` ${type}` : "");
}

function resetConversation() {
  userMsg.style.display  = "none";
  agentMsg.style.display = "none";
  userMsg.classList.remove("visible");
  agentMsg.classList.remove("visible");
  sentimentBadge.className = "sentiment-badge";
  sentimentBadge.style.display = "none";
  transcriptionEl.textContent  = "";
  responseEl.textContent       = "";
  responseEl.classList.remove("streaming-cursor");
  audioPlayingEl.classList.remove("visible");
}

function scrollToBottom() {
  conversation.scrollTop = conversation.scrollHeight;
}

function showUserMessage(text) {
  transcriptionEl.textContent = text;
  userMsg.style.display = "block";
  requestAnimationFrame(() => userMsg.classList.add("visible"));
  scrollToBottom();
}

function showSentimentBadge(sentiment) {
  const labelEl = sentimentBadge.querySelector(".sentiment-label");
  sentimentBadge.style.display = "flex";

  if (sentiment === "angry") {
    sentimentBadge.className = "sentiment-badge angry visible";
    labelEl.textContent = "Frustrated detected — responding with empathy";
  } else {
    sentimentBadge.className = "sentiment-badge neutral visible";
    labelEl.textContent = "Tone: neutral";
  }
  scrollToBottom();
}

function appendToken(text) {
  if (agentMsg.style.display === "none") {
    agentMsg.style.display = "block";
    requestAnimationFrame(() => agentMsg.classList.add("visible"));
    responseEl.classList.add("streaming-cursor");
  }
  responseEl.textContent += text;
  scrollToBottom();
}

function finaliseResponse() {
  responseEl.classList.remove("streaming-cursor");
}

function playAudioBase64(base64wav) {
  return new Promise((resolve, reject) => {
    try {
      const binary = atob(base64wav);
      const bytes  = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

      const blob = new Blob([bytes.buffer], { type: "audio/wav" });
      const url  = URL.createObjectURL(blob);
      const audio = new Audio(url);

      audioPlayingEl.classList.add("visible");
      scrollToBottom();

      audio.onended = () => {
        URL.revokeObjectURL(url);
        audioPlayingEl.classList.remove("visible");
        resolve();
      };
      audio.onerror = (e) => {
        URL.revokeObjectURL(url);
        audioPlayingEl.classList.remove("visible");
        reject(e);
      };
      audio.play().catch(reject);
    } catch (e) {
      reject(e);
    }
  });
}

// ── SSE parser ─────────────────────────────────────────────────────────────────
/**
 * Parses the SSE stream from a fetch Response.
 * Calls handlers[eventName](parsedData) for each received event.
 */
async function consumeSSE(response, handlers) {
  const reader  = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE events are separated by double newlines
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop(); // keep the trailing incomplete block

    for (const block of blocks) {
      if (!block.trim()) continue;

      let eventName = "message";
      let eventData = "";

      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) {
          eventName = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          eventData = line.slice(6).trim();
        }
      }

      if (eventData) {
        console.log("[consumeSSE] Event: name=%s data=%s", eventName, eventData.slice(0, 120));
        if (handlers[eventName]) {
          try {
            handlers[eventName](JSON.parse(eventData));
          } catch (err) {
            console.error("[consumeSSE] Parse error for event=%s:", eventName, err, eventData);
          }
        } else {
          console.warn("[consumeSSE] No handler for event:", eventName);
        }
      }
    }
  }
}

// ── Core pipeline ─────────────────────────────────────────────────────────────
async function sendAudio(audioBlob) {
  console.log("[sendAudio] Blob size=%d bytes, type=%s", audioBlob.size, audioBlob.type);

  if (audioBlob.size < 1000) {
    console.warn("[sendAudio] Blob is very small (%d bytes) — likely no audio was captured", audioBlob.size);
    setStatus("Recording too short — try again", "error");
    isProcessing = false;
    micBtn.disabled = false;
    return;
  }

  isProcessing = true;
  micBtn.disabled = true;
  resetConversation();

  const formData = new FormData();
  const ext = audioBlob.type.includes("ogg") ? "ogg"
             : audioBlob.type.includes("mp4") ? "m4a"
             : "webm";
  const filename = `recording.${ext}`;
  formData.append("audio", audioBlob, filename);
  console.log("[sendAudio] Sending as filename=%s", filename);

  setStatus("Transcribing…", "active");

  try {
    console.log("[fetch] POST /api/voice-chat ...");
    const response = await fetch("/api/voice-chat", {
      method: "POST",
      body: formData,
    });

    console.log("[fetch] Response status=%d, ok=%s, content-type=%s",
      response.status, response.ok, response.headers.get("content-type"));

    if (!response.ok) {
      const body = await response.text();
      console.error("[fetch] Error body:", body);
      throw new Error(`Server error: ${response.status} — ${body}`);
    }

    console.log("[SSE] Starting stream consumption...");
    await consumeSSE(response, {

      transcription({ text }) {
        console.log("[SSE] transcription:", text);
        showUserMessage(text);
        setStatus("Thinking…", "active");
      },

      sentiment({ value }) {
        console.log("[SSE] sentiment:", value);
        showSentimentBadge(value);
      },

      token({ text }) {
        console.debug("[SSE] token:", JSON.stringify(text));
        appendToken(text);
        setStatus("Responding…", "active");
      },

      audio({ data }) {
        console.log("[SSE] audio received, base64 length=%d", data.length);
        finaliseResponse();
        setStatus("Playing…", "active");
        playAudioBase64(data)
          .then(() => console.log("[audio] Playback finished"))
          .catch((e) => console.error("[audio] Playback error:", e))
          .finally(() => setStatus("Click the mic to start"));
      },

      error({ message }) {
        console.error("[SSE] error event:", message);
        setStatus(`Error: ${message}`, "error");
        finaliseResponse();
      },

      done() {
        console.log("[SSE] done event received");
        if (!audioPlayingEl.classList.contains("visible")) {
          setStatus("Click the mic to start");
        }
        isProcessing = false;
        micBtn.disabled = false;
      },

    });

    console.log("[SSE] Stream fully consumed");

  } catch (err) {
    console.error("[sendAudio] Caught error:", err);
    setStatus(`Connection error: ${err.message}`, "error");
    finaliseResponse();
    isProcessing = false;
    micBtn.disabled = false;
  }
}

// ── Recording ─────────────────────────────────────────────────────────────────
async function startRecording() {
  console.log("[startRecording] Requesting mic access...");
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    console.log("[startRecording] Mic granted. Tracks:", stream.getTracks().map(t => t.label));

    const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg"]
      .find((t) => MediaRecorder.isTypeSupported(t)) || "";
    console.log("[startRecording] Using mimeType:", mimeType || "(browser default)");

    mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
    audioChunks   = [];

    mediaRecorder.ondataavailable = (e) => {
      console.log("[MediaRecorder] dataavailable: size=%d bytes, state=%s", e.data.size, mediaRecorder.state);
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstart = () => {
      console.log("[MediaRecorder] started, mimeType=%s", mediaRecorder.mimeType);
    };

    mediaRecorder.onstop = () => {
      console.log("[MediaRecorder] stopped. Total chunks=%d", audioChunks.length);
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
      console.log("[MediaRecorder] Final blob: size=%d bytes, type=%s", blob.size, blob.type);
      sendAudio(blob);
    };

    mediaRecorder.onerror = (e) => {
      console.error("[MediaRecorder] error:", e.error);
    };

    mediaRecorder.start(250);
    console.log("[startRecording] MediaRecorder.start(250) called");

    isRecording = true;
    micBtn.classList.add("recording");
    micWrap.classList.add("recording");
    setStatus("Recording… click to stop", "active");

  } catch (err) {
    console.error("[startRecording] Error:", err.name, err.message);
    if (err.name === "NotAllowedError") {
      setStatus("Microphone permission denied", "error");
    } else {
      setStatus(`Mic error: ${err.message}`, "error");
    }
  }
}

function stopRecording() {
  console.log("[stopRecording] mediaRecorder state=%s", mediaRecorder?.state);
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
    console.log("[stopRecording] stop() called");
  } else {
    console.warn("[stopRecording] mediaRecorder not active, state=%s", mediaRecorder?.state);
  }
  isRecording = false;
  micBtn.classList.remove("recording");
  micWrap.classList.remove("recording");
  setStatus("Processing…", "active");
}

// ── Mic button click ──────────────────────────────────────────────────────────
micBtn.addEventListener("click", () => {
  console.log("[micBtn] click — isRecording=%s, isProcessing=%s", isRecording, isProcessing);
  if (isProcessing) {
    console.log("[micBtn] Blocked — pipeline is processing");
    return;
  }

  if (isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
});

// ── Browser compatibility guard ───────────────────────────────────────────────
if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
  setStatus("Your browser does not support audio recording", "error");
  micBtn.disabled = true;
}
