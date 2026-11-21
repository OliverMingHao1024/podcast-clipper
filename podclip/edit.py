"""Edit a whole uncut episode into one tighter episode.

Two steps so a human stays in control:

1. ``build_plan`` finds cuts and writes an editable plan (``plan.json`` + readable ``plan.md``).
   Cuts come from three places: long silences (ffmpeg silencedetect), cues that are only a filler
   ("嗯", "呃"), and stretches the model flags as retakes / recording incidents / tangents.
2. ``render`` applies the cuts whose ``apply`` is still true: one ffmpeg pass, optional loudness
   normalisation, plus a subtitle file remapped to the new timeline. Cuts that remove speech are first
   moved to the nearest pause (``snap_cuts``) and joined with a short crossfade so the background noise
   does not drop out; cuts inside pauses keep a very short fade.

The model's answer is untrusted: rows must be ints in range, kinds are whitelisted, and one AI cut
may not exceed MAX_AI_CUT_SEC. Anything else is dropped before it reaches the plan.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from . import srt
from .notes import episode_outline
from .finder import SYSTEM, Config, _extract_json, clock, windows
from .llm import LLMBackend, LLMError
from .render import RenderError, ffmpeg_path

SILENCE_DB = -35
SILENCE_MIN_SEC = 0.8     # a pause at least this long is shortened
SILENCE_KEEP_SEC = 0.4    # ... to this much
FILLER_TRIM = 0.05        # cuts of filler cues stay this far inside the cue (word edges drift)
AI_TRIM = 0.1
MIN_PIECE = 0.05
log = logging.getLogger(__name__)
FADE = 0.02
XFADE = 0.1       # overlap at a join where speech was removed, so the room tone never drops out
SNAP_SEC = 0.3    # how far a content cut may move to reach a pause
MAX_AI_CUT_SEC = 300
AI_KINDS = ("retake", "incident", "tangent", "intro", "other")
FILLERS = {"嗯", "呃", "額", "欸", "唔", "嗯嗯", "呃呃", "嗯哼"}
_PUNCT = re.compile(r"[\s，。,.!?！？…、~～\-—]+")


@dataclass
class Cut:
    start: float
    end: float
    kind: str          # silence | filler | retake | incident | tangent | intro | other
    reason: str = ""
    apply: bool = True

    @property
    def length(self) -> float:
        return self.end - self.start


# ---------------------------------------------------------------- finding cuts ---

def probe_duration(path: Path) -> float:
    exe = shutil.which("ffprobe")
    if not exe:
        raise RenderError("ffprobe not found on PATH")
    out = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1",
                          str(path)], capture_output=True, text=True, encoding="utf-8")
    try:
        return float(out.stdout.strip())
    except ValueError as error:
        raise RenderError(f"cannot read duration of {path.name}") from error


def silence_cuts(src: Path, duration: float, *, noise_db: float = SILENCE_DB, min_sec: float = SILENCE_MIN_SEC,
                 keep_sec: float = SILENCE_KEEP_SEC) -> list[Cut]:
    proc = subprocess.run([ffmpeg_path(), "-hide_banner", "-nostats", "-i", str(src), "-af",
                           f"silencedetect=noise={noise_db}dB:d={min_sec}", "-f", "null", "-"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RenderError(f"silence detection failed: {proc.stderr.strip()[-300:]}")
    starts = [float(m) for m in re.findall(r"silence_start: (-?[\d.]+)", proc.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", proc.stderr)]
    if len(ends) < len(starts):  # silence runs to the end of the file
        ends.append(duration)
    cuts = []
    for s, e in zip(starts, ends):
        s = max(s, 0.0)
        if e - s >= min_sec:
            cuts.append(Cut(s + keep_sec / 2, e - keep_sec / 2, "silence", f"{e - s:.1f}s pause"))
    return cuts


def filler_cuts(cues: list[srt.Cue]) -> list[Cut]:
    cuts = []
    for c in cues:
        if _PUNCT.sub("", c.text) in FILLERS and c.end - c.start - 2 * FILLER_TRIM > MIN_PIECE:
            cuts.append(Cut(c.start + FILLER_TRIM, c.end - FILLER_TRIM, "filler", c.text.strip()))
    return cuts


AI_PROMPT = (
    "你是 Podcast 後製剪輯師。要把這集未剪的節目整理成一整集，請標出『應該刪掉』的連續段落。\n"
    "每行格式為「行號|開始時間|文本」。只標以下情況，寧缺勿濫，內容有價值的閒聊一律保留：\n"
    "- retake：講錯後重講，刪掉講錯的那一遍（保留最後完整的一遍）\n"
    "- incident：錄音事故或與節目無關的雜務（手機鈴聲、收音測試、『再來一次』、討論要不要剪掉）\n"
    "  口頭剪輯指令（例如『這段不能用』『這邊剪掉』『這個不要放』）指的是它『前面剛講完』的那一段，"
    "不是指令本身：start 要從被點名那段的第一句開始（通常是前一個話題或前一次重講的起點），end 含這句指令；"
    "若看不出被點名的段落從哪裡開始，或只是玩笑、並非真的要剪，就不要標。reason 要寫出被點名的內容是什麼。\n"
    "- intro：正式開場前的寒暄、試音、等待。主持人／來賓的自我介紹、節目名稱、本集主題預告屬於正式內容，一律保留，不得標記\n"
    "- tangent：完全離題、對聽眾毫無價值且不影響前後理解的段落\n"
    "每項給：start / end（起訖行號，含 end 行）、kind（retake|incident|tangent|intro）、reason（全程使用{language}，不得夾雜英文，30 字內）。\n"
    f"單一段落不得超過 {MAX_AI_CUT_SEC} 秒；不確定就不要標。沒有就回傳空陣列。\n"
    '輸出格式：{{"cuts":[{{"start":0,"end":0,"kind":"retake","reason":"..."}}]}}\n'
)


def parse_ai_cuts(raw: str, cues: list[srt.Cue], first: int, last: int) -> list[Cut]:
    data = _extract_json(raw)
    items = data.get("cuts") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("response has no cuts list")
    cuts: list[Cut] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        s, e, kind = item.get("start"), item.get("end"), item.get("kind")
        if isinstance(s, bool) or isinstance(e, bool) or not isinstance(s, int) or not isinstance(e, int):
            continue
        if not first <= s <= e <= last or kind not in AI_KINDS:
            continue
        start, end = cues[s].start + AI_TRIM, cues[e].end - AI_TRIM
        if not MIN_PIECE < end - start <= MAX_AI_CUT_SEC:
            continue
        cuts.append(Cut(start, end, kind, re.sub(r"[\r\n]+", " ", str(item.get("reason") or "")).strip()[:80]))
    return cuts


def ai_cuts(cues: list[srt.Cue], backend: LLMBackend, language: str = "繁體中文") -> list[Cut]:
    cfg = Config()
    picked: list[Cut] = []
    failed = 0
    spans = windows(cues, cfg)
    for first, last in spans:
        rows = "\n".join(f"{i}|{clock(cues[i].start)}|{cues[i].spoken}" for i in range(first, last + 1))
        user = f"{AI_PROMPT.format(language=language)}<transcript>\n{rows}\n</transcript>"
        result = None
        for attempt in range(2):
            try:
                result = parse_ai_cuts(backend.complete(SYSTEM, user), cues, first, last)
                break
            except LLMError:
                break
            except ValueError as error:
                user += f"\n上一次輸出不合格：{error}。請嚴格依格式重新輸出。"
        if result is None:
            failed += 1
        else:
            picked.extend(result)
    if failed == len(spans):
        raise LLMError("the model returned no usable edit suggestions")
    return picked


# ----------------------------------------------------------------- plan files ---

def is_content(cut: Cut) -> bool:
    """Silence and filler cuts happen inside pauses; everything else removes speech and needs a softer join."""
    return cut.kind not in ("silence", "filler")


def _spans(cuts: list[Cut], duration: float) -> list[tuple[float, float, bool]]:
    """Union of the cuts that are switched on, clamped to the file; the flag says a content cut is inside."""
    raw = sorted((max(c.start, 0.0), min(c.end, duration), is_content(c)) for c in cuts if c.apply and c.end > c.start)
    merged: list[list] = []
    for s, e, content in raw:
        if e - s < MIN_PIECE:
            continue
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
            merged[-1][2] = merged[-1][2] or content
        else:
            merged.append([s, e, content])
    return [(s, e, c) for s, e, c in merged]


def merge(cuts: list[Cut], duration: float) -> list[tuple[float, float]]:
    """Union of the cuts that are switched on, clamped to the file."""
    return [(s, e) for s, e, _ in _spans(cuts, duration)]


def layout(cuts: list[Cut], duration: float) -> tuple[list[tuple[float, float]], list[tuple[float, bool]]]:
    """Kept segments plus, for each join between two of them, (end of the removed part, crossfaded?).

    A join is crossfaded when speech was removed and both neighbours are long enough to overlap.
    """
    segs: list[tuple[float, float]] = []
    joins: list[tuple[float, bool]] = []
    pos, acc = 0.0, None  # acc = (end, content) of the removal since the last kept segment
    for s, e, content in [*_spans(cuts, duration), (duration, duration, False)]:
        if s - pos >= MIN_PIECE:
            if acc is not None and segs:
                joins.append(acc)
            acc = None
            segs.append((pos, s))
        acc = (e, (acc[1] if acc else False) or content)
        pos = e
    out = []
    for i, (end, content) in enumerate(joins):
        long_enough = segs[i][1] - segs[i][0] >= 2.5 * XFADE and segs[i + 1][1] - segs[i + 1][0] >= 2.5 * XFADE
        out.append((end, content and long_enough))
    return segs, out


def _frame_levels(src: Path, start: float, length: float) -> list[float]:
    """Loudness (RMS) of consecutive 10 ms frames from start; empty when the audio cannot be read."""
    import array
    proc = subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-ss", f"{max(start, 0):.3f}",
                           "-t", f"{length:.3f}", "-i", str(src), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                          capture_output=True)
    if proc.returncode != 0:
        return []
    samples = array.array("h")
    samples.frombytes(proc.stdout[: len(proc.stdout) // 2 * 2])
    n = 80
    return [(sum(x * x for x in samples[i:i + n]) / n) ** 0.5 for i in range(0, len(samples) - n + 1, n)]


def _quietest(src: Path, t: float, duration: float) -> float:
    """The quietest moment within SNAP_SEC of t (nearest one when several are equally quiet)."""
    lo = max(t - SNAP_SEC, 0.0)
    levels = _frame_levels(src, lo, min(t + SNAP_SEC, duration) - lo)
    if not levels:
        return t
    floor = min(levels) * 1.25 + 1.0
    best = min((i for i, v in enumerate(levels) if v <= floor), key=lambda i: abs(lo + i * 0.01 + 0.005 - t))
    return lo + best * 0.01 + 0.005


def snap_cuts(src: Path, cuts: list[Cut], duration: float) -> list[Cut]:
    """Move the edges of content cuts to the nearest pause so a join does not land inside a word."""
    out = []
    for c in cuts:
        if c.apply and is_content(c):
            try:
                s, e = _quietest(src, c.start, duration), _quietest(src, c.end, duration)
            except (OSError, ValueError):
                s, e = c.start, c.end
            if e - s >= 0.5:  # never let snapping swallow the cut
                c = Cut(s, e, c.kind, c.reason, c.apply)
        out.append(c)
    return out


def kept_segments(cuts: list[Cut], duration: float) -> list[tuple[float, float]]:
    out, pos = [], 0.0
    for s, e in merge(cuts, duration):
        if s - pos >= MIN_PIECE:
            out.append((pos, s))
        pos = e
    if duration - pos >= MIN_PIECE:
        out.append((pos, duration))
    return out


def build_plan(src: Path, cues: list[srt.Cue], backend: LLMBackend | None, *, language: str = "繁體中文") -> dict[str, Any]:
    duration = probe_duration(src)
    cuts = silence_cuts(src, duration) + filler_cuts(cues)
    outline: list[dict] = []
    if backend is not None:
        cuts += ai_cuts(cues, backend, language)
        try:
            outline = episode_outline(cues, backend, language)
        except (LLMError, ValueError) as error:  # the outline is a reading aid; the plan is still usable without it
            log.warning("no outline: %s", error)
    cuts.sort(key=lambda c: c.start)
    return {"version": 1, "source": str(src.resolve()), "duration": duration, "outline": outline,
            "cuts": [asdict(c) for c in cuts]}


def _excerpt(cues: list[srt.Cue], start: float, end: float, limit: int = 40) -> str:
    text = " ".join(c.text for c in cues if c.end > start and c.start < end)
    return (text[:limit] + "…") if len(text) > limit else text


def plan_markdown(plan: dict[str, Any], cues: list[srt.Cue]) -> str:
    cuts = plan["cuts"]
    removed: dict[str, float] = {}
    for c in cuts:
        removed[c["kind"]] = removed.get(c["kind"], 0) + c["end"] - c["start"]
    total = sum(removed.values())
    lines = [f"# 剪輯清單：{Path(plan['source']).name}", "",
             f"原長 {plan['duration'] / 60:.1f} 分，預計剪掉約 {total / 60:.1f} 分（重疊處已重複計算，實際以渲染為準）。",
             "把 plan.json 裡不想剪的項目 `\"apply\"` 改成 `false`，再執行 edit-render。", "",
             *([ "## 段落大綱（原音檔時間）", "", *[f"- {clock(o['start'])} {o['topic']}" for o in plan.get("outline", [])], ""]
               if plan.get("outline") else []),
             "| 類型 | 總長 |", "|---|---|", *[f"| {k} | {v / 60:.1f} 分 |" for k, v in sorted(removed.items())], "",
             "| # | 時間 | 長度 | 類型 | 說明 | 逐字稿 |", "|---|---|---|---|---|---|"]
    for i, c in enumerate(cuts):
        if c["kind"] == "silence" and c["end"] - c["start"] < 3:
            continue  # short pauses would drown the list; they are still in plan.json
        lines.append(f"| {i} | {clock(c['start'])}–{clock(c['end'])} | {c['end'] - c['start']:.1f}s | {c['kind']} | "
                     f"{c['reason'].replace('|', '/')} | {_excerpt(cues, c['start'], c['end']).replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def write_plan(plan: dict[str, Any], cues: list[srt.Cue], folder: Path) -> tuple[Path, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "plan.md").write_text(plan_markdown(plan, cues), encoding="utf-8")
    return folder / "plan.json", folder / "plan.md"


def read_plan(path: Path) -> tuple[Path, float, list[Cut]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("cuts"), list):
        raise ValueError("not a podclip plan")
    cuts = []
    for item in data["cuts"]:
        try:
            cuts.append(Cut(float(item["start"]), float(item["end"]), str(item["kind"]), str(item.get("reason", "")),
                            bool(item.get("apply", True))))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"bad cut entry: {item!r}") from error
    src = Path(data["source"])
    if not src.is_file():
        raise ValueError(f"source file not found: {src}")
    return src, float(data["duration"]), cuts


# ------------------------------------------------------------------- render ---

def remap_cues(cues: list[srt.Cue], cuts: list[Cut], duration: float) -> list[srt.Cue]:
    removed = merge(cuts, duration)
    overlaps = [end for end, crossfaded in layout(cuts, duration)[1] if crossfaded]  # each overlap shortens the audio

    def new_time(t: float) -> float:
        return t - sum(min(max(t - s, 0.0), e - s) for s, e in removed) - XFADE * sum(1 for end in overlaps if end <= t)

    out = []
    for c in cues:
        start, end = new_time(c.start), new_time(c.end)
        if end - start >= MIN_PIECE:
            out.append(replace(c, start=start, end=end))
    return out


def render(src: Path, duration: float, cuts: list[Cut], out: Path, *, loudnorm: bool = True) -> tuple[Path, float]:
    """Returns (output path, new duration)."""
    segments, joins = layout(cuts, duration)
    if not segments:
        raise RenderError("every part of the episode is cut")
    crossfaded = [xf for _, xf in joins]
    parts = []
    for i, (a, b) in enumerate(segments):
        fade = min(FADE, (b - a) / 3)
        fades = []  # an edge that is crossfaded with its neighbour must not also dip to silence
        if i == 0 or not crossfaded[i - 1]:
            fades.append(f"afade=t=in:d={fade:.3f}")
        if i == len(segments) - 1 or not crossfaded[i]:
            fades.append(f"afade=t=out:st={b - a - fade:.3f}:d={fade:.3f}")
        parts.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS" + "".join("," + f for f in fades) + f"[s{i}]")
    chunks: list[list[int]] = [[0]]  # runs of segments joined with plain fades; chunks meet through crossfades
    for i in range(1, len(segments)):
        if crossfaded[i - 1]:
            chunks.append([i])
        else:
            chunks[-1].append(i)
    for j, members in enumerate(chunks):
        parts.append("".join(f"[s{i}]" for i in members) + (f"concat=n={len(members)}:v=0:a=1[c{j}]" if len(members) > 1
                                                          else f"anull[c{j}]"))
    current = "c0"
    for j in range(1, len(chunks)):
        parts.append(f"[{current}][c{j}]acrossfade=d={XFADE}:c1=qsin:c2=qsin[x{j}]")
        current = f"x{j}"
    tail = ",loudnorm=I=-16:TP=-1.5:LRA=11" if loudnorm else ""
    graph = ";".join(parts) + f";[{current}]anull{tail}[a]"
    codec = {".mp3": ["-c:a", "libmp3lame", "-q:a", "2"], ".m4a": ["-c:a", "aac", "-b:a", "128k"],
             ".wav": ["-c:a", "pcm_s16le"]}.get(out.suffix.lower())
    if codec is None:
        raise RenderError("output must be .mp3, .m4a or .wav")
    out.parent.mkdir(parents=True, exist_ok=True)
    script = out.parent / f".{out.stem}.filter.txt"
    script.write_text(graph, encoding="utf-8")  # a long graph would overflow the Windows command line
    try:
        proc = subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                               "-filter_complex_script", str(script), "-map", "[a]", *codec, str(out)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
    finally:
        script.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RenderError(f"ffmpeg failed: {proc.stderr.strip()[-400:]}")
    return out, sum(b - a for a, b in segments) - XFADE * sum(crossfaded)
