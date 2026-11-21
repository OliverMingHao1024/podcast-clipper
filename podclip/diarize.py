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
# Second look with voices. The turns decide who talks most under a cue, but short interjections ("嗯對", "Pobby")
# laid over a long speech are often missed by them. Each cue's own audio is compared with every speaker's average
# voice, and the label changes only when another speaker is clearly closer. On 37 hand-corrected cues this fixed
# 3 of 4 wrong labels and broke none (cosine similarities: the right voice 0.4-0.8, the others mostly below 0.3);
# the numbers were chosen on that small sample, so they are conservative on purpose.
MIN_EMBED_SEC = 0.6  # shorter cues give unreliable voice features
OVERRIDE_MIN, OVERRIDE_MARGIN = 0.35, 0.3  # the new speaker must be at least this similar and this much closer
CENTROID_CHUNK_SEC, MIN_CHUNKS, MAX_CHUNKS = 6.0, 4, 60
# Remembered voices (voices.py). A cue is named when its voice is clearly one known person: at least KNOWN_MIN
# similar (0.5 when only one person is known, since there is nobody to compare with) and KNOWN_MARGIN ahead of the
# next known person. Cues that stay unsure keep their 講者N, unless almost every sure cue of their cluster agrees
# on one person. Measured only on small hand-checked samples: 36/37 cues (leave-one-region-out on one episode) and
# 24/24 confident turns on a second episode, so the numbers are conservative.
KNOWN_MIN, KNOWN_MIN_ALONE, KNOWN_MARGIN = 0.40, 0.50, 0.15
CLUSTER_SHARE, CLUSTER_MIN_CUES = 0.85, 8


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


def turns_for(audio: Path, speakers: int, samples=None) -> list[tuple[float, float, int]]:
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
    samples = _samples(audio) if samples is None else samples
    last = [-1]

    def progress(done: int, total: int) -> int:
        pct = int(100 * done / total) // 10 * 10 if total else 0
        if pct > last[0]:
            last[0] = pct
            print(f"identifying speakers... {min(pct, 100)}%", file=sys.stderr, flush=True)
        return 0

    result = engine.process(samples, callback=progress).sort_by_start_time()
    return [(s.start, s.end, s.speaker) for s in result]


def pick(cues: list[Cue], turns: list[tuple[float, float, int]]) -> list[int | None]:
    """The speaker who talks most during each cue (None when nobody does)."""
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
    return picked


def name(cues: list[Cue], picked: list) -> list[Cue]:
    """Name speaker numbers 講者1.. by order of first appearance; a picked value that is already a name is kept."""
    names: dict[int, str] = {}
    out = []
    for c, who in zip(cues, picked):
        if who is None:
            out.append(Cue(c.start, c.end, c.text, ""))
        elif isinstance(who, str):
            out.append(Cue(c.start, c.end, c.text, who))
        else:
            names.setdefault(who, f"{LABEL}{len(names) + 1}")
            out.append(Cue(c.start, c.end, c.text, names[who]))
    return out


def label(cues: list[Cue], turns: list[tuple[float, float, int]]) -> list[Cue]:
    """Label cues from the turns alone, named 講者1.. by order of first appearance."""
    return name(cues, pick(cues, turns))


def _embedder():
    """A function: audio samples -> unit-length voice vector (the same model the diarization uses)."""
    import numpy as np
    import sherpa_onnx as so
    extractor = so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(
        model=str(ensure_models()[1]), num_threads=max(1, min(4, os.cpu_count() or 1))))

    def embed(samples):
        stream = extractor.create_stream()
        stream.accept_waveform(16000, samples)
        stream.input_finished()
        vec = np.array(extractor.compute(stream), dtype=np.float32)
        return vec / np.linalg.norm(vec)
    return embed


def centroids(samples, turns: list[tuple[float, float, int]], embed) -> dict:
    """Average voice per speaker, from speech that nobody else is talking over. Speakers with too little are left out."""
    import numpy as np
    spans: dict[int, list[tuple[float, float]]] = {}
    for start, end, who in turns:
        if end - start >= 1.0 and not any(min(end, e) - max(start, s) > 0 for s, e, w in turns if w != who):
            spans.setdefault(who, []).append((start, end))
    out = {}
    for who, parts in spans.items():
        mean = _mean_voice(np.concatenate([samples[int(a * 16000):int(b * 16000)] for a, b in parts]), embed)
        if mean is not None:
            out[who] = mean
    return out


def _mean_voice(speech, embed, min_chunks: int = MIN_CHUNKS):
    """Average voice vector of some seconds of speech (6 s pieces, at most 60 of them), None when there is too little."""
    import numpy as np
    size = int(CENTROID_CHUNK_SEC * 16000)
    chunks = [speech[i:i + size] for i in range(0, len(speech) - size + 1, size)]
    if len(chunks) < min_chunks:
        return None
    mean = np.mean([embed(c) for c in chunks[::max(1, len(chunks) // MAX_CHUNKS)]], axis=0)
    return mean / np.linalg.norm(mean)


def voice_sample(samples, cues: list[Cue], who: str, embed):
    """A voice vector for the speaker labelled `who`, from their own cues of at least 1 s (None if under ~18 s)."""
    import numpy as np
    spans = [(c.start, c.end) for c in cues if c.speaker == who and c.end - c.start >= 1.0]
    if not spans:
        return None
    return _mean_voice(np.concatenate([samples[int(a * 16000):int(b * 16000)] for a, b in spans]), embed, min_chunks=3)


def cue_vectors(cues: list[Cue], samples, embed) -> list:
    """One voice vector per cue (None for cues shorter than MIN_EMBED_SEC)."""
    return [embed(samples[int(c.start * 16000):int(c.end * 16000)]) if c.end - c.start >= MIN_EMBED_SEC else None
            for c in cues]


def refine(cues: list[Cue], picked: list[int | None], turns, samples, embed, vectors=None) -> tuple[list[int | None], int]:
    """Change a cue's speaker when its own audio is clearly closer to another speaker's voice. Returns (picked, changes)."""
    known = centroids(samples, turns, embed)
    if len(known) < 2:
        return picked, 0
    out, changed = list(picked), 0
    for i, c in enumerate(cues):
        current = picked[i]
        if current not in known or c.end - c.start < MIN_EMBED_SEC:
            continue
        voice = vectors[i] if vectors is not None else embed(samples[int(c.start * 16000):int(c.end * 16000)])
        sims = {who: float(voice @ vec) for who, vec in known.items()}
        best = max(sims, key=sims.get)
        if best != current and sims[best] >= OVERRIDE_MIN and sims[best] - sims[current] >= OVERRIDE_MARGIN:
            out[i], changed = best, changed + 1
    return out, changed


def match_known(picked: list, vectors: list, known: dict) -> tuple[list, int]:
    """Name cues whose voice is clearly one remembered person. Returns (picked, number of cues named)."""
    if not known:
        return picked, 0
    names, need = list(known), (KNOWN_MIN if len(known) > 1 else KNOWN_MIN_ALONE)
    out, named = list(picked), 0
    for i, vec in enumerate(vectors):
        if vec is None:
            continue
        sims = sorted(((float(vec @ known[n]), n) for n in names), reverse=True)
        second = sims[1][0] if len(sims) > 1 else -1.0
        if sims[0][0] >= need and sims[0][0] - second >= KNOWN_MARGIN:
            out[i], named = sims[0][1], named + 1
    for who in {p for p in picked if isinstance(p, int)}:  # a cluster whose sure cues agree: name its unsure cues too
        sure = [out[i] for i, p in enumerate(picked) if p == who and isinstance(out[i], str)]
        if len(sure) >= CLUSTER_MIN_CUES:
            top = max(set(sure), key=sure.count)
            if sure.count(top) / len(sure) >= CLUSTER_SHARE:
                for i, p in enumerate(picked):
                    if p == who and not isinstance(out[i], str):
                        out[i], named = top, named + 1
    return out, named


def label_cues(audio: Path, cues: list[Cue], speakers: int, known: dict | None = None) -> list[Cue]:
    """Speaker labels for cues: turns, a voice check, then remembered voices (known; the voices file when None)."""
    samples = _samples(audio)
    turns = turns_for(audio, speakers, samples)
    picked = pick(cues, turns)
    try:
        embed = _embedder()
        vectors = cue_vectors(cues, samples, embed)
        picked, changed = refine(cues, picked, turns, samples, embed, vectors)
        print(f"voice check: {changed} short lines moved to a closer voice", file=sys.stderr, flush=True)
        if known is None:
            from . import voices
            known = voices.known()
        picked, named = match_known(picked, vectors, known)
        if known:
            print(f"remembered voices: {len(known)} known, {named} lines named", file=sys.stderr, flush=True)
    except Exception as error:  # noqa: BLE001 - this second look is optional; keep the turn-based labels
        print(f"warning: voice check skipped: {error}", file=sys.stderr)
    return name(cues, picked)


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
