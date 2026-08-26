"""Loopback capture test: records the operating system's audio output."""
import sys

import numpy as np
import soundcard as sc
import soundfile as sf

sys.stdout.reconfigure(encoding="utf-8")

SAMPLE_RATE = 16000
CHANNELS = 1
DURATION_SECONDS = 5
OUTPUT_FILENAME = "system_audio_test.wav"


def get_loopback_microphone():
    """Return the loopback microphone tied to the default output device."""
    default_speaker = sc.default_speaker()
    return sc.get_microphone(id=str(default_speaker.name), include_loopback=True)


def record_system_audio(duration=DURATION_SECONDS, samplerate=SAMPLE_RATE, channels=CHANNELS):
    """Record system output audio (loopback) for a fixed duration."""
    microphone = get_loopback_microphone()
    num_frames = int(duration * samplerate)

    print("🎧 Grabando audio del sistema por 5 segundos...")
    with microphone.recorder(samplerate=samplerate, channels=channels) as recorder:
        audio_data = recorder.record(numframes=num_frames)

    return audio_data


def save_audio(audio_data, filename=OUTPUT_FILENAME, samplerate=SAMPLE_RATE):
    """Save float32 audio data to a 16-bit PCM WAV file, clipping to avoid overflow."""
    audio_data = np.clip(audio_data, -1.0, 1.0).astype(np.float32)
    sf.write(filename, audio_data, samplerate, subtype="PCM_16")
    print(f"✅ Audio guardado en {filename}")


def main():
    try:
        audio_data = record_system_audio()
    except Exception as error:
        print(f"❌ Error al grabar audio: {error}")
        sys.exit(1)

    save_audio(audio_data)


if __name__ == "__main__":
    main()
