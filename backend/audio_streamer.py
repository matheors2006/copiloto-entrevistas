"""Real-time system audio loopback streamer using small blocks to avoid buffer underruns."""
import sys

import numpy as np
import soundcard as sc

sys.stdout.reconfigure(encoding="utf-8")

SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE = 1024
MAX_BAR_LENGTH = 50


def get_loopback_microphone():
    """Return the loopback microphone tied to the default output device."""
    default_speaker = sc.default_speaker()
    return sc.get_microphone(id=str(default_speaker.name), include_loopback=True)


def to_pcm16(audio_block):
    """Convert a float32 [-1, 1] audio block to 16-bit PCM samples (Deepgram-ready)."""
    clipped = np.clip(audio_block, -1.0, 1.0)
    return (clipped * 32767).astype(np.int16)


def print_volume_bar(pcm16_block):
    """Print a live volume indicator based on the RMS of a PCM16 block."""
    rms = np.sqrt(np.mean(pcm16_block.astype(np.float64) ** 2)) / 32767
    bar_length = int(rms * MAX_BAR_LENGTH)
    bar = "|" * bar_length
    print(f"\r🔊 [{bar:<{MAX_BAR_LENGTH}}] RMS={rms:.3f}", end="", flush=True)


def stream_loopback_audio():
    """Continuously capture system audio in small blocks for low-latency streaming."""
    microphone = get_loopback_microphone()

    print(f"🎧 Streaming de audio del sistema iniciado (bloques de {BLOCK_SIZE} frames). Presiona Ctrl+C para detener.")
    with microphone.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS, blocksize=BLOCK_SIZE) as recorder:
        while True:
            audio_block = recorder.record(numframes=BLOCK_SIZE)
            pcm16_block = to_pcm16(audio_block)
            print_volume_bar(pcm16_block)


def main():
    try:
        stream_loopback_audio()
    except KeyboardInterrupt:
        print("\n🛑 Streaming detenido por el usuario.")
    except Exception as error:
        print(f"\n❌ Error durante el streaming: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()