"""FastAPI server exposing the interview copilot pipeline over a WebSocket."""
import asyncio
import io
import json
import os

import numpy as np
import soundcard as sc
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pypdf import PdfReader

from llm_engine import procesar_cv_pdf, stream_respuesta, traducir_pregunta

load_dotenv()

app = FastAPI()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE = 1024
CV_MOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cv_mock.json")
ENGLISH_HINT_WORDS = {"the", "what", "how", "why", "would", "could", "is", "are", "you", "your", "when"}
SPANISH_HINT_CHARS = "ñáéíóúü¿¡"


def looks_like_english(text):
    """Lightweight fallback when Deepgram's language metadata is unavailable."""
    words = set(text.lower().split())
    return bool(words & ENGLISH_HINT_WORDS) and not any(char in text for char in SPANISH_HINT_CHARS)


@app.post("/upload-cv")
async def upload_cv(file: UploadFile = File(...)):
    """Extract text from an uploaded PDF CV and regenerate the structured profile via the LLM."""
    try:
        pdf_bytes = await file.read()
        reader = PdfReader(io.BytesIO(pdf_bytes))
        texto_pdf = "\n".join(page.extract_text() or "" for page in reader.pages).strip()

        if not texto_pdf:
            return JSONResponse(status_code=400, content={"message": "No se pudo extraer texto del PDF"})

        await procesar_cv_pdf(texto_pdf)
        return {"message": "CV actualizado correctamente"}
    except Exception as error:
        return JSONResponse(status_code=500, content={"message": f"Error al procesar el CV: {error}"})


def get_loopback_microphone():
    """Return the loopback microphone tied to the default output device."""
    default_speaker = sc.default_speaker()
    return sc.get_microphone(id=str(default_speaker.name), include_loopback=True)


def to_pcm16_bytes(audio_block):
    """Convert a float32 [-1, 1] audio block to 16-bit PCM bytes for Deepgram."""
    clipped = np.clip(audio_block, -1.0, 1.0)
    return (clipped * 32767).astype(np.int16).tobytes()


async def pump_loopback_audio(deepgram_connection):
    """Continuously capture system audio in small blocks and forward it to Deepgram."""
    microphone = get_loopback_microphone()
    with microphone.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS, blocksize=BLOCK_SIZE) as recorder:
        while True:
            audio_block = await asyncio.to_thread(recorder.record, numframes=BLOCK_SIZE)
            await deepgram_connection.send_media(to_pcm16_bytes(audio_block))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    if not DEEPGRAM_API_KEY:
        await websocket.close(code=1011, reason="DEEPGRAM_API_KEY no configurado")
        return

    with open(CV_MOCK_PATH, encoding="utf-8") as f:
        cv_json = json.load(f)

    accumulated_transcript = []
    llm_task = None
    translation_task = None

    async def run_llm_response(question_text):
        """Stream the LLM answer as a standalone task, decoupled from the Deepgram listener."""
        async for token in stream_respuesta(question_text, cv_json):
            await websocket.send_json({"type": "answer_token", "text": token})

    async def run_translation(question_text):
        """Translate an English question to Spanish as a standalone task and forward it to the client."""
        translated = await traducir_pregunta(question_text)
        await websocket.send_json({"type": "translation", "text": f"Traducción: {translated}"})

    async def handle_deepgram_message(message):
        """Stream the accumulating question live, then hand off to the LLM once speech_final ends it.

        The LLM call runs as a separate task instead of being awaited here, since awaiting it
        directly would block this handler and, with it, the Deepgram listen loop that calls it
        (`_emit_async` awaits each callback before reading the next websocket message).
        """
        nonlocal llm_task, translation_task
        if getattr(message, "type", None) != "Results" or not message.is_final:
            return

        alternative = message.channel.alternatives[0]
        transcript = alternative.transcript
        if transcript:
            accumulated_transcript.append(transcript)

        if not message.speech_final:
            if accumulated_transcript:
                await websocket.send_json(
                    {"type": "interim_question", "text": " ".join(accumulated_transcript).strip()}
                )
            return

        full_question = " ".join(accumulated_transcript).strip()
        accumulated_transcript.clear()
        if not full_question:
            return

        if llm_task is not None and not llm_task.done():
            llm_task.cancel()
        if translation_task is not None and not translation_task.done():
            translation_task.cancel()

        await websocket.send_json({"type": "question", "text": full_question})
        await websocket.send_json({"type": "clear_answer"})
        llm_task = asyncio.create_task(run_llm_response(full_question))

        detected_languages = alternative.languages or []
        is_english = "en" in detected_languages or (not detected_languages and looks_like_english(full_question))
        translation_task = asyncio.create_task(run_translation(full_question)) if is_english else None

    deepgram_client = AsyncDeepgramClient(api_key=DEEPGRAM_API_KEY)

    async with deepgram_client.listen.v1.connect(
        model="nova-2",
        language="multi",
        encoding="linear16",
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        endpointing=1500,
    ) as connection:
        connection.on(EventType.MESSAGE, handle_deepgram_message)

        listen_task = asyncio.create_task(connection.start_listening())
        audio_task = asyncio.create_task(pump_loopback_audio(connection))
        disconnect_task = asyncio.create_task(websocket.receive_text())

        pending = {listen_task, audio_task, disconnect_task}
        try:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is not disconnect_task and task.exception():
                    raise task.exception()
        except WebSocketDisconnect:
            pass
        finally:
            for task in pending:
                task.cancel()
            for task in (llm_task, translation_task):
                if task is not None:
                    task.cancel()
            extra_tasks = [task for task in (llm_task, translation_task) if task is not None]
            await asyncio.gather(
                listen_task,
                audio_task,
                disconnect_task,
                *extra_tasks,
                return_exceptions=True,
            )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
