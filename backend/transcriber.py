"""Real-time transcription of system audio loopback using Deepgram's streaming API."""
import asyncio
import os
import sys

import numpy as np
import soundcard as sc
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE = 1024

GREEN = "\033[92m"
RESET = "\033[0m"


def get_loopback_microphone():
    """Return the loopback microphone tied to the default output device."""
    default_speaker = sc.default_speaker()
    return sc.get_microphone(id=str(default_speaker.name), include_loopback=True)


def to_pcm16_bytes(audio_block):
    """Convert a float32 [-1, 1] audio block to 16-bit PCM bytes for Deepgram."""
    clipped = np.clip(audio_block, -1.0, 1.0)
    return (clipped * 32767).astype(np.int16).tobytes()


def handle_message(message):
    """Print the transcript in green when Deepgram marks a segment as final."""
    if getattr(message, "type", None) != "Results" or not message.is_final:
        return
    transcript = message.channel.alternatives[0].transcript
    if transcript:
        print(f"{GREEN}Entrevistador: {transcript}{RESET}")


def handle_error(error):
    """Report a Deepgram websocket error without crashing the stream."""
    print(f"\n❌ Error de Deepgram: {error}")


async def stream_to_deepgram():
    """Capture system audio in small blocks and stream it to Deepgram for live transcription."""
    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY no está definido en backend/.env")

    client = AsyncDeepgramClient(api_key=DEEPGRAM_API_KEY)
    microphone = get_loopback_microphone()

    async with client.listen.v1.connect(
        model="nova-2",
        language="es",
        encoding="linear16",
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        endpointing=800,
    ) as connection:
        connection.on(EventType.MESSAGE, handle_message)
        connection.on(EventType.ERROR, handle_error)
        listen_task = asyncio.create_task(connection.start_listening())

        print("🎧 Transcribiendo audio del sistema en tiempo real. Presiona Ctrl+C para detener.")
        with microphone.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS, blocksize=BLOCK_SIZE) as recorder:
            while True:
                audio_block = await asyncio.to_thread(recorder.record, numframes=BLOCK_SIZE)
                await connection.send_media(to_pcm16_bytes(audio_block))

        await listen_task


def main():
    try:
        asyncio.run(stream_to_deepgram())
    except KeyboardInterrupt:
        print("\n🛑 Transcripción detenida por el usuario.")
    except Exception as error:
        print(f"\n❌ Error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()