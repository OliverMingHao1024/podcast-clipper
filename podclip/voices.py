"""Remembered voices: a name plus a few "voice vectors", so a person is recognised again in the next episode.

A voice vector is a list of numbers the speaker model computes from some seconds of speech; it cannot be turned
back into audio, but it identifies a person, so treat the file like personal data: it stays on this computer
(``podclip-work/voices.json``, never committed), and the page can list, export, import and delete it.
Vectors from a different speaker model are ignored, never mixed.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import time
from pathlib import Path

from . import diarize

VERSION = 1
MAX_SAMPLES = 10  # vectors kept per person; the newest replace the oldest
MAX_PEOPLE = 50
MAX_BYTES = 5 * 1024 * 1024
_LOCK = threading.Lock()


def path() -> Path:
    return Path(os.environ.get("PODCLIP_VOICES") or "podclip-work/voices.json").expanduser()


def _model_id() -> str:
    return diarize.EMBEDDING["sha256"][:12]


def _empty() -> dict:
    return {"version": VERSION, "model": _model_id(), "voices": {}}


def _valid_vector(vec: object, dim: int | None = None) -> bool:
    return (isinstance(vec, list) and 16 <= len(vec) <= 1024 and (dim is None or len(vec) == dim)
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in vec))


def _clean(data: object) -> dict:
    """Keep only well-formed people (a usable name and 1+ same-length vectors); anything else is dropped."""
    out = _empty()
    if not isinstance(data, dict) or data.get("version") != VERSION or data.get("model") != _model_id():
        return out
    people = data.get("voices")
    for who, entry in (people.items() if isinstance(people, dict) else []):
        name = diarize.clean_name(who)
        samples = entry.get("samples") if isinstance(entry, dict) else None
        if not name or name != who or not isinstance(samples, list) or len(out["voices"]) >= MAX_PEOPLE:
            continue
        dim = len(samples[0]) if samples and isinstance(samples[0], list) else None
        good = [s for s in samples if _valid_vector(s, dim)][-MAX_SAMPLES:]
        if good:
            out["voices"][name] = {"samples": good, "updated": float(entry.get("updated") or 0)}
    return out


def load(where: Path | None = None) -> dict:
    where = Path(where) if where else path()
    try:
        if where.stat().st_size > MAX_BYTES:
            return _empty()
        return _clean(json.loads(where.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return _empty()


def _save(data: dict, where: Path) -> None:
    where.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=where.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(tmp, where)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def people(where: Path | None = None) -> list[dict]:
    """[{name, samples}] for the page's list; never the vectors themselves."""
    return [{"name": n, "samples": len(v["samples"])} for n, v in sorted(load(where)["voices"].items())]


def known(where: Path | None = None) -> dict:
    """{name: unit-length average vector} for matching."""
    import numpy as np
    out = {}
    for name, entry in load(where)["voices"].items():
        mean = np.mean(np.array(entry["samples"], dtype=np.float32), axis=0)
        norm = float(np.linalg.norm(mean))
        if norm > 0:
            out[name] = mean / norm
    return out


def enroll(name: str, vector, where: Path | None = None) -> str:
    """Remember one more voice vector for name; returns the cleaned name. Existing vectors are kept."""
    where = Path(where) if where else path()
    clean = diarize.clean_name(name)
    vec = [round(float(x), 5) for x in vector]
    if not clean or not _valid_vector(vec):
        raise ValueError("cannot remember this voice: bad name or vector")
    with _LOCK:
        data = load(where)
        entry = data["voices"].get(clean)
        if entry is None and len(data["voices"]) >= MAX_PEOPLE:
            raise ValueError(f"at most {MAX_PEOPLE} people can be remembered")
        if entry and len(entry["samples"][0]) != len(vec):
            raise ValueError("this voice does not fit the ones already stored under that name")
        samples = (entry["samples"] if entry else []) + [vec]
        data["voices"][clean] = {"samples": samples[-MAX_SAMPLES:], "updated": time.time()}
        _save(data, where)
    return clean


def forget(name: str, where: Path | None = None) -> bool:
    where = Path(where) if where else path()
    with _LOCK:
        data = load(where)
        if name not in data["voices"]:
            return False
        del data["voices"][name]
        _save(data, where)
    return True


def export_text(where: Path | None = None) -> str:
    return json.dumps(load(where), ensure_ascii=False)


def import_text(text: str, where: Path | None = None) -> int:
    """Merge an exported file into this computer's store (vectors of a name already here are added to it).
    Returns how many people the file contributed; a file that is not a valid export raises ValueError."""
    where = Path(where) if where else path()
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("the file is too large")
    try:
        raw = json.loads(text)
    except ValueError as error:
        raise ValueError("this is not a voice file exported by podclip") from error
    incoming = _clean(raw)
    if not incoming["voices"]:
        raise ValueError("no usable voices in this file (it may come from a different speaker model)")
    with _LOCK:
        data = load(where)
        for name, entry in incoming["voices"].items():
            have = data["voices"].get(name)
            if have is None and len(data["voices"]) >= MAX_PEOPLE:
                continue
            if have and len(have["samples"][0]) != len(entry["samples"][0]):
                continue
            samples = (have["samples"] if have else []) + entry["samples"]
            data["voices"][name] = {"samples": samples[-MAX_SAMPLES:], "updated": time.time()}
        _save(data, where)
    return len(incoming["voices"])


def add_from_audio(audio: Path, name: str, where: Path | None = None) -> int:
    """Remember a person from a recording of only them. Returns the seconds of speech used; ValueError says what is wrong."""
    clean = diarize.clean_name(name)
    if not clean:
        raise ValueError("type a name of 1-20 characters, without 【 or 】")
    diarize.require()
    try:
        vec, seconds = diarize.voice_from_recording(diarize._samples(Path(audio)), diarize._embedder())
    except RuntimeError as error:  # the file could not be decoded
        raise ValueError(f"cannot read this audio: {error}") from error
    enroll(clean, vec, where)
    return round(seconds)


def remember(audio: Path, cues: list, mapping: dict, where: Path | None = None) -> dict:
    """Remember the voices of speakers found in cues: mapping is {label in cues: name to store it under}.
    Returns {name: True when stored, False when that speaker has too little speech (about 18 s) to learn from}."""
    diarize.require()
    samples = diarize._samples(Path(audio))
    embed = diarize._embedder()
    result = {}
    for label, name in mapping.items():
        clean = diarize.clean_name(name)
        if not clean:
            continue
        vec = diarize.voice_sample(samples, cues, label, embed)
        if vec is None:
            result[clean] = False
            continue
        enroll(clean, vec, where)
        result[clean] = True
    return result
