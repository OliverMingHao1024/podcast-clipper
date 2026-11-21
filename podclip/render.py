"""FFmpeg output: audio clip, per-clip SRT, optional 9:16 waveform video with burned subtitles."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from . import srt
from .finder import Clip

AUDIO_CODECS = {".mp3": ["-c:a", "libmp3lame", "-q:a", "2"], ".m4a": ["-c:a", "aac", "-b:a", "128k"],
                ".wav": ["-c:a", "pcm_s16le"]}
DEFAULT_FONT = {"win32": "Microsoft JhengHei", "darwin": "PingFang TC"}.get(sys.platform, "Noto Sans CJK TC")


class RenderError(RuntimeError):
    pass


def ffmpeg_path() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RenderError("ffmpeg not found on PATH")
    return exe


def _run(args: list[str], cwd: Path) -> None:
    proc = subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", *args], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RenderError(f"ffmpeg failed: {proc.stderr.strip()[-400:]}")


def cut_audio(src: Path, clip: Clip, out: Path, ext: str = ".mp3") -> Path:
    if ext not in AUDIO_CODECS:
        raise RenderError(f"unsupported audio format {ext}")
    target = out.with_suffix(ext)
    _run(["-ss", f"{clip.start:.3f}", "-t", f"{clip.duration:.3f}", "-i", str(src.resolve()), "-vn",
          *AUDIO_CODECS[ext], str(target.resolve())], out.parent)
    return target


def clip_cues(cues: list[srt.Cue], clip: Clip) -> list[srt.Cue]:
    return [replace(c, start=max(c.start, clip.start), end=min(c.end, clip.end))
            for c in cues[clip.start_row:clip.end_row + 1]]


def write_srt(cues: list[srt.Cue], clip: Clip, out: Path) -> Path:
    target = out.with_suffix(".srt")
    srt.write(target, clip_cues(cues, clip), offset=clip.start)
    return target


# aspect -> (width, height, waveform height). The wave is centred; subtitles sit near the bottom.
ASPECTS = {"9:16": (1080, 1920, 500), "1:1": (1080, 1080, 400), "16:9": (1920, 1080, 360)}


def waveform_video(audio: Path, subtitles: Path, duration: float, out: Path, *, font: str = DEFAULT_FONT,
                   wave_color: str = "0x6AA9FF", aspect: str = "9:16") -> Path:
    """Dark background, centred waveform, subtitles near the bottom (1080x1920 for 9:16, see ASPECTS).

    ffmpeg runs inside the clip folder and gets bare file names, which avoids the drive-letter and
    backslash escaping the subtitles filter needs for absolute Windows paths.
    """
    if not font.replace(" ", "").isalnum():
        raise RenderError("font name may contain only letters, digits and spaces")
    if not re.fullmatch(r"0x[0-9A-Fa-f]{6}", wave_color):
        raise RenderError("wave_color must look like 0x6AA9FF")
    if aspect not in ASPECTS:
        raise RenderError(f"aspect must be one of {', '.join(ASPECTS)}")
    width, height, wave_h = ASPECTS[aspect]
    folder = audio.parent
    target = out.with_suffix(".mp4")
    style = f"FontName={font},FontSize=14,PrimaryColour=&H00FFFFFF&,OutlineColour=&H00000000&,Outline=2,Alignment=2,MarginV=40"  # libass scales margins from a 288-high canvas: 40 -> ~270 px on 1920
    # showwaves emits premultiplied RGBA at a fixed ~61% alpha: an alpha overlay (or a gain on the
    # colour planes) gives a dark, wrong-hued wave. Only its shape is trusted: take the alpha plane,
    # binarise it, and merge it as the alpha of a solid colour, which overlays with straight alpha.
    graph = (f"color=c=0x101114:s={width}x{height}:d={duration:.3f},format=rgba[bg];"
             f"[0:a]aformat=channel_layouts=mono,showwaves=s={width}x{wave_h}:mode=cline:scale=sqrt:rate=25,"
             f"format=rgba,alphaextract,lutyuv=y='if(gt(val,0),255,0)'[mask];"
             f"color=c={wave_color}:s={width}x{wave_h}:d={duration:.3f},format=rgba[tint];"
             f"[tint][mask]alphamerge[wave];"
             f"[bg][wave]overlay=0:{(height - wave_h) // 2}:shortest=1:format=auto,"
             f"subtitles={subtitles.name}:force_style='{style}',format=yuv420p[v]")
    _run(["-i", audio.name, "-filter_complex", graph, "-map", "[v]", "-map", "0:a", "-c:v", "libx264",
          "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-shortest", target.name], folder)
    return target
