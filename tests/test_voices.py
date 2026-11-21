import json

import pytest

from podclip import diarize, voices
from podclip.srt import Cue

np = pytest.importorskip("numpy")


def vec(*head):
    """A 32-number vector that starts with the given numbers."""
    return [float(x) for x in head] + [0.0] * (32 - len(head))


@pytest.fixture()
def store(tmp_path):
    return tmp_path / "voices.json"


# ------------------------------------------------------------------------ store ---

def test_enroll_list_and_forget(store):
    assert voices.people(store) == []
    assert voices.enroll("  小  明 ", vec(1), store) == "小 明"
    voices.enroll("小 明", vec(0.9, 0.1), store)
    voices.enroll("小華", vec(0, 1), store)
    assert voices.people(store) == [{"name": "小 明", "samples": 2}, {"name": "小華", "samples": 1}]
    assert voices.forget("小華", store) is True and voices.forget("小華", store) is False
    assert [p["name"] for p in voices.people(store)] == ["小 明"]


def test_known_gives_unit_length_averages(store):
    voices.enroll("甲", vec(2), store)
    voices.enroll("甲", vec(0, 2), store)
    got = voices.known(store)["甲"]
    assert abs(float(np.linalg.norm(got)) - 1.0) < 1e-6 and abs(float(got[0]) - float(got[1])) < 1e-6


def test_only_the_newest_samples_are_kept(store):
    for i in range(voices.MAX_SAMPLES + 3):
        voices.enroll("甲", vec(1, i), store)
    assert voices.people(store) == [{"name": "甲", "samples": voices.MAX_SAMPLES}]
    assert json.loads(store.read_text(encoding="utf-8"))["voices"]["甲"]["samples"][-1][1] == voices.MAX_SAMPLES + 2


def test_bad_names_and_vectors_are_refused(store):
    for bad_name in ("", "含【括號】", "x" * 21):
        with pytest.raises(ValueError):
            voices.enroll(bad_name, vec(1), store)
    for bad_vec in ([], [1.0] * 4, [float("nan")] + [0.0] * 31, ["x"] * 32):
        with pytest.raises(ValueError):
            voices.enroll("甲", bad_vec, store)
    voices.enroll("甲", vec(1), store)
    with pytest.raises(ValueError, match="fit"):
        voices.enroll("甲", [1.0] * 48, store)  # a different vector length cannot join the same person
    assert not (store.parent / "tmp").exists()


def test_a_damaged_or_foreign_file_reads_as_empty(store):
    store.write_text("not json", encoding="utf-8")
    assert voices.load(store)["voices"] == {}
    store.write_text(json.dumps({"version": 1, "model": "other-model", "voices": {"甲": {"samples": [vec(1)]}}}), encoding="utf-8")
    assert voices.load(store)["voices"] == {}  # vectors of another speaker model are never mixed in
    store.write_bytes(b"x" * (voices.MAX_BYTES + 1))
    assert voices.load(store)["voices"] == {}
    assert voices.load(store.parent / "missing.json")["voices"] == {}


def test_load_drops_malformed_people_but_keeps_good_ones(store):
    good = {"samples": [vec(1)], "updated": 1}
    raw = {"version": 1, "model": voices._model_id(), "voices": {
        "好": good, "壞": {"samples": [[1.0, "x"]]}, "含【】": good, "空": {"samples": []}, "非": 5}}
    store.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    assert list(voices.load(store)["voices"]) == ["好"]


# ---------------------------------------------------------------- export, import ---

def test_export_then_import_merges_samples(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    voices.enroll("甲", vec(1), a)
    voices.enroll("乙", vec(0, 1), a)
    voices.enroll("甲", vec(0.5, 0.5), b)
    assert voices.import_text(voices.export_text(a), b) == 2
    assert {p["name"]: p["samples"] for p in voices.people(b)} == {"甲": 2, "乙": 1}


def test_import_rejects_files_that_are_not_valid_exports(store):
    for text in ("nope", "[]", json.dumps({"version": 1, "model": "x", "voices": {"甲": {"samples": [vec(1)]}}}),
                 json.dumps({"version": 1, "model": voices._model_id(), "voices": {"甲": {"samples": [[float("inf")] * 32]}}})):
        with pytest.raises(ValueError):
            voices.import_text(text, store)
    assert not store.exists()
    with pytest.raises(ValueError, match="large"):
        voices.import_text(" " * (voices.MAX_BYTES + 1), store)


# ------------------------------------------------------------- learning a voice ---

def _audio():
    sr = 16000
    samples = np.concatenate([np.full(30 * sr, 0.5), np.full(30 * sr, -0.5)]).astype(np.float32)
    embed = lambda a: np.array([1.0, 0.0] + [0.0] * 30, dtype=np.float32) if a.mean() > 0 else np.array([0.0, 1.0] + [0.0] * 30, dtype=np.float32)
    cues = [Cue(0, 30, "甲說很久的話", "講者1"), Cue(30, 60, "乙說很久的話", "講者2"), Cue(5, 5.5, "短", "講者3")]
    return samples, embed, cues


def test_voice_sample_needs_enough_speech_of_that_speaker():
    samples, embed, cues = _audio()
    first = diarize.voice_sample(samples, cues, "講者1", embed)
    assert list(map(float, first))[:2] == [1.0, 0.0]
    assert diarize.voice_sample(samples, cues, "講者3", embed) is None  # only a half-second cue
    assert diarize.voice_sample(samples, cues, "沒有這人", embed) is None


def test_remember_stores_named_speakers_and_reports_the_ones_it_could_not_learn(store, monkeypatch):
    samples, embed, cues = _audio()
    monkeypatch.setattr(diarize, "require", lambda: None)
    monkeypatch.setattr(diarize, "_samples", lambda _a: samples)
    monkeypatch.setattr(diarize, "_embedder", lambda: embed)
    done = voices.remember("ep.mp3", cues, {"講者1": "小明", "講者2": "小華", "講者3": "路人", "講者1x": "含【】"}, store)
    assert done == {"小明": True, "小華": True, "路人": False}
    assert [p["name"] for p in voices.people(store)] == ["小明", "小華"]


# ---------------------------------------------------------------------- matching ---

def unit(*v):
    a = np.array(v, dtype=np.float32)
    return a / np.linalg.norm(a)


def test_name_keeps_names_and_numbers_the_rest_by_first_appearance():
    cues = [Cue(i, i + 1, "x") for i in range(4)]
    assert [c.speaker for c in diarize.name(cues, [5, "小明", 5, 2])] == ["講者1", "小明", "講者1", "講者2"]


def test_a_cue_is_named_only_when_one_known_person_is_clearly_closer():
    known = {"甲": unit(1, 0, 0), "乙": unit(0, 1, 0)}
    vectors = [unit(1, 0.1, 0), unit(1, 1, 0), unit(0, 0, 1), None]
    out, named = diarize.match_known([0, 0, 0, 0], vectors, known)
    assert out == ["甲", 0, 0, 0] and named == 1  # 2nd is torn between both, 3rd is nobody, 4th is too short


def test_with_one_known_person_the_bar_is_higher():
    known = {"甲": unit(1, 0, 0)}
    out, _ = diarize.match_known([0, 0], [unit(1, 1, 0), unit(1, 0.1, 0)], known)  # 0.71 vs 0.99
    assert out == ["甲", "甲"]  # 0.71 and 0.99 both pass the alone-bar of 0.5
    weak, _ = diarize.match_known([0], [unit(0.45, 1, 0)], known)  # about 0.41: enough with company, not alone
    assert weak == [0]


def test_no_known_voices_changes_nothing():
    assert diarize.match_known([0, 1], [unit(1, 0), unit(0, 1)], {}) == ([0, 1], 0)


def test_a_pure_cluster_names_its_unsure_cues_but_a_mixed_one_does_not():
    known = {"甲": unit(1, 0, 0), "乙": unit(0, 1, 0)}
    sure_a, unsure = unit(1, 0.05, 0), unit(0, 0, 1)
    pure_picked = [0] * 10
    out, _ = diarize.match_known(pure_picked, [sure_a] * 9 + [unsure], known)
    assert out == ["甲"] * 10  # nine sure cues all say 甲, so the unsure tenth is 甲 as well
    mixed_picked = [0] * 10
    out, _ = diarize.match_known(mixed_picked, [sure_a] * 5 + [unit(0.05, 1, 0)] * 4 + [unsure], known)
    assert out[-1] == 0 and out[:5] == ["甲"] * 5 and out[5:9] == ["乙"] * 4  # a cluster of two people stays unnamed
    few, _ = diarize.match_known([0] * 4, [sure_a] * 3 + [unsure], known)
    assert few[-1] == 0  # three sure cues are too few to speak for the cluster


# -------------------------------------------------------------------------- web ---

def _server(tmp_path):
    import threading
    from podclip import web
    srv = web.make_server(tmp_path / "work")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _call(srv, method, path, body=None, raw=None, token=True):
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1])
    headers = {"Host": f"127.0.0.1:{srv.server_address[1]}"}
    if token:
        headers["X-Token"] = srv.state.token
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    out = (resp.status, resp.read(), dict(resp.getheaders()))
    conn.close()
    return out


def test_web_lists_forgets_exports_and_imports_voices(tmp_path):
    srv = _server(tmp_path)
    try:
        where = srv.state.workdir / "voices.json"
        voices.enroll("甲", vec(1), where)
        status, body, _ = _call(srv, "GET", "/api/voices")
        assert status == 200 and json.loads(body)["voices"] == [{"name": "甲", "samples": 1}]
        assert "samples" not in json.dumps(json.loads(body)["voices"][0]).replace('"samples": 1', "")  # no vectors leave the server
        status, body, headers = _call(srv, "GET", f"/export/voices?t={srv.state.token}", token=False)
        assert status == 200 and "attachment" in headers["Content-Disposition"] and "甲" in body.decode("utf-8")
        assert _call(srv, "GET", "/export/voices?t=wrong", token=False)[0] == 403
        exported = body
        assert _call(srv, "POST", "/api/voices/forget", {"name": "甲"})[0] == 200
        assert _call(srv, "POST", "/api/voices/forget", {"name": "甲"})[0] == 404
        assert _call(srv, "PUT", "/api/voices/import", raw=b"garbage")[0] == 400
        status, body, _ = _call(srv, "PUT", "/api/voices/import", raw=exported)
        assert status == 200 and json.loads(body)["imported"] == 1
        assert _call(srv, "GET", "/api/voices", token=False)[0] == 403
    finally:
        srv.shutdown()
        srv.server_close()


def test_rename_can_remember_voices_and_a_failure_keeps_the_rename(tmp_path, monkeypatch):
    from podclip import srt, web
    srv = _server(tmp_path)
    try:
        folder = tmp_path / "job"
        (folder / "out").mkdir(parents=True)
        cues = [Cue(0, 30, "甲說很久的話", "講者1"), Cue(30, 60, "乙說很久的話", "講者2")]
        srt.write(folder / "out" / "ep.srt", cues)
        audio = tmp_path / "ep.mp3"
        audio.write_bytes(b"x")
        job = web.Job("clips", folder)
        job.source = audio
        job.status = "done"
        srv.state.jobs[job.id] = job
        seen = {}
        monkeypatch.setattr(voices, "remember", lambda a, c, m, where=None: seen.update(audio=a, mapping=m, where=where) or {"小明": True})
        status, body, _ = _call(srv, "POST", f"/api/speakers/{job.id}", {"names": {"講者1": "小明"}, "remember": True})
        data = json.loads(body)
        assert status == 200 and data["remembered"] == ["小明"] and data["note"] == ""
        assert seen["mapping"] == {"講者1": "小明"} and seen["audio"] == audio and seen["where"] == srv.state.workdir / "voices.json"
        assert [c.speaker for c in srt.read(folder / "out" / "ep.srt")] == ["小明", "講者2"]
        # without the box ticked nothing is learned
        seen.clear()
        _call(srv, "POST", f"/api/speakers/{job.id}", {"names": {"講者2": "小華"}})
        assert seen == {}
        # a learning failure must not undo the rename
        def boom(*_a, **_k):
            raise RuntimeError("no model")
        monkeypatch.setattr(voices, "remember", boom)
        status, body, _ = _call(srv, "POST", f"/api/speakers/{job.id}", {"names": {"小華": "阿華"}, "remember": True})
        assert status == 200 and "沒能記住" in json.loads(body)["note"]
        assert [c.speaker for c in srt.read(folder / "out" / "ep.srt")] == ["小明", "阿華"]
        job.source = None  # audio gone: same, the rename still happens
        status, body, _ = _call(srv, "POST", f"/api/speakers/{job.id}", {"names": {"阿華": "華華"}, "remember": True})
        assert status == 200 and "沒能記住" in json.loads(body)["note"]
    finally:
        srv.shutdown()
        srv.server_close()
