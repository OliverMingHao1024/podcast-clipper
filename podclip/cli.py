"""podclip run episode.mp3 [--srt episode.srt] [--out out] [--backend claude]"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__, srt
from .finder import Clip, Config, find_clips_with_alternates
from .llm import LLMError, make_backend, named_commands
from .render import ASPECTS, DEFAULT_FONT, RenderError, cut_audio, waveform_video, write_srt

AUDIO_EXT = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac", ".opus", ".mp4", ".mkv", ".webm"}
FORMATS = ("audio", "srt", "video")


def _slug(text: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", text).strip("._")
    return cleaned[:40] or "clip"


def _backend(args: argparse.Namespace):
    try:
        return make_backend(args.backend, model=args.model, cmd=args.cmd)
    except ValueError as error:
        raise SystemExit(str(error))


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

    # the ideal length the model is told about follows the allowed range (45-180 s gives the old 60-120 s)
    cfg = Config(min_sec=args.min_sec, max_sec=args.max_sec, target_lo=max(args.min_sec, round(args.max_sec / 3)),
                 target_hi=round(args.max_sec * 2 / 3), threshold=args.threshold, max_clips=args.max_clips,
                 language=args.title_language)
    print(f"{len(cues)} cues, asking the model for clips...", file=sys.stderr)
    clips, alternates = find_clips_with_alternates(cues, _backend(args), cfg)

    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    options = {"formats": formats, "audio_ext": args.audio_ext, "font": args.font, "wave_color": args.wave_color,
               "aspect": args.aspect}
    manifest = [_render_clip(n, clip, src, cues, out, options, args.dry_run) for n, clip in enumerate(clips, 1)]
    srt_path = Path(args.srt).expanduser().resolve() if args.srt else out / f"{src.stem}.srt"
    _write_manifest(out, {"source": src.name, "source_path": str(src), "srt_path": str(srt_path), "options": options,
                          "clips": manifest, "alternates": [_clip_fields(c) for c in alternates]})
    for e in manifest:
        print(f"{e['index']:02d} [{e['start']:.0f}s-{e['end']:.0f}s] {e['score']:.2f} {e['title']}")
    print(f"done: {len(manifest)} clips, {len(alternates)} alternates kept -> {out}", file=sys.stderr)
    return 0


def _clip_fields(clip: Clip) -> dict:
    return {k: v for k, v in asdict(clip).items() if k != "extra"}


def _post_text(clip: Clip) -> str:
    tags = " ".join(f"#{t}" for t in clip.tags)
    parts = [clip.title, clip.description or clip.reason]
    if tags:
        parts.append(tags)
    return "\n\n".join(parts) + "\n"


def _render_clip(n: int, clip: Clip, src: Path, cues: list[srt.Cue], out: Path, options: dict, dry_run: bool) -> dict:
    folder = out / f"{n:02d}_{_slug(clip.title)}"
    folder.mkdir(exist_ok=True)
    entry = {"index": n, "folder": folder.name, **_clip_fields(clip)}
    if not dry_run:
        formats = options["formats"]
        base = folder / "clip"
        audio = cut_audio(src, clip, base, options["audio_ext"]) if ("audio" in formats or "video" in formats) else None
        subs = write_srt(cues, clip, base) if "srt" in formats else None
        if "video" in formats and audio and subs:
            waveform_video(audio, subs, clip.duration, base, font=options["font"], wave_color=options["wave_color"],
                           aspect=options.get("aspect", "9:16"))
        (folder / "post.txt").write_text(_post_text(clip), encoding="utf-8")
    return entry


def _write_manifest(out: Path, manifest: dict) -> None:
    (out / "clips.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _more(args: argparse.Namespace) -> int:
    """Render the best remaining alternates from an earlier `run` (no model call, no transcription)."""
    out = Path(args.out).expanduser().resolve()
    try:
        manifest = json.loads((out / "clips.json").read_text(encoding="utf-8"))
        alternates = list(manifest["alternates"])
        src, srt_path, options = Path(manifest["source_path"]), Path(manifest["srt_path"]), manifest["options"]
        cues = srt.read(srt_path)
        done = list(manifest["clips"])
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(f"{out / 'clips.json'} cannot be continued ({error}); run `podclip run` again")
    if not alternates:
        raise SystemExit("no alternates left")
    if not src.is_file():
        raise SystemExit(f"source file not found: {src}")
    for _ in range(min(args.count, len(alternates))):
        clip = Clip(**alternates.pop(0))
        entry = _render_clip(len(done) + 1, clip, src, cues, out, options, False)
        done.append(entry)
        print(f"{entry['index']:02d} [{entry['start']:.0f}s-{entry['end']:.0f}s] {entry['score']:.2f} {entry['title']}")
    manifest["clips"], manifest["alternates"] = done, alternates
    _write_manifest(out, manifest)
    print(f"done: {len(done)} clips, {len(alternates)} alternates left -> {out}", file=sys.stderr)
    return 0


def _supported_audio(path: str) -> Path:
    src = Path(path).expanduser().resolve()
    if not src.is_file() or src.suffix.lower() not in AUDIO_EXT:
        raise SystemExit(f"not a supported audio file: {src}")
    return src


def _edit_plan(args: argparse.Namespace) -> int:
    from . import edit
    src = _supported_audio(args.input)
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.srt:
        cues = srt.read(Path(args.srt).expanduser())
    else:
        from .transcribe import transcribe
        print("transcribing locally...", file=sys.stderr)
        cues = transcribe(src, model=args.whisper_model, language=args.language, device=args.device)
        srt.write(out / f"{src.stem}.srt", cues)
    backend = None if args.no_ai else _backend(args)
    print("looking for silences, fillers" + ("" if args.no_ai else " and AI suggestions") + "...", file=sys.stderr)
    plan = edit.build_plan(src, cues, backend, language=args.title_language)
    plan_json, plan_md = edit.write_plan(plan, cues, out)
    by_kind: dict[str, int] = {}
    for c in plan["cuts"]:
        by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1
    print(f"{len(plan['cuts'])} cuts {by_kind}\nreview: {plan_md}\nedit:   {plan_json}  (set \"apply\": false to keep a cut)")
    return 0


def _edit_render(args: argparse.Namespace) -> int:
    from . import edit
    src, duration, cuts = edit.read_plan(Path(args.plan))
    out = Path(args.out).expanduser().resolve()
    result, new_len = edit.render(src, duration, cuts, out, loudnorm=not args.no_loudnorm)
    if args.srt:
        edited = edit.remap_cues(srt.read(Path(args.srt).expanduser()), cuts, duration)
        srt.write(result.with_suffix(".srt"), edited)
    print(f"{duration / 60:.1f} min -> {new_len / 60:.1f} min: {result}", file=sys.stderr)
    return 0


def _notes(args: argparse.Namespace) -> int:
    from . import notes
    cues = srt.read(Path(args.srt).expanduser())
    text = notes.episode_notes(cues, _backend(args), language=args.title_language).render()
    if args.out:
        out = Path(args.out).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"notes: {out}", file=sys.stderr)
    print(text)
    return 0


def _add_backend_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--backend", choices=("claude", "cmd", *named_commands()), default="claude",
                   help="claude, cmd (with --cmd), or a named CLI: built-in presets and podclip-backends.json")
    p.add_argument("--model", help="model name passed to the claude CLI")
    p.add_argument("--cmd", help="for --backend cmd: command that reads the prompt on stdin and prints JSON")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="podclip", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="find and cut clips from an audio file")
    r.add_argument("input")
    r.add_argument("--srt", help="existing subtitle file; skips transcription")
    r.add_argument("--out", default="out")
    _add_backend_args(r)
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
    r.add_argument("--wave-color", default="0x6AA9FF", help="waveform colour as 0xRRGGBB")
    r.add_argument("--aspect", choices=tuple(ASPECTS), default="9:16", help="video shape: 9:16 vertical, 1:1 square, 16:9 wide")
    r.add_argument("--dry-run", action="store_true", help="only write clips.json, cut nothing")
    r.add_argument("-v", "--verbose", action="store_true")
    e = sub.add_parser("edit-plan", help="find cuts in a whole uncut episode and write a reviewable plan")
    e.add_argument("input")
    e.add_argument("--srt", help="existing subtitle file; skips transcription")
    e.add_argument("--out", default="edit")
    _add_backend_args(e)
    e.add_argument("--no-ai", action="store_true", help="only silences and fillers, no model call")
    e.add_argument("--title-language", default="繁體中文", help="language of the AI cut reasons")
    e.add_argument("--language", help="spoken language code for Whisper, e.g. zh")
    e.add_argument("--whisper-model", default="small")
    e.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    e.add_argument("-v", "--verbose", action="store_true")
    d = sub.add_parser("edit-render", help="apply a reviewed plan and write the edited episode")
    d.add_argument("plan")
    d.add_argument("--out", default="episode_edited.mp3")
    d.add_argument("--srt", help="original subtitle file; writes a remapped .srt next to the output")
    d.add_argument("--no-loudnorm", action="store_true")
    d.add_argument("-v", "--verbose", action="store_true")
    m = sub.add_parser("more", help="cut more clips from the alternates an earlier `run` kept")
    m.add_argument("out", help="the --out folder of the earlier run (contains clips.json)")
    m.add_argument("--count", type=int, default=1)
    m.add_argument("-v", "--verbose", action="store_true")
    n = sub.add_parser("notes", help="write the episode blurb (summary + 本集重點 list) from a subtitle file")
    n.add_argument("srt", help="subtitle file of the (edited) episode")
    n.add_argument("--out", help="also write the text to this file")
    _add_backend_args(n)
    n.add_argument("--title-language", default="繁體中文")
    n.add_argument("-v", "--verbose", action="store_true")
    w = sub.add_parser("web", help="start the local browser UI (for people who do not use a terminal)")
    w.add_argument("--workdir", default="podclip-work", help="where uploads and results are kept")
    w.add_argument("--port", type=int, default=0, help="0 = pick a free port")
    w.add_argument("--no-browser", action="store_true")
    args = p.parse_args(argv)
    if args.command == "web":
        from .web import serve
        return serve(Path(args.workdir).expanduser(), args.port, not args.no_browser)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    try:
        if args.command == "edit-plan":
            return _edit_plan(args)
        if args.command == "notes":
            return _notes(args)
        if args.command == "more":
            return _more(args)
        if args.command == "edit-render":
            return _edit_render(args)
        return _run(args)
    except (LLMError, RenderError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
