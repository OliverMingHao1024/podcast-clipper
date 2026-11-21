"""Minimal SRT reader/writer. No third-party dependency."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MAX_SRT_BYTES = 5 * 1024 * 1024
_TIME = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")
_SPEAKER = re.compile(r"^【([^【】]{1,20})】\s*")  # "【小明】text": the speaker label, when a file has one


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str
    speaker: str = ""

    @property
    def spoken(self) -> str:
        """The line as the model should read it: "name：text" when the speaker is known."""
        return f"{self.speaker}：{self.text}" if self.speaker else self.text


EDITED_STEM = "episode_edited"  # what `edit-render` names its output; its subtitles use the edited timeline


def source_subtitles(folder: Path) -> Path | None:
    """The subtitles of the ORIGINAL audio in a run's output folder: the top-level .srt that is not the edited
    episode's. Picking the first file by name is wrong when the audio's name sorts after "episode_edited"
    (any Chinese file name does), because the edited file's times no longer match the original audio."""
    found = sorted(Path(folder).glob("*.srt"))
    originals = [p for p in found if not p.stem.startswith(EDITED_STEM)]
    return (originals or found or [None])[0]


def to_seconds(stamp: str) -> float:
    m = _TIME.fullmatch(stamp.strip())
    if not m:
        raise ValueError(f"bad SRT timestamp: {stamp!r}")
    h, mi, s, ms = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def to_stamp(sec: float) -> str:
    ms = round(max(sec, 0.0) * 1000)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


LABELLED_SHARE, MAX_LABELS = 0.75, 12


def parse(text: str) -> list[Cue]:
    """Cues from SRT text. A leading 【name】 is a speaker label only when the file looks labelled: at least three
    quarters of the cues carry one (the tool leaves only cues with no speech unlabelled) and there are at most 12
    different names. Otherwise it is ordinary text, because subtitle files often open lines with tags such as
    【笑】 or 【本集重點】, and those must not turn into speakers."""
    cues: list[Cue] = []
    for block in re.split(r"\r?\n\s*\r?\n", text.strip().lstrip("﻿")):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        arrow = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if arrow is None:
            continue
        left, right = lines[arrow].split("-->", 1)
        try:
            start, end = to_seconds(left), to_seconds(right.split()[0])
        except (ValueError, IndexError):
            continue
        body = " ".join(ln.strip() for ln in lines[arrow + 1:]).strip()
        if body and end > start:
            cues.append(Cue(start, end, body))
    tagged = [(c, _SPEAKER.match(c.text)) for c in cues]
    tagged = [(c, m) for c, m in tagged if m and c.text[m.end():].strip()]
    if tagged and len(tagged) >= LABELLED_SHARE * len(cues) and len({m[1].strip() for _, m in tagged}) <= MAX_LABELS:
        split = {id(c): (c.text[m.end():].strip(), m[1].strip()) for c, m in tagged}
        cues = [Cue(c.start, c.end, *split[id(c)]) if id(c) in split else c for c in cues]
    cues.sort(key=lambda c: c.start)
    return cues


def read(path: Path) -> list[Cue]:
    path = Path(path)
    if path.stat().st_size > MAX_SRT_BYTES:
        raise ValueError(f"subtitle file larger than {MAX_SRT_BYTES} bytes")
    cues = parse(path.read_text(encoding="utf-8-sig", errors="replace"))
    if not cues:
        raise ValueError("subtitle file has no usable cues")
    return cues


def write(path: Path, cues: list[Cue], *, offset: float = 0.0, labels: bool = True) -> None:
    out = []
    for n, c in enumerate(cues, 1):
        label = f"【{c.speaker}】" if c.speaker and labels else ""
        out.append(f"{n}\n{to_stamp(c.start - offset)} --> {to_stamp(c.end - offset)}\n{label}{c.text}\n")
    Path(path).write_text("\n".join(out), encoding="utf-8")
