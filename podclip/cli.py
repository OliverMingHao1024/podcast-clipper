"""podclip run episode.mp3 [--srt episode.srt] [--out out] [--backend claude]"""
from __future__ import annotations

import argparse
import json
import logging
import re
import shlex
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__, srt
from .finder import Config, find_clips
from .llm import ClaudeCLI, CommandBackend, LLMError
from .render import DEFAULT_FONT, RenderError, cut_audio, waveform_video, write_srt

AUDIO_EXT = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac", ".opus", ".mp4", ".mkv", ".webm"}
FORMATS = ("audio", "srt", "video")


def _slug(text: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", text).strip("._")
    return cleaned[:40] or "clip"


def _backend(args: argparse.Namespace):
    if args.backend == "claude":
        return ClaudeCLI(model=args.model)
    if not args.cmd:
        raise SystemExit("--backend cmd needs --cmd, e.g. --cmd \"mytool --stdin\"")
    return CommandBackend(shlex.split(args.cmd))


def _run(args: argparse.Namespace) -> int:
    src = Path(args.input).expanduser().resolve()
    if not src.is_file() or src.suffix.lower() not in AUDIO_EXT:
        raise SystemExit(f"not a supported audio file: {src}")
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    if bad := [f for f in formats if f not in FORMATS]:
        raise SystemExit(f"unknown format {bad}; choose from {FORMATS}")
    if "video" in formats and "srt" not in formats:
        formats.append("srt")  # the video burns the subtitles in

    if args.srt:
        cues = srt.read(Path(args.srt).expanduser())
    else:
        from .transcribe import transcribe
        print("transcribing locally...", file=sys.stderr)
        cues = transcribe(src, model=args.whisper_model, language=args.language, device=args.device)
        Path(args.out).mkdir(parents=True, exist_ok=True)
        srt.write(Path(args.out) / f"{src.stem}.srt", cues)

    cfg = Config(min_sec=args.min_sec, max_sec=args.max_sec, threshold=args.threshold,
                 max_clips=args.max_clips, language=args.title_language)
    print(f"{len(cues)} cues, asking the model for clips...", file=sys.stderr)
    clips = find_clips(cues, _backend(args), cfg)

    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for n, clip in enumerate(clips, 1):
        folder = out / f"{n:02d}_{_slug(clip.title)}"
        folder.mkdir(exist_ok=True)
        entry = {"index": n, "folder": folder.name, **{k: v for k, v in asdict(clip).items() if k != "extra"}}
        if not args.dry_run:
            base = folder / "clip"
            audio = cut_audio(src, clip, base, args.audio_ext) if ("audio" in formats or "video" in formats) else None
            subs = write_srt(cues, clip, base) if "srt" in formats else None
            if "video" in formats and audio and subs:
                waveform_video(audio, subs, clip.duration, base, font=args.font)
            (folder / "post.txt").write_text(f"{clip.title}\n\n{clip.reason}\n", encoding="utf-8")
        manifest.append(entry)
    (out / "clips.json").write_text(json.dumps({"source": src.name, "clips": manifest}, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    for e in manifest:
        print(f"{e['index']:02d} [{e['start']:.0f}s-{e['end']:.0f}s] {e['score']:.2f} {e['title']}")
    print(f"done: {len(manifest)} clips -> {out}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="podclip", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="find and cut clips from an audio file")
    r.add_argument("input")
    r.add_argument("--srt", help="existing subtitle file; skips transcription")
    r.add_argument("--out", default="out")
    r.add_argument("--backend", choices=("claude", "cmd"), default="claude")
    r.add_argument("--model", help="model name passed to the claude CLI")
    r.add_argument("--cmd", help="for --backend cmd: command that reads the prompt on stdin and prints JSON")
    r.add_argument("--formats", default="audio,srt,video", help="comma list of audio,srt,video")
    r.add_argument("--audio-ext", default=".mp3", choices=(".mp3", ".m4a", ".wav"))
    r.add_argument("--min-sec", type=float, default=45)
    r.add_argument("--max-sec", type=float, default=180)
    r.add_argument("--threshold", type=float, default=0.7)
    r.add_argument("--max-clips", type=int, default=10)
    r.add_argument("--title-language", default="繁體中文")
    r.add_argument("--language", help="spoken language code for Whisper, e.g. zh")
    r.add_argument("--whisper-model", default="small")
    r.add_argument("--device", choices=("cpu", "cuda"), default="cpu", help="Whisper device; cuda needs the gpu extra")
    r.add_argument("--font", default=DEFAULT_FONT)
    r.add_argument("--dry-run", action="store_true", help="only write clips.json, cut nothing")
    r.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    try:
        return _run(args)
    except (LLMError, RenderError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
