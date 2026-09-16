# Interview Copilot

A real-time, bilingual (ES/EN) desktop AI copilot that listens to a live interview call and
streams back short, human-sounding talking points for the candidate — grounded in their own
CV. Built as a floating, low-latency overlay on top of a fully async speech-to-text → LLM
pipeline.

> Full architecture, WebSocket event dictionary, and concurrency model: see
> [`docs/SPEC.md`](docs/SPEC.md).

## Overview

During a live interview, Interview Copilot:

1. Captures the system's audio output (the interviewer's voice, via WASAPI loopback) — no
   microphone or interviewer-side install required.
2. Transcribes it in real time with Deepgram's streaming speech-to-text API, auto-detecting
   Spanish or English per question.
3. Feeds the finalized question, together with the candidate's structured CV profile, to a
   Groq-hosted LLM, which streams back 2–3 short, first-person talking points — phrased the
   way the candidate would actually say them out loud, not as an AI-generated checklist.
4. Renders everything in a frameless, draggable, opacity-adjustable overlay window that stays
   on top of a video call.

Two manual controls close the loop between the automated pipeline and how a real interview
actually flows:

- **⚡ Force Response** — manually re-runs the LLM on the current/last question, for when
  Deepgram's endpointing is slow to finalize an utterance.
- **⏸ Pause / ▶ Play** — mutes audio capture during small talk without dropping the Deepgram
  connection, so there's zero reconnect latency when the interview resumes.

## Architecture stack

| Layer | Technology |
|---|---|
| Desktop shell | [Tauri](https://tauri.app/) (Rust) — frameless, always-on-top overlay window |
| Frontend | React + TypeScript, Tailwind CSS |
| Backend | Python, [FastAPI](https://fastapi.tiangolo.com/) (WebSocket + REST) |
| Speech-to-text | [Deepgram](https://deepgram.com/) streaming API (`nova-2`, multi-language) |
| LLM reasoning | [Groq](https://groq.com/) (`openai/gpt-oss-120b` for answers, `openai/gpt-oss-20b` for fast translation) |
| Audio capture | [`soundcard`](https://github.com/bastibe/SoundCard) (WASAPI loopback) |
| PDF parsing | [`pypdf`](https://pypdf.readthedocs.io/) |

## Project structure

```
backend/
  main.py            FastAPI app: /ws WebSocket pipeline + /upload-cv endpoint
  llm_engine.py       Groq prompt engineering: talking points, translation, CV extraction
  cv_mock.json        Structured candidate profile (regenerated on CV upload)
  requirements.txt
desktop-ui/
  src/App.tsx          Overlay UI: question/answer panes, pause, force-response, CV upload
  src-tauri/           Tauri window config, capabilities, Rust shell
docs/
  SPEC.md              System specification (architecture, WS protocol, concurrency model)
.skills/
  interview_copilot/   Agent Skill (SKILL.md) documenting this pipeline for AI coding agents
```

## Setup & installation

### Prerequisites

- Python 3.12+
- Node.js 18+ and Rust (stable toolchain) for Tauri
- A [Deepgram](https://console.deepgram.com/) API key
- A [Groq](https://console.groq.com/) API key
- Windows with a default playback device (loopback capture is WASAPI-based)

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Create `backend/.env`:

```
DEEPGRAM_API_KEY=your_deepgram_key
GROQ_API_KEY=your_groq_key
```

Run the server:

```bash
python main.py
# or: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Desktop UI

```bash
cd desktop-ui
npm install
npm run tauri dev
```

### One-click launcher

`lanzador_copiloto.bat` (repo root) frees port 8000 if a previous instance is still bound to
it, then opens the backend and the Tauri dev server in separate terminals.

## Usage

1. Start the backend and the desktop UI (via the launcher, or the two commands above).
2. Play or join the interview call so its audio goes through your system's default output
   device.
3. The overlay shows the interviewer's question live as it's transcribed, then streams the
   talking points underneath as Groq generates them.
4. If the question was in English, a Spanish translation appears under it.
5. Click **⏸ Pause** during small talk to stop listening without losing the connection; click
   **▶ Play** to resume instantly.
6. Click **⚡ Forzar Respuesta** to manually trigger an answer from the current transcript if
   Deepgram hasn't finalized it yet.
7. Click **Subir CV** to replace the candidate profile with a new PDF at any time — every
   answer after that is grounded in the new CV.

## Design principles

- **Never block the transcription loop.** LLM calls run as detached `asyncio.Task`s; awaiting
  them inline would stall Deepgram's event listener and freeze the whole pipeline.
- **The candidate is a human, not an AI.** The LLM's system prompt enforces a first-person,
  conversational tone and forbids AI-tutorial formatting (numbered steps, "in summary", etc.).
- **Fail soft.** Groq/WebSocket errors are caught and logged, never allowed to take down the
  live connection mid-interview.
- **No stealth mode.** This project deliberately does not attempt to hide the overlay from
  screen-share or recording software — it's built as a personal accessibility/preparation
  aid, not a tool for deceiving an interviewer.
