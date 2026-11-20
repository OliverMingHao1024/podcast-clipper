"""Optional local speech-to-text with faster-whisper (pip install -e .[asr]). Runs fully offline once
the model is cached; nothing is uploaded."""
from __future__ import annotations

import os
from pathlib import Path

from .srt import Cue


def _expose_pip_cuda_libs() -> None:
    """Make the DLLs from `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12` loadable (Windows)."""
    if not hasattr(os, "add_dll_directory"):
        return
    try:
        import nvidia
    except ImportError:
        return
    for root in nvidia.__path__:
        for bin_dir in Path(root).glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def transcribe(audio: Path, *, model: str = "small", language: str | None = None, device: str = "cpu") -> list[Cue]:
    # device defaults to cpu: "auto" picks a CUDA GPU when one is seen even if the CUDA libraries are missing.
    if device == "cuda":
        _expose_pip_cuda_libs()
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError("faster-whisper is not installed; run: pip install -e .[asr], or pass --srt") from error
    engine = WhisperModel(model, device=device, compute_type="int8" if device == "cpu" else "float16")
    segments, _info = engine.transcribe(str(audio), language=language, vad_filter=True)
    cues = [Cue(s.start, s.end, s.text.strip()) for s in segments if s.text.strip() and s.end > s.start]
    if not cues:
        raise RuntimeError("transcription produced no text")
    return cues
