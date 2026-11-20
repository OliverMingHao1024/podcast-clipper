import json
import shutil
import subprocess
from pathlib import Path

import pytest

from podclip import edit, srt
from podclip.cli import main
from podclip.edit import Cut, filler_cuts, kept_segments, merge, parse_ai_cuts, remap_cues
from podclip.llm import LLMError


def cues_of(*texts, step=5.0):
    return [srt.Cue(i * step, i * step + step, t) for i, t in enumerate(texts)]


def test_merge_unions_overlaps_and_skips_disabled():
    cuts = [Cut(10, 20, "a"), Cut(15, 30, "b"), Cut(40, 50, "c", apply=False), Cut(60, 60.01, "tiny")]
    assert merge(cuts, 100) == [(10, 30)]
    assert merge([Cut(-5, 3, "x"), Cut(98, 120, "y")], 100) == [(0, 3), (98, 100)]


def test_kept_segments_are_the_complement():
    assert kept_segments([Cut(10, 20, "a"), Cut(30, 40, "b")], 100) == [(0, 10), (20, 30), (40, 100)]
    assert kept_segments([Cut(0, 100, "all")], 100) == []


def test_filler_cuts_only_pure_filler_cues():
    cues = cues_of("嗯", "嗯，", "我覺得嗯這樣", "呃呃。", "就是")
    cuts = filler_cuts(cues)
    assert [c.reason for c in cuts] == ["嗯", "嗯，", "呃呃。"]
    assert all(c.start > cues[i].start and c.end < cues[i].end for c, i in zip(cuts, (0, 1, 3)))


def test_parse_ai_cuts_validates():
    cues = cues_of(*["句"] * 100)  # 500 s
    raw = json.dumps({"cuts": [
        {"start": 10, "end": 14, "kind": "retake", "reason": "重講"},
        {"start": 10, "end": 14, "kind": "delete_everything", "reason": "bad kind"},
        {"start": 0, "end": 99, "kind": "tangent", "reason": "too long"},
        {"start": 50, "end": 500, "kind": "tangent", "reason": "out of range"},
        {"start": "3", "end": 4, "kind": "retake", "reason": "str"},
        {"start": 20, "end": 21, "kind": "incident", "reason": "x\ny"},
    ]}, ensure_ascii=False)
    cuts = parse_ai_cuts(raw, cues, 0, 99)
    assert [(c.kind, round(c.start), round(c.end)) for c in cuts] == [("retake", 50, 75), ("incident", 100, 110)]
    assert "\n" not in cuts[1].reason


def test_remap_cues_shifts_and_drops():
    cues = cues_of("a", "b", "c", "d")          # 0-5, 5-10, 10-15, 15-20
    out = remap_cues(cues, [Cut(5, 10, "x")], 20)
    assert [(c.text, c.start, c.end) for c in out] == [("a", 0, 5), ("c", 5, 10), ("d", 10, 15)]


class Fake:
    def __init__(self, answer):
        self.answer = answer

    def complete(self, system, user):
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_ai_failure_raises():
    with pytest.raises(LLMError):
        edit.ai_cuts(cues_of(*["句"] * 20), Fake(LLMError("boom")))


needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg missing")


def _tone_silence_tone(path: Path):
    # 10 s tone, 4 s silence, 10 s tone
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=300:duration=10",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=4",
                    "-f", "lavfi", "-i", "sine=frequency=500:duration=10",
                    "-filter_complex", "[0:a]aformat=sample_rates=44100:channel_layouts=mono[a];"
                    "[2:a]aformat=sample_rates=44100:channel_layouts=mono[c];[a][1:a][c]concat=n=3:v=0:a=1",
                    str(path)], check=True)


@needs_ffmpeg
def test_silence_detected_and_removed_end_to_end(tmp_path):
    audio = tmp_path / "ep.mp3"
    _tone_silence_tone(audio)
    cues = cues_of("嗯", "內容", "內容", step=8.0)
    srt.write(tmp_path / "ep.srt", cues)
    out = tmp_path / "plan"
    assert main(["edit-plan", str(audio), "--srt", str(tmp_path / "ep.srt"), "--out", str(out), "--no-ai"]) == 0
    plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    kinds = {c["kind"] for c in plan["cuts"]}
    assert kinds == {"silence", "filler"}
    silence = next(c for c in plan["cuts"] if c["kind"] == "silence")
    assert 9.5 < silence["start"] < 10.5 and 13.5 < silence["end"] < 14.5
    assert (out / "plan.md").read_text(encoding="utf-8").startswith("# 剪輯清單")

    edited = tmp_path / "edited.mp3"
    assert main(["edit-render", str(out / "plan.json"), "--out", str(edited), "--srt", str(tmp_path / "ep.srt"),
                 "--no-loudnorm"]) == 0
    new_len = edit.probe_duration(edited)
    removed = sum(c["end"] - c["start"] for c in plan["cuts"])
    assert abs(new_len - (plan["duration"] - removed)) < 0.5
    assert (tmp_path / "edited.srt").stat().st_size > 0


@needs_ffmpeg
def test_apply_false_keeps_the_cut(tmp_path):
    audio = tmp_path / "ep.mp3"
    _tone_silence_tone(audio)
    out = tmp_path / "plan"
    main(["edit-plan", str(audio), "--srt", str(_srt(tmp_path)), "--out", str(out), "--no-ai"])
    plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    for c in plan["cuts"]:
        c["apply"] = False
    (out / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    edited = tmp_path / "edited.wav"
    assert main(["edit-render", str(out / "plan.json"), "--out", str(edited), "--no-loudnorm"]) == 0
    assert abs(edit.probe_duration(edited) - plan["duration"]) < 0.3


def _srt(tmp_path):
    p = tmp_path / "x.srt"
    srt.write(p, cues_of("內容", "內容", "內容", step=8.0))
    return p
