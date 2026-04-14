# VoxSupport AI

A voice-powered customer support agent that listens to your question, detects your tone, retrieves relevant knowledge, generates a response, and speaks it back — all in real time.

## How it works

Each request runs a 5-step pipeline, fully streamed to the browser via Server-Sent Events (SSE):

```
Mic input
   │
   ▼
1. STT        Mistral voxtral-mini-2507   — transcribes your audio
   │
   ▼
2. Sentiment  Rule-based detector         — classifies as angry / neutral
   │
   ▼
3. RAG        Keyword retrieval           — pulls relevant knowledge-base chunks
   │
   ▼
4. LLM        mistral-small-latest        — generates a support response
   │
   ▼
5. TTS        Mistral voxtral-mini-tts-2603 — converts response to speech
```

Text tokens stream word-by-word while TTS synthesizes in a background thread, so the audio is ready the moment the last word appears.

## Project structure

```
voice-support-agent/
├── backend/
│   ├── main.py           # FastAPI app — pipeline, SSE, routes
│   ├── rag.py            # Knowledge base + keyword retrieval
│   ├── sentiment.py      # Rule-based sentiment classifier
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── app.js            # MediaRecorder, SSE consumer, UI
│   └── style.css
├── .env                  # Your API key (gitignored)
├── .env.example          # Template
└── .gitignore
```

## Prerequisites

- Python 3.9+
- A [Mistral AI](https://console.mistral.ai/) account with an API key
- A modern browser (Chrome, Firefox, Edge) with microphone access

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/ajithsundaram/VoxSupport-AI.git
cd VoxSupport-AI
```

### 2. Add your API key

```bash
cp .env.example .env
```

Open `.env` and set your key:

```
MISTRAL_API_KEY=your_mistral_api_key_here
```

### 3. Install dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 4. Run the server

```bash
cd backend
python3 -m uvicorn main:app --reload --port 8000
```

### 5. Open the app

Visit [http://localhost:8000](http://localhost:8000) in your browser.

## Usage

1. Click the **microphone** button and speak your question
2. Click the button again (or it stops automatically) to send
3. Watch your words appear as transcription, see the sentiment badge, read the streamed response, and hear it spoken back

## SSE event stream

The backend streams the following events to the frontend:

| Event | Payload | Description |
|---|---|---|
| `transcription` | `{ text }` | What the user said |
| `sentiment` | `{ value }` | `"angry"` or `"neutral"` |
| `token` | `{ text }` | One word of the LLM response |
| `audio` | `{ data }` | Base64-encoded WAV |
| `done` | `{}` | Pipeline complete |
| `error` | `{ message }` | Something went wrong |

## Knowledge base

The default KB in `backend/rag.py` covers 8 topics: **billing, refunds, outages, account/login, plans, cancellation, support contacts, and technical issues**.

To extend it, add entries to the `KNOWLEDGE_BASE` list:

```python
{
    "id": 9,
    "topic": "shipping",
    "keywords": ["ship", "delivery", "track", "order", "package"],
    "text": "Orders ship within 2 business days...",
}
```

## Sentiment detection

The rule-based detector in `backend/sentiment.py` scores text by angry signal phrases, exclamation marks, and ALL-CAPS words. When a user sounds frustrated (`score >= 1`), the LLM uses an empathetic system prompt and a softer TTS voice.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `MISTRAL_API_KEY` | Yes | Your Mistral AI API key |

## Models used

| Step | Model |
|---|---|
| Speech-to-Text | `voxtral-mini-2507` |
| LLM | `mistral-small-latest` |
| Text-to-Speech | `voxtral-mini-tts-2603` |

## Sample screen

<img width="1304" height="822" alt="Screenshot 2026-04-14 at 3 37 11 PM" src="https://github.com/user-attachments/assets/56efc52f-190f-459e-a21b-e781e2abda58" />



