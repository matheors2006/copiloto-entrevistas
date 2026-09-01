"""FastAPI server exposing the interview copilot pipeline over a WebSocket."""
import asyncio
import json
import os

import numpy as np
import soundcard as sc
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from llm_engine import stream_respuesta

load_dotenv()

app = FastAPI()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE = 1024
CV_MOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cv_mock.json")


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

    async def handle_deepgram_message(message):
        """Stream the accumulating question live, then ask the LLM once speech_final ends it."""
        if getattr(message, "type", None) != "Results" or not message.is_final:
            return

        transcript = message.channel.alternatives[0].transcript
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

        await websocket.send_json({"type": "question", "text": full_question})
        async for token in stream_respuesta(full_question, cv_json):
            await websocket.send_json({"type": "answer_token", "text": token})

    deepgram_client = AsyncDeepgramClient(api_key=DEEPGRAM_API_KEY)

    async with deepgram_client.listen.v1.connect(
        model="nova-2",
        language="es",
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
            await asyncio.gather(listen_task, audio_task, disconnect_task, return_exceptions=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
