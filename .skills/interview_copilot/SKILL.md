---
name: interview_copilot
description: >
  Playbook for working on the Interview Copilot real-time audio pipeline: FastAPI WebSocket
  server orchestrating system audio loopback capture, Deepgram streaming speech-to-text
  (audio streaming, deepgram websocket, live transcription, speech_final/endpointing),
  Groq LLM reasoning grounded in a candidate CV JSON (groq llm, prompt engineering, talking
  points, language lock), and the Tauri/React floating overlay (tauri overlay, desktop
  window, WebSocket client). Use this skill whenever touching backend/main.py,
  backend/llm_engine.py, desktop-ui/src/App.tsx, the /ws WebSocket protocol, audio capture
  timing, Deepgram connection lifecycle, or Groq prompt/response behavior in this repo.
  Do NOT use for general web development tasks unrelated to the real-time audio pipeline
  (e.g. unrelated CRUD endpoints, styling-only changes, or generic React work that does not
  touch the WebSocket/audio/LLM flow).
---

# Interview Copilot — Real-Time Audio Pipeline Playbook

This skill documents the non-obvious rules that keep the `/ws` pipeline in
`backend/main.py` and `backend/llm_engine.py` alive under real interview conditions. Read
[`docs/SPEC.md`](../../docs/SPEC.md) first for the full architecture and WebSocket event
dictionary; this file is the "how to change it safely" companion.

## The one rule that matters most: never block the Deepgram listen loop

The Deepgram SDK's `connection.start_listening()` drives an `_emit_async` loop that
**awaits each registered callback to completion before reading the next WebSocket message**.

`handle_deepgram_message` (the callback registered via `connection.on(EventType.MESSAGE,
...)`) therefore must never directly `await` anything slow — in particular, never `await`
an LLM call inline. Doing so blocks Deepgram's own message loop for the full duration of the
LLM stream, which starves the transcription pipeline. This was the root cause of a real,
previously-shipped bug: the app worked for the first 2–3 questions, then appeared to go
"deaf," because the third `await stream_respuesta(...)` inline call blocked
`start_listening()` from ever reading Deepgram's next message.

**The fix, and the pattern to always follow when adding new LLM-driven behavior:**

```python
# WRONG — blocks the Deepgram listener for the whole LLM stream
async def handle_deepgram_message(message):
    ...
    async for token in stream_respuesta(full_question, cv_json, detected_language):
        await send_json_safe({"type": "answer_token", "text": token})

# RIGHT — decoupled, fire-and-forget task
async def handle_deepgram_message(message):
    ...
    llm_task = asyncio.create_task(run_llm_response(full_question, detected_language))
```

Any new feature that calls Groq (or any other slow I/O) from inside a Deepgram callback or
the client-message listener must use `asyncio.create_task(...)`, track the task in a
connection-scoped variable, and cancel the previous one before starting a new one (see
`llm_task` / `translation_task` in `main.py`) — otherwise overlapping questions will produce
interleaved or stale answers.

## Concurrency map

Each `/ws` connection runs these tasks concurrently (details in `docs/SPEC.md` §5):

- `listen_task` — Deepgram's `start_listening()`. Must stay unblocked (see above).
- `audio_task` — `pump_loopback_audio`. Streams mic/loopback audio, or KeepAlive frames while
  paused. Runs independently.
- `client_listener_task` — `listen_to_client`. Loops on `websocket.receive_text()` for the
  connection's lifetime, handling client-sent control messages (`force_response`,
  `toggle_pause`). This is a loop, not a single `await` — a single-shot listener would end
  the whole connection after the client's first message.
- `llm_task` / `translation_task` — per-question, fire-and-forget, cancelled and replaced on
  every new finalized question or `force_response`.

All WebSocket sends — from the main handler and from every background task — must go through
`send_json_safe`, which holds a single `asyncio.Lock` for the connection. Calling
`websocket.send_json(...)` directly from a new background task will race with other senders
and can corrupt the WebSocket frame stream.

## Strict error-handling requirements

- Every Groq call reachable from a background task (`stream_respuesta`,
  `traducir_pregunta`, and any new one you add) must catch its own exceptions, log them, and
  degrade gracefully (empty stream / `None` return) — **never let a Groq timeout, rate limit,
  or connection error propagate and kill the WebSocket.**
- `send_json_safe` must remain the only place that calls `websocket.send_json`, and it must
  keep catching send failures instead of raising.
- HTTP endpoints (e.g. `/upload-cv`) must translate internal errors into `HTTPException` so
  FastAPI's CORS middleware still attaches CORS headers to the error response — a raw
  unhandled exception can produce a response the Tauri webview's CORS check silently rejects.

## Prompt engineering fallback strategies

- **Language lock beats CV language.** `stream_respuesta` always appends the language-lock
  system message (`build_language_lock_prompt`) **last**, after the CV-grounded user message,
  to exploit recency bias — otherwise a Spanish-heavy CV can pull an English-language
  question's answer back into Spanish. If you add new system messages, keep the language lock
  last unless you've re-verified language compliance empirically (see `docs/SPEC.md` §6).
- **Never say "I don't know."** The system prompt's contingency rule forbids "not in the CV" /
  "no experience" answers — for unfamiliar tech, the model must reason from adjacent
  experience or general engineering knowledge, in first person, as the candidate would.
- **Sound human, not like an AI tutorial.** The persona prompt bans numbered lists, "Step 1/2",
  and AI clichés ("here's how I'd do it", "in summary"). When editing `SYSTEM_PROMPT`, keep
  new instructions in that same first-person, conversational register — don't reintroduce
  tutorial-style formatting.
- **Verify empirically after any prompt change.** Prompt edits in this codebase have
  previously broken the language lock in subtle ways (e.g. Spanish-only tone examples leaking
  into English answers). After editing `SYSTEM_PROMPT` or `build_language_lock_prompt`, run a
  quick manual check with both `idioma_detectado="es"` and `"en"` before committing.

## Audio pipeline notes

- Loopback capture is WASAPI-based (`soundcard`), tied to the current default output device —
  there is no separate microphone input; the app listens to what the machine is playing.
- While paused (`PauseState.is_paused`), `pump_loopback_audio` must skip real audio capture
  entirely and send periodic `connection.send_keep_alive()` frames instead — this avoids
  Deepgram's inactivity timeout without billing/streaming audio during small talk. Do not
  close and reopen the Deepgram connection for pause/resume; the keepalive approach avoids
  reconnect latency on resume.
- `endpointing` (currently 1500ms) controls how long Deepgram waits after silence before
  marking `speech_final`. Lowering it improves responsiveness but risks cutting off slower
  speakers mid-sentence; changing it is a UX trade-off, not a pure bug fix.
