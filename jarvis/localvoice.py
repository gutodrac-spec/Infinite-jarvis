"""Voz local, leve e grátis: Whisper (faster-whisper) para ouvir e Piper para falar.

Roda na CPU do próprio Codespace/PC. O áudio da chamada pelo navegador trafega como PCM 16 bits, 16 kHz, mono.
"""
import io
import os
from functools import lru_cache
from pathlib import Path

import httpx
import numpy as np
import soxr

RATE = 16000
MODELS_DIR = Path(os.getenv("JARVIS_MODELS_DIR", "./models")).resolve()
PIPER_VOICE = os.getenv("PIPER_VOICE", "pt_BR-faber-medium")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")  # tiny | base | small (melhor, mais lento)


# ---------- Ouvir (Whisper) ----------

@lru_cache(maxsize=1)
def _whisper():
    from faster_whisper import WhisperModel

    return WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8", download_root=str(MODELS_DIR / "whisper"))


def _transcribe(audio) -> str:
    segments, _ = _whisper().transcribe(audio, language="pt", beam_size=1, vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()


def transcribe_pcm(pcm: bytes) -> str:
    """Uma fala da chamada (PCM 16 bits, 16 kHz) → texto."""
    return _transcribe(np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768)


def transcribe_file(audio: bytes, mime: str = "audio/ogg") -> str:
    """Áudio do WhatsApp (ogg/opus, mp3 etc.) → texto."""
    return _transcribe(io.BytesIO(audio))


# ---------- Falar (Piper) ----------

def _voice_path() -> Path:
    return MODELS_DIR / "piper" / f"{PIPER_VOICE}.onnx"


@lru_cache(maxsize=1)
def _piper():
    from piper import PiperVoice

    return PiperVoice.load(_voice_path())


def synthesize(text: str) -> bytes:
    """Texto → PCM 16 bits, 16 kHz."""
    chunks = list(_piper().synthesize(text))
    if not chunks:
        return b""
    audio = soxr.resample(np.concatenate([c.audio_float_array for c in chunks]), chunks[0].sample_rate, RATE)
    return np.clip(audio * 32767, -32768, 32767).astype(np.int16).tobytes()


def download_models() -> None:
    """Baixa a voz do Piper e o modelo do Whisper (uma vez, ~200 MB no total)."""
    lang, rest = PIPER_VOICE.split("-", 1)
    name, quality = rest.rsplit("-", 1)
    base = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang.split('_')[0]}/{lang}/{name}/{quality}/{PIPER_VOICE}"
    target = _voice_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".onnx", ".onnx.json"):
        dest = target.with_name(PIPER_VOICE + suffix)
        if dest.exists():
            continue
        print(f"Baixando {dest.name}...")
        with httpx.stream("GET", base + suffix, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                for block in r.iter_bytes():
                    f.write(block)
    print(f"Carregando Whisper '{WHISPER_MODEL}'...")
    _whisper()
    print("Modelos prontos em", MODELS_DIR)
