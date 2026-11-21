"""Optional "who is speaking" labels (pip install -e .[speakers]), done on this computer with sherpa-onnx.

Two small public models are downloaded once into the models folder (~46 MB, hashes pinned below): pyannote's
segmentation model (MIT) finds the speech turns and a 3D-Speaker embedding model (Apache-2.0) tells voices apart.
No account or token is needed and the audio never leaves the computer.

The number of people has to be given: letting the clustering guess it split one voice into dozens of speakers on
real episodes, while a given count (2 or 3) produced plausible turns. Labels are "講者1", "講者2" ... in order of
first appearance; the page lets the user rename them afterwards. How accurate the turns are on a given episode is
not measured here: overlapping talk and laughter get misassigned, so treat the labels as a draft.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from importlib.util import find_spec
from pathlib import Path

from .srt import Cue

MIN_SPEAKERS, MAX_SPEAKERS = 2, 8
_BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SEGMENTATION = {
    "url": f"{_BASE}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
    "sha256": "24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488",
    "member": "sherpa-onnx-pyannote-segmentation-3-0/model.onnx", "name": "segmentation-pyannote-3.0.onnx"}
EMBEDDING = {
    "url": f"{_BASE}/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
    "sha256": "f1ee61be04000b50392a63442e5dd9feaea7e81dddd494d3647cf1c3d88a1498",
    "member": None, "name": "embedding-3dspeaker-eres2net-zh.onnx"}
LABEL = "講者"
ISOLATED_SEC = 1.0  # a cue this short, between two cues of one other speaker, is taken as a mislabel


def available() -> bool:
    return find_spec("sherpa_onnx") is not None and find_spec("numpy") is not None


def require() -> None:
    if not available():
        raise RuntimeError("speaker labels need sherpa-onnx; run: pip install -e .[speakers]")


def check_count(speakers: int) -> int:
    if isinstance(speakers, bool) or not isinstance(speakers, int) or not MIN_SPEAKERS <= speakers <= MAX_SPEAKERS:
        raise ValueError(f"the number of speakers must be {MIN_SPEAKERS}-{MAX_SPEAKERS}")
    return speakers


def model_dir() -> Path:
    return Path(os.environ.get("PODCLIP_MODELS") or "podclip-work/models").expanduser()


def _fetch(url: str, sha256: str, member: str | None, target: Path) -> None:
    """Download url, check its hash, and write the model (or the one member of the archive) atomically."""
    print(f"downloading speaker model {target.name}...", file=sys.stderr, flush=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        raw, digest = Path(tmp) / "download", hashlib.sha256()
        with urllib.request.urlopen(url, timeout=60) as resp, raw.open("wb") as fh:  # noqa: S310 - fixed https URL
            while chunk := resp.read(1 << 20):
                digest.update(chunk)
                fh.write(chunk)
        if digest.hexdigest() != sha256:
            raise RuntimeError(f"the downloaded {target.name} does not match the expected hash; try again later")
        if member:
            try:
                with tarfile.open(raw, "r:bz2") as tar, tar.extractfile(member) as src:  # one named member, no extraction paths
                    part = Path(tmp) / "member"
                    part.write_bytes(src.read())
            except (KeyError, AttributeError, tarfile.TarError) as error:
                raise RuntimeError(f"the downloaded {target.name} archive is not as expected") from error
            raw = part
        raw.replace(target)


def ensure_models(folder: Path | None = None) -> tuple[Path, Path]:
    folder = Path(folder) if folder else model_dir()
    paths = []
    for spec in (SEGMENTATION, EMBEDDING):
        path = folder / spec["name"]
        if not path.is_file():
            try:
                _fetch(spec["url"], spec["sha256"], spec["member"], path)
            except OSError as error:
                raise RuntimeError(f"could not download the speaker model ({error}); check the internet connection") from error
        paths.append(path)
    return paths[0], paths[1]


def _samples(audio: Path):
    import numpy as np
    proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                          capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        reason = proc.stderr.decode("utf-8", errors="replace").strip()[-200:]
        raise RuntimeError(f"ffmpeg could not decode the audio for speaker labelling: {reason}")
    return np.frombuffer(proc.stdout, dtype="<i2").astype(np.float32) / 32768.0


def turns_for(audio: Path, speakers: int) -> list[tuple[float, float, int]]:
    """(start, end, speaker index) turns for the whole file, sorted by start."""
    check_count(speakers)
    require()
    import sherpa_onnx as so
    seg_model, emb_model = ensure_models()
    threads = max(1, min(4, os.cpu_count() or 1))
    config = so.OfflineSpeakerDiarizationConfig(
        segmentation=so.OfflineSpeakerSegmentationModelConfig(
            pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(seg_model)), num_threads=threads),
        embedding=so.SpeakerEmbeddingExtractorConfig(model=str(emb_model), num_threads=threads),
        clustering=so.FastClusteringConfig(num_clusters=speakers),
        min_duration_on=0.3, min_duration_off=0.5)
    if not config.validate():
        raise RuntimeError("the speaker models could not be loaded; delete the models folder to download them again")
    engine = so.OfflineSpeakerDiarization(config)
    samples, last = _samples(audio), [-1]

    def progress(done: int, total: int) -> int:
        pct = int(100 * done / total) // 10 * 10 if total else 0
        if pct > last[0]:
            last[0] = pct
            print(f"identifying speakers... {min(pct, 100)}%", file=sys.stderr, flush=True)
        return 0

    result = engine.process(samples, callback=progress).sort_by_start_time()
    return [(s.start, s.end, s.speaker) for s in result]


def label(cues: list[Cue], turns: list[tuple[float, float, int]]) -> list[Cue]:
    """Give every cue the speaker who talks most during it, named 講者1.. by order of first appearance."""
    picked: list[int | None] = []
    for c in cues:
        spent: dict[int, float] = {}
        for start, end, who in turns:
            if start >= c.end:
                break  # turns are sorted by start
            overlap = min(end, c.end) - max(start, c.start)
            if overlap > 0:
                spent[who] = spent.get(who, 0.0) + overlap
        picked.append(max(spent, key=spent.get) if spent else None)
    for i, c in enumerate(cues):  # no speech found under this cue: use the nearest turn within 1 s
        if picked[i] is None and turns:
            gap, who = min((max(s - c.end, c.start - e, 0.0), w) for s, e, w in turns)
            picked[i] = who if gap <= 1.0 else None
    for i in range(1, len(cues) - 1):  # one very short cue wedged between two cues of the same other speaker
        before, after = picked[i - 1], picked[i + 1]
        if before is not None and before == after != picked[i] and cues[i].end - cues[i].start < ISOLATED_SEC:
            picked[i] = before
    names: dict[int, str] = {}
    out = []
    for c, who in zip(cues, picked):
        if who is None:
            out.append(Cue(c.start, c.end, c.text, ""))
            continue
        names.setdefault(who, f"{LABEL}{len(names) + 1}")
        out.append(Cue(c.start, c.end, c.text, names[who]))
    return out


def label_cues(audio: Path, cues: list[Cue], speakers: int) -> list[Cue]:
    return label(cues, turns_for(audio, speakers))


def summarize(cues: list[Cue], samples: int = 2) -> list[dict]:
    """Per speaker: label, seconds of speech and a few example lines, for the page's rename form."""
    info: dict[str, dict] = {}
    for c in cues:
        if not c.speaker:
            continue
        row = info.setdefault(c.speaker, {"label": c.speaker, "seconds": 0.0, "samples": []})
        row["seconds"] += c.end - c.start
        if len(row["samples"]) < samples and len(c.text) >= 8:
            row["samples"].append(c.text[:40])
    return sorted(info.values(), key=lambda r: r["label"])


def clean_name(name: object) -> str:
    """A name typed by the user, or "" when it is unusable (the label then stays as it was)."""
    if not isinstance(name, str):
        return ""
    name = " ".join(name.split())
    return "" if not 1 <= len(name) <= 20 or "【" in name or "】" in name else name


def rename(cues: list[Cue], names: dict) -> list[Cue]:
    """Apply {old label: new name} to every cue at once (so swapping two names works)."""
    fixed = {old: clean_name(new) for old, new in names.items() if isinstance(old, str)}
    return [Cue(c.start, c.end, c.text, fixed.get(c.speaker) or c.speaker) for c in cues]
