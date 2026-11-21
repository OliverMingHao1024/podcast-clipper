import bz2
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
from dataclasses import replace

import pytest

from podclip import diarize, srt
from podclip.cli import main
from podclip.srt import Cue

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg missing")


def cues(*spans):
    return [Cue(a, b, f"第{i}句講話內容") for i, (a, b) in enumerate(spans)]


# --------------------------------------------------------------------- labelling ---

def test_label_picks_the_speaker_with_most_overlap_and_names_by_first_appearance():
    c = cues((0, 4), (4, 8), (8, 12))
    turns = [(0, 4, 7), (4, 5, 7), (5, 8, 2), (8, 12, 7)]  # raw ids 7 and 2: the first heard is 講者1
    assert [x.speaker for x in diarize.label(c, turns)] == ["講者1", "講者2", "講者1"]


def test_label_keeps_text_and_times():
    c = cues((0, 4))
    out = diarize.label(c, [(0, 4, 0)])
    assert (out[0].start, out[0].end, out[0].text) == (0, 4, c[0].text)


def test_cue_without_speech_takes_a_turn_within_a_second_else_stays_unlabelled():
    c = cues((0, 3), (3.5, 4.5), (20, 22))
    turns = [(0, 3, 1)]
    out = diarize.label(c, turns)
    assert [x.speaker for x in out] == ["講者1", "講者1", ""]  # 0.5 s away is close enough, 17 s away is not


def test_isolated_short_cue_follows_its_neighbours():
    c = cues((0, 6), (6, 6.6), (6.6, 12))
    turns = [(0, 6, 0), (6, 6.6, 1), (6.6, 12, 0)]
    assert [x.speaker for x in diarize.label(c, turns)] == ["講者1", "講者1", "講者1"]
    long_middle = cues((0, 6), (6, 9), (9, 12))  # a real 3 s interjection stays
    assert [x.speaker for x in diarize.label(long_middle, [(0, 6, 0), (6, 9, 1), (9, 12, 0)])] == ["講者1", "講者2", "講者1"]


def test_label_with_no_turns_labels_nothing():
    assert [x.speaker for x in diarize.label(cues((0, 3)), [])] == [""]


def test_check_count_bounds():
    assert diarize.check_count(3) == 3
    for bad in (0, 1, 9, True, 2.5, "3"):
        with pytest.raises(ValueError):
            diarize.check_count(bad)


# ----------------------------------------------------------------- srt and names ---

def test_srt_keeps_speaker_labels_and_can_leave_them_out(tmp_path):
    c = [Cue(0, 2, "你好", "小明"), Cue(2, 4, "沒有標籤")]
    srt.write(tmp_path / "a.srt", c)
    assert "【小明】你好" in (tmp_path / "a.srt").read_text(encoding="utf-8")
    assert srt.read(tmp_path / "a.srt") == c
    srt.write(tmp_path / "b.srt", c, labels=False)
    assert "【" not in (tmp_path / "b.srt").read_text(encoding="utf-8")
    assert [x.speaker for x in srt.read(tmp_path / "b.srt")] == ["", ""]


def test_a_bracket_only_line_is_not_a_speaker():
    parsed = srt.parse("1\n00:00:00,000 --> 00:00:02,000\n【笑】\n")
    assert parsed == [Cue(0, 2, "【笑】")]


def test_spoken_line_for_the_model():
    assert Cue(0, 1, "好", "小明").spoken == "小明：好" and Cue(0, 1, "好").spoken == "好"


def test_rename_applies_all_at_once_so_names_can_swap():
    c = [Cue(0, 1, "a", "講者1"), Cue(1, 2, "b", "講者2"), Cue(2, 3, "c")]
    out = diarize.rename(c, {"講者1": "講者2", "講者2": "講者1"})
    assert [x.speaker for x in out] == ["講者2", "講者1", ""]


def test_unusable_names_keep_the_label():
    c = [Cue(0, 1, "a", "講者1")]
    for bad in ("", "   ", "x" * 21, "含【括號】", 5, None):
        assert diarize.rename(c, {"講者1": bad})[0].speaker == "講者1"
    assert diarize.rename(c, {"講者1": "  小  明 "})[0].speaker == "小 明"


def test_summarize_gives_minutes_and_example_lines():
    c = [Cue(0, 60, "這是一句夠長的範例句子", "講者1"), Cue(60, 90, "短", "講者2"), Cue(90, 150, "另一句夠長的範例句子呢", "講者1")]
    rows = diarize.summarize(c)
    assert [(r["label"], r["seconds"]) for r in rows] == [("講者1", 120), ("講者2", 30)]
    assert rows[0]["samples"] and rows[1]["samples"] == []


# ----------------------------------------------------------------------- models ---

def _archive(member: str, payload: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(member)
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    return bz2.compress(buf.getvalue())


def test_fetch_checks_the_hash_and_extracts_only_the_named_member(tmp_path):
    blob = _archive("pkg/model.onnx", b"MODEL")
    src = tmp_path / "pkg.tar.bz2"
    src.write_bytes(blob)
    target = tmp_path / "models" / "seg.onnx"
    diarize._fetch(src.as_uri(), hashlib.sha256(blob).hexdigest(), "pkg/model.onnx", target)
    assert target.read_bytes() == b"MODEL"
    with pytest.raises(RuntimeError, match="hash"):
        diarize._fetch(src.as_uri(), "0" * 64, "pkg/model.onnx", tmp_path / "models" / "bad.onnx")
    assert not (tmp_path / "models" / "bad.onnx").exists()
    with pytest.raises(RuntimeError, match="not as expected"):
        diarize._fetch(src.as_uri(), hashlib.sha256(blob).hexdigest(), "pkg/other.onnx", tmp_path / "models" / "x.onnx")


def test_ensure_models_downloads_only_what_is_missing(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(diarize, "_fetch", lambda url, sha, member, target: (calls.append(target.name), target.write_bytes(b"x")))
    diarize.ensure_models(tmp_path)
    diarize.ensure_models(tmp_path)
    assert sorted(calls) == sorted([diarize.SEGMENTATION["name"], diarize.EMBEDDING["name"]])


def test_download_failure_is_a_readable_error(tmp_path, monkeypatch):
    def boom(*_a):
        raise OSError("offline")
    monkeypatch.setattr(diarize, "_fetch", boom)
    with pytest.raises(RuntimeError, match="internet"):
        diarize.ensure_models(tmp_path)


# -------------------------------------------------------------------------- cli ---

def test_speakers_need_the_optional_package(monkeypatch, tmp_path):
    monkeypatch.setattr(diarize, "available", lambda: False)
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x")
    with pytest.raises(SystemExit, match="sherpa-onnx"):
        main(["edit-plan", str(audio), "--speakers", "3", "--out", str(tmp_path / "o")])
    monkeypatch.setattr(diarize, "available", lambda: True)
    with pytest.raises(SystemExit, match="2-8"):
        main(["edit-plan", str(audio), "--speakers", "1", "--out", str(tmp_path / "o")])


@needs_ffmpeg
def test_run_labels_subtitles_and_the_video_comes_later_with_the_names_burned_in(tmp_path, monkeypatch):
    audio = tmp_path / "ep.mp3"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=400",
                    str(audio)], check=True)
    source = [Cue(i * 5.0, i * 5.0 + 5.0, f"第{i}句內容") for i in range(80)]
    srt.write(tmp_path / "ep.srt", source)
    monkeypatch.setattr(diarize, "available", lambda: True)
    monkeypatch.setattr(diarize, "label_cues", lambda _a, c, n: [Cue(x.start, x.end, x.text, f"講者{i % 2 + 1}") for i, x in enumerate(c)])
    reply = tmp_path / "reply.py"
    clips = json.dumps({"clips": [{"start": 10, "end": 30, "title": "甲", "reason": "理由理由理由", "score": 0.9}]}, ensure_ascii=False)
    reply.write_text(f"import sys; sys.stdin.read(); print({clips!r})", encoding="utf-8")
    out = tmp_path / "out"
    assert main(["run", str(audio), "--srt", str(tmp_path / "ep.srt"), "--out", str(out), "--speakers", "2", "--backend", "cmd",
                 "--cmd", f'python "{reply}"']) == 0
    episode = srt.read(out / "ep.srt")  # the labelled copy replaces the attached file
    assert episode[0].speaker == "講者1" and episode[1].speaker == "講者2"
    manifest = json.loads((out / "clips.json").read_text(encoding="utf-8"))
    assert manifest["srt_path"] == str(out / "ep.srt")
    folder = next(p for p in out.iterdir() if p.is_dir())
    assert "【講者" in (folder / "clip.srt").read_text(encoding="utf-8")
    assert not (folder / "clip.mp4").exists() and not (folder / ".video.srt").exists()  # nothing is burned in yet
    srt.write(folder / "clip.srt", [replace(c, speaker="小明") for c in srt.read(folder / "clip.srt")])  # the user renamed
    assert main(["videos", str(out)]) == 0
    burned = (folder / ".video.srt").read_text(encoding="utf-8")
    assert "【" not in burned and "小明：第" in burned
    assert (folder / "clip.mp4").stat().st_size > 0


def test_a_labelling_failure_keeps_the_transcript(tmp_path, monkeypatch, capsys):
    from podclip.cli import _label_speakers
    monkeypatch.setattr(diarize, "label_cues", lambda *_a: (_ for _ in ()).throw(RuntimeError("no model")))
    c = [Cue(0, 1, "a")]
    out, ok = _label_speakers(tmp_path / "a.mp3", c, 2)
    assert out == c and ok is False and "speaker labels skipped" in capsys.readouterr().err


# ------------------------------------------------------------------ voice check ---

def _fake_world(np):
    """Two 'voices': samples of +0.5 (speaker 0) and -0.5 (speaker 1). embed() turns the sign into a unit vector."""
    sr = 16000
    samples = np.concatenate([np.full(40 * sr, 0.5), np.full(40 * sr, -0.5), np.full(4 * sr, 0.5), np.full(4 * sr, -0.5)]).astype(np.float32)

    def embed(a):
        return np.array([1.0, 0.0] if a.mean() > 0 else [0.0, 1.0], dtype=np.float32)
    turns = [(0, 40, 0), (40, 80, 1), (80, 84, 1), (84, 88, 1)]  # the turns call the last 8 s speaker 1, wrongly for 80-84
    return samples, turns, embed


def test_voice_check_moves_a_cue_whose_audio_matches_another_speaker():
    np = pytest.importorskip("numpy")
    samples, turns, embed = _fake_world(np)
    c = [Cue(10, 12, "甲說的"), Cue(50, 52, "乙說的"), Cue(80, 82, "其實是甲")]
    picked = diarize.pick(c, turns)
    assert picked == [0, 1, 1]
    fixed, changed = diarize.refine(c, picked, turns, samples, embed)
    assert fixed == [0, 1, 0] and changed == 1


def test_voice_check_ignores_very_short_cues_and_leaves_unknown_speakers_alone():
    np = pytest.importorskip("numpy")
    samples, turns, embed = _fake_world(np)
    short = [Cue(80, 80.4, "嗯")]
    assert diarize.refine(short, [1], turns, samples, embed) == ([1], 0)
    assert diarize.refine([Cue(80, 82, "x")], [None], turns, samples, embed) == ([None], 0)
    assert diarize.refine([Cue(80, 82, "x")], [7], turns, samples, embed) == ([7], 0)  # no voice known for speaker 7


def test_voice_check_needs_two_voices_with_enough_clean_speech():
    np = pytest.importorskip("numpy")
    samples, _turns, embed = _fake_world(np)
    one_voice = [(0, 40, 0), (40, 41, 1)]  # speaker 1 has only 1 s alone: no average voice for it
    assert diarize.refine([Cue(50, 52, "x")], [1], one_voice, samples, embed) == ([1], 0)


def test_voice_check_keeps_a_close_call():
    np = pytest.importorskip("numpy")
    samples, turns, _ = _fake_world(np)
    blurry = lambda a: np.array([0.7, 0.6], dtype=np.float32) / np.linalg.norm([0.7, 0.6])  # equally close to both centroids
    known = diarize.centroids(samples, turns, lambda a: np.array([1.0, 0.0], dtype=np.float32) if a.mean() > 0 else np.array([0.0, 1.0], dtype=np.float32))
    assert set(known) == {0, 1}
    c = [Cue(80, 82, "x")]
    real = lambda a: np.array([1.0, 0.0], dtype=np.float32) if a.mean() > 0 else np.array([0.0, 1.0], dtype=np.float32)
    # a vague voice cannot beat the margin even though it is not exactly the assigned speaker's
    assert diarize.refine(c, [0], turns, samples, lambda a: blurry(a) if len(a) == 32000 else real(a))[1] == 0


def test_a_failing_voice_check_keeps_the_turn_labels(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(diarize, "_samples", lambda _a: [0.0] * 10)
    monkeypatch.setattr(diarize, "turns_for", lambda _a, _n, _s=None: [(0, 3, 4)])
    monkeypatch.setattr(diarize, "_embedder", lambda: (_ for _ in ()).throw(RuntimeError("no model")))
    out = diarize.label_cues(tmp_path / "a.mp3", [Cue(0, 3, "你好")], 2)
    assert out[0].speaker == "講者1" and "voice check skipped" in capsys.readouterr().err
