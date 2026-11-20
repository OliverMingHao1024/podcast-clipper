import json

import pytest

from podclip import notes
from podclip.srt import Cue


class Fake:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def complete(self, system, user):
        self.calls.append(user)
        return self.answers.pop(0)


CUES = [Cue(i * 10.0, i * 10.0 + 9, f"句子{i}") for i in range(30)]


def test_single_window_formats_like_the_sample():
    answer = json.dumps({"summary": "簡介。", "topics": [{"row": 12, "topic": "賄選的標準"}, {"row": 2, "topic": "火球祭的驚喜"},
                                                         {"row": 40, "topic": "越界列"}, {"row": True, "topic": "壞"},
                                                         {"row": 5, "topic": "火球祭的驚喜？"}]}, ensure_ascii=False)
    out = notes.episode_notes(CUES, Fake(answer))
    assert out.topics == ["火球祭的驚喜", "賄選的標準"]  # time order, out-of-range / bool / duplicate rows dropped
    assert out.render() == "簡介。\n\n【本集重點】\n\n火球祭的驚喜\n\n賄選的標準\n"


def test_bad_json_is_retried_once_then_gives_up():
    fake = Fake("not json", "still not")
    with pytest.raises(Exception):
        notes.episode_notes(CUES, fake)
    assert len(fake.calls) == 2 and "上一次輸出不合格" in fake.calls[1]


def test_topic_text_is_bounded_and_cleaned():
    parsed = notes.parse_window(json.dumps({"summary": "x" * 999, "topics": [{"row": 1, "topic": "**" + "長" * 100 + "\n"}]}), 0, 5)
    assert len(parsed.topics[0]) <= notes.MAX_TOPIC and "*" not in parsed.topics[0] and len(parsed.summary) <= notes.MAX_SUMMARY


def test_multiple_windows_are_merged_by_a_second_call():
    long_cues = [Cue(i * 60.0, i * 60.0 + 50, f"逐字稿Z{i}") for i in range(130)]  # ~2.2 h -> several windows
    spans = notes.windows(long_cues, notes.Config())
    assert len(spans) >= 2
    window_answers = [json.dumps({"summary": "s", "topics": [{"row": a, "topic": f"主題{a}"}]}) for a, _ in spans]
    fake = Fake(*window_answers, json.dumps({"summary": "合併", "topics": ["甲", "乙", "甲"]}))
    out = notes.episode_notes(long_cues, fake)
    assert out.topics == ["甲", "乙"] and out.summary == "合併"
    assert "<topics>" in fake.calls[-1] and "逐字稿Z" not in fake.calls[-1]  # the merge call never sees the transcript
