"""Rough time and usage estimate shown before a run.

Speech recognition speed is the ratio (processing seconds / audio seconds). The defaults below were measured
on one CPU and one RTX 3060; after each real run the page's server records what this computer actually did
(``speed.json``) and the estimate switches to the median of those runs. AI time is a flat figure per call.
Rendering time is not included. Everything here is a guess to set expectations, never a promise.
"""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

LOAD_SEC = 0  # model loading is already part of the measured ratios below
AI_CALL_SEC = 12  # one model call; measured 6-10 s on short and full-length transcripts
WINDOW_SEC, OVERLAP_SEC = 3600, 240  # same as finder.Config
KEEP_RUNS = 5
SPEAKER_RTF = 0.13  # speaker labelling: 58-80 s per 10 audio minutes on a 16-core CPU (4 threads); not learned per computer

# (model, device) -> processing seconds per audio second. CPU: measured on a 16-core desktop with 2-10 minute
# samples (it varies with other load, small gave 0.17-0.23). cuda: small measured on an RTX 3060 (65 min in 160 s);
# the other cuda values scale that by the CPU ratios between models, so treat them as rougher.
DEFAULT_RTF = {
    ("tiny", "cpu"): 0.05, ("base", "cpu"): 0.08, ("small", "cpu"): 0.2, ("medium", "cpu"): 0.8,
    ("tiny", "cuda"): 0.01, ("base", "cuda"): 0.016, ("small", "cuda"): 0.041, ("medium", "cuda"): 0.16,
}


def windows_for(duration: float) -> int:
    """How many transcript windows (= model calls per pass) an episode needs."""
    if duration <= WINDOW_SEC:
        return 1
    return math.ceil((duration - WINDOW_SEC) / (WINDOW_SEC - OVERLAP_SEC)) + 1


def _load(path: Path | None) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record_speed(path: Path | str | None, model: str, device: str, audio_sec: float, elapsed_sec: float) -> None:
    """Remember how fast recognition ran on this computer (keeps the last few runs per model and device)."""
    if not path or audio_sec < 60 or elapsed_sec <= 0:
        return
    path = Path(path)
    data = _load(path)
    runs = [r for r in data.get(f"{model}|{device}", []) if isinstance(r, (int, float))]
    data[f"{model}|{device}"] = (runs + [round(elapsed_sec / audio_sec, 4)])[-KEEP_RUNS:]
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def rtf(model: str, device: str, stats_path: Path | None = None) -> tuple[float, bool]:
    """(ratio, learned) - learned is True when it comes from this computer's own runs."""
    runs = [r for r in _load(stats_path).get(f"{model}|{device}", []) if isinstance(r, (int, float)) and r > 0]
    if runs:
        return statistics.median(runs), True
    return DEFAULT_RTF.get((model, device), DEFAULT_RTF[("small", "cpu")]), False


def estimate(kind: str, duration: float, *, model: str = "small", device: str = "cpu", has_srt: bool = False,
             use_ai: bool = True, stats_path: Path | None = None, speakers: bool = False) -> dict:
    """kind is "clips" or "plan". Returns seconds and call counts plus short notes for the page."""
    notes: list[str] = []
    windows = windows_for(duration)
    if has_srt:
        transcribe_sec = 0.0
        notes.append("已附字幕檔，會跳過語音辨識。")
    else:
        ratio, learned = rtf(model, device, stats_path)
        transcribe_sec = LOAD_SEC + ratio * duration
        notes.append("語音辨識時間依這台電腦的實際跑分估算。" if learned else
                     "語音辨識時間是參考值，第一次跑完後會改用這台電腦的實測；第一次使用某個模型還要另外下載。")
    if kind == "clips":
        calls = windows
    elif kind == "plan":
        calls = 2 * windows if use_ai else 0  # AI cuts + the section outline, one pass each
    else:
        raise ValueError("kind must be clips or plan")
    speaker_sec = SPEAKER_RTF * duration if speakers else 0.0
    if speakers:
        notes.append("說話者辨識時間是參考值；第一次使用要先下載約 46 MB 的模型。")
    ai_sec = calls * AI_CALL_SEC
    if calls:
        notes.append(f"AI 約 {calls} 次呼叫，會計入你的訂閱用量。")
    notes.append("不含切檔與輸出影片的時間。")
    return {"transcribe_sec": round(transcribe_sec), "speaker_sec": round(speaker_sec), "ai_calls": calls,
            "ai_sec": round(ai_sec), "total_sec": round(transcribe_sec + speaker_sec + ai_sec), "windows": windows,
            "notes": notes}
