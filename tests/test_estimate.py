import json

import pytest

from podclip import estimate as est


def test_windows_match_the_finder():
    assert [est.windows_for(s) for s in (60, 3600, 3744, 3900, 7000)] == [1, 1, 2, 2, 3]


def test_clips_and_plan_call_counts():
    one = est.estimate("clips", 600, has_srt=True)
    assert one["ai_calls"] == 1 and one["transcribe_sec"] == 0 and one["total_sec"] == one["ai_sec"]
    assert est.estimate("plan", 3744, has_srt=True)["ai_calls"] == 4          # cuts + outline, two windows each
    assert est.estimate("plan", 3744, has_srt=True, use_ai=False)["ai_calls"] == 0
    with pytest.raises(ValueError):
        est.estimate("notes", 100)


def test_transcription_time_scales_with_model_and_device():
    slow = est.estimate("clips", 3600, model="medium", device="cpu")["transcribe_sec"]
    fast = est.estimate("clips", 3600, model="tiny", device="cpu")["transcribe_sec"]
    gpu = est.estimate("clips", 3600, model="small", device="cuda")["transcribe_sec"]
    assert slow > fast and gpu < est.estimate("clips", 3600, model="small", device="cpu")["transcribe_sec"]


def test_learned_speed_replaces_the_default(tmp_path):
    stats = tmp_path / "speed.json"
    assert est.rtf("small", "cpu", stats) == (est.DEFAULT_RTF[("small", "cpu")], False)
    for audio, took in ((600, 60), (1200, 180), (900, 90)):
        est.record_speed(stats, "small", "cpu", audio, took)
    ratio, learned = est.rtf("small", "cpu", stats)
    assert learned and ratio == pytest.approx(0.1)                              # median of 0.1, 0.15, 0.1
    assert est.estimate("clips", 1000, stats_path=stats)["transcribe_sec"] == round(est.LOAD_SEC + 0.1 * 1000)


def test_record_speed_ignores_junk_and_keeps_only_recent_runs(tmp_path):
    stats = tmp_path / "speed.json"
    est.record_speed(stats, "small", "cpu", 10, 5)      # too short to say anything
    est.record_speed(None, "small", "cpu", 600, 60)     # no path configured
    assert not stats.exists()
    for i in range(8):
        est.record_speed(stats, "base", "cpu", 600, 30 + i)
    assert len(json.loads(stats.read_text())["base|cpu"]) == est.KEEP_RUNS
    stats.write_text("{not json")
    assert est.rtf("base", "cpu", stats)[1] is False    # a broken file falls back to defaults
