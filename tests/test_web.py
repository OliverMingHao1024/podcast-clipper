import http.client
import json
import threading

import pytest

from podclip import web


@pytest.fixture()
def server(tmp_path):
    srv = web.make_server(tmp_path / "work")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def call(srv, method, path, body=None, *, token=True, host=None, origin=None, raw=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1])
    headers = {"Host": host or f"127.0.0.1:{srv.server_address[1]}"}
    if token:
        headers["X-Token"] = srv.state.token
    if origin:
        headers["Origin"] = origin
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    payload = resp.read()
    conn.close()
    return resp.status, payload


def test_page_embeds_token_only_on_valid_host(server):
    status, body = call(server, "GET", "/", token=False)
    assert status == 200 and server.state.token.encode() in body
    status, _ = call(server, "GET", "/", token=False, host="evil.example:80")
    assert status == 403


def test_api_needs_token_and_same_origin(server):
    assert call(server, "GET", "/api/env", token=False)[0] == 403
    assert call(server, "GET", "/api/env")[0] == 200
    assert call(server, "GET", "/api/env", origin="http://evil.example")[0] == 403


def test_upload_rejects_bad_type_and_accepts_audio(server):
    assert call(server, "PUT", "/api/upload?name=x.exe", raw=b"abc")[0] == 400
    status, body = call(server, "PUT", "/api/upload?name=..%5C..%5Cep.mp3", raw=b"abc")
    assert status == 200
    info = json.loads(body)
    saved = server.state.upload_file(info["upload_id"])
    assert saved.name == "ep.mp3" and saved.read_bytes() == b"abc"
    assert saved.is_relative_to(server.state.workdir / "uploads")


def test_start_rejects_unlisted_options(server):
    up = json.loads(call(server, "PUT", "/api/upload?name=a.mp3", raw=b"abc")[1])["upload_id"]
    for options in ({"whisper_model": "--cmd"}, {"language": "zh --cmd x"}, {"device": "tpu"},
                    {"formats": []}, {"max_clips": 999}):
        body = {"kind": "clips", "upload_id": up, "options": options}
        assert call(server, "POST", "/api/start", body)[0] == 400, options
    assert call(server, "POST", "/api/start", {"kind": "clips", "upload_id": "../x", "options": {"formats": ["audio"]}})[0] == 400


def test_build_argv_has_no_user_paths(tmp_path):
    argv = web.build_argv("plan", {"language": "zh", "no_ai": True}, tmp_path / "a.mp3", tmp_path)
    assert argv[0] == "edit-plan" and "--no-ai" in argv and "--cmd" not in argv
    assert argv[argv.index("--backend") + 1] == "claude"


def test_files_stay_inside_job_out(server, tmp_path):
    folder = tmp_path / "job"
    (folder / "out").mkdir(parents=True)
    (folder / "out" / "clip.txt").write_text("hi")
    (folder / "out" / ".hidden").write_text("x")
    (folder / "secret.txt").write_text("no")
    job = web.Job("clips", folder)
    job.status = "done"
    server.state.jobs[job.id] = job
    t = server.state.token
    assert call(server, "GET", f"/files/{job.id}/clip.txt?t={t}", token=False) == (200, b"hi")
    assert call(server, "GET", f"/files/{job.id}/..%2Fsecret.txt?t={t}", token=False)[0] == 404
    assert call(server, "GET", f"/files/{job.id}/.hidden?t={t}", token=False)[0] == 404
    assert call(server, "GET", f"/files/{job.id}/clip.txt", token=False)[0] == 403


def test_plan_flags_roundtrip(server, tmp_path):
    folder = tmp_path / "job"
    (folder / "out").mkdir(parents=True)
    plan = {"version": 1, "source": "x.mp3", "duration": 60.0,
            "cuts": [{"start": 1, "end": 3, "kind": "silence", "reason": "", "apply": True},
                     {"start": 5, "end": 9, "kind": "intro", "reason": "<script>", "apply": True}]}
    (folder / "out" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    job = web.Job("plan", folder)
    job.status = "done"
    server.state.jobs[job.id] = job
    assert call(server, "POST", f"/api/plan/{job.id}", {"apply": [True]})[0] == 400
    assert call(server, "POST", f"/api/plan/{job.id}", {"apply": [True, "no"]})[0] == 400
    assert call(server, "POST", f"/api/plan/{job.id}", {"apply": [True, False]})[0] == 200
    status, body = call(server, "GET", f"/api/plan/{job.id}")
    assert status == 200 and [c["apply"] for c in json.loads(body)["cuts"]] == [True, False]


def test_job_environment_is_quiet_and_offline(monkeypatch, tmp_path):
    seen = {}

    class FakePopen:
        stdout = iter(())
        pid = 1

        def __init__(self, argv, **kw):
            seen["env"], seen["argv"] = kw["env"], argv

        def wait(self):
            return 0

    monkeypatch.setattr(web.subprocess, "Popen", FakePopen)
    state = web.State(tmp_path, "t")
    folder = tmp_path / "uploads" / ("a" * 32)
    folder.mkdir(parents=True)
    (folder / "ep.mp3").write_bytes(b"x")
    web.start_job(state, "plan", {"upload_id": "a" * 32, "no_ai": True})
    assert seen["env"]["HF_HUB_DISABLE_TELEMETRY"] == "1" and "--no-ai" in seen["argv"]


def test_unread_post_body_does_not_poison_the_connection(server, tmp_path):
    folder = tmp_path / "job"
    folder.mkdir()
    job = web.Job("clips", folder)
    job.status = "done"
    server.state.jobs[job.id] = job
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
    headers = {"X-Token": server.state.token}
    conn.request("POST", f"/api/cancel/{job.id}", body=b"{}", headers=headers)  # handler never reads this body
    assert conn.getresponse().read()
    conn.request("GET", f"/api/job/{job.id}", headers=headers)  # same keep-alive connection
    resp = conn.getresponse()
    assert resp.status == 200 and json.loads(resp.read())["status"] == "done"
    conn.close()


def test_backend_must_be_a_known_name(monkeypatch, tmp_path):
    monkeypatch.setenv("PODCLIP_BACKENDS", str(tmp_path / "none.json"))
    argv = web.build_argv("plan", {"backend": "codex"}, tmp_path / "a.mp3", tmp_path)
    assert argv[argv.index("--backend") + 1] == "codex"
    for bad in ("cmd", "rm -rf", "--cmd", "gemini"):
        with pytest.raises(web.ApiError):
            web.build_argv("plan", {"backend": bad}, tmp_path / "a.mp3", tmp_path)


def test_upload_name_cannot_be_a_windows_device(server):
    info = json.loads(call(server, "PUT", "/api/upload?name=NUL.mp3", raw=b"abc")[1])
    assert server.state.upload_file(info["upload_id"]).name == "_NUL.mp3"


def _done_job(server, tmp_path, kind="clips"):
    folder = tmp_path / "job"
    (folder / "out" / "01_a").mkdir(parents=True)
    (folder / "out" / "01_a" / "clip.mp3").write_bytes(b"audio")
    (folder / "out" / "01_a" / "post.txt").write_text("標題", encoding="utf-8")
    (folder / "out" / "clips.json").write_text(json.dumps({"clips": [], "alternates": [{}, {}]}), encoding="utf-8")
    (folder / "out" / "plan.json").write_text("{}", encoding="utf-8")
    (folder / "out" / ".hidden").write_text("x")
    job = web.Job(kind, folder)
    job.status = "done"
    server.state.jobs[job.id] = job
    return job


def test_zip_bundles_visible_result_files_only(server, tmp_path):
    import io
    import zipfile
    job = _done_job(server, tmp_path)
    t = server.state.token
    assert call(server, "GET", f"/zip/{job.id}", token=False)[0] == 403
    status, body = call(server, "GET", f"/zip/{job.id}?t={t}", token=False)
    assert status == 200
    names = sorted(zipfile.ZipFile(io.BytesIO(body)).namelist())
    assert names == ["01_a/clip.mp3", "01_a/post.txt", "clips.json"]  # no hidden files, no plan.json
    assert call(server, "GET", f"/zip/{'0' * 32}?t={t}", token=False)[0] == 404


def test_zip_of_an_edited_episode_has_only_the_deliverables(server, tmp_path):
    import io
    import zipfile
    job = _done_job(server, tmp_path, "render")
    out = job.folder / "out"
    for name in ("episode_edited.mp3", "episode_edited.srt", "episode_notes.txt", "plan.md", "ep.srt"):
        (out / name).write_text("x")
    status, body = call(server, "GET", f"/zip/{job.id}?t={server.state.token}", token=False)
    assert sorted(zipfile.ZipFile(io.BytesIO(body)).namelist()) == ["episode_edited.mp3", "episode_edited.srt",
                                                                     "episode_notes.txt", "plan.md"]


def test_job_reports_alternates_and_more_needs_a_manifest(server, tmp_path):
    job = _done_job(server, tmp_path)
    info = json.loads(call(server, "GET", f"/api/job/{job.id}")[1])
    assert info["alternates"] == 2
    argv = web.build_argv("more", {}, None, job.folder)
    assert argv[0] == "more" and argv[2:] == ["--count", "1"]
    (job.folder / "out" / "clips.json").unlink()
    assert call(server, "POST", "/api/start", {"kind": "more", "plan_job": job.id, "options": {}})[0] == 400


def test_clip_options_carry_length_and_shape(tmp_path):
    argv = web.build_argv("clips", {"formats": ["audio"], "min_sec": 30, "max_sec": 90, "aspect": "1:1"}, tmp_path / "a.mp3", tmp_path)
    assert argv[argv.index("--min-sec") + 1] == "30" and argv[argv.index("--max-sec") + 1] == "90"
    assert argv[argv.index("--aspect") + 1] == "1:1"
    for bad in ({"aspect": "4:3"}, {"min_sec": 100, "max_sec": 50}, {"max_sec": 5000}):
        with pytest.raises(web.ApiError):
            web.build_argv("clips", {"formats": ["audio"], **bad}, tmp_path / "a.mp3", tmp_path)


def test_parse_range_cases():
    assert web.parse_range(None, 100) is None
    assert web.parse_range("bytes=0-9", 100) == (0, 9)
    assert web.parse_range("bytes=90-", 100) == (90, 99)
    assert web.parse_range("bytes=-10", 100) == (90, 99)
    assert web.parse_range("bytes=50-500", 100) == (50, 99)  # end is clamped
    assert web.parse_range("bytes=0-1,5-6", 100) is None      # multi-range: whole file instead
    assert web.parse_range("nonsense", 100) is None
    for bad in ("bytes=100-", "bytes=60-50", "bytes=-0"):
        with pytest.raises(ValueError):
            web.parse_range(bad, 100)


def _raw(server, path, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
    conn.request("GET", path, headers={"Host": f"127.0.0.1:{server.server_address[1]}", **(headers or {})})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, dict(resp.getheaders()), body


def test_audio_is_served_inline_with_ranges_and_other_files_stay_downloads(server, tmp_path):
    job = _done_job(server, tmp_path)
    data = bytes(range(200))
    (job.folder / "out" / "01_a" / "clip.mp3").write_bytes(data)
    t = server.state.token
    base = f"/files/{job.id}/01_a/clip.mp3?t={t}"
    status, h, body = _raw(server, base + "&inline=1", {"Range": "bytes=10-19"})
    assert status == 206 and body == data[10:20] and h["Content-Range"] == "bytes 10-19/200"
    assert h["Content-Type"] == "audio/mpeg" and h["Content-Disposition"].startswith("inline") and h["Accept-Ranges"] == "bytes"
    assert _raw(server, base + "&inline=1")[2] == data
    assert _raw(server, base + "&inline=1", {"Range": "bytes=500-"})[0] == 416
    status, h, _ = _raw(server, base)  # no inline flag: a download
    assert h["Content-Type"] == "application/octet-stream" and h["Content-Disposition"].startswith("attachment")
    status, h, _ = _raw(server, f"/files/{job.id}/01_a/post.txt?t={t}&inline=1")  # not an audio type: never inline
    assert h["Content-Disposition"].startswith("attachment") and h["Content-Type"] == "application/octet-stream"


def test_source_route_serves_only_the_server_chosen_upload(server, tmp_path):
    job = _done_job(server, tmp_path)
    t = server.state.token
    assert _raw(server, f"/source/{job.id}?t={t}")[0] == 404  # no source set
    audio = tmp_path / "ep.mp3"
    audio.write_bytes(b"abcdef")
    job.source = audio
    assert _raw(server, f"/source/{job.id}?t={t}", {"Range": "bytes=1-3"})[2] == b"bcd"
    assert _raw(server, f"/source/{job.id}")[0] == 403  # token required
    note = tmp_path / "secret.txt"
    note.write_text("no")
    job.source = note
    assert _raw(server, f"/source/{job.id}?t={t}")[0] == 404  # only audio types


def _upload_audio(server, name="ep.mp3"):
    return json.loads(call(server, "PUT", f"/api/upload?name={name}", raw=b"abc")[1])["upload_id"]


SRT = "1\n00:00:01,000 --> 00:00:03,000\n第一句\n\n2\n00:00:04,000 --> 00:00:06,000\n第二句\n"


def test_subtitles_attach_validate_and_feed_the_run(server):
    up = _upload_audio(server)
    assert call(server, "PUT", f"/api/subtitles?for={up}", raw=b"not subtitles at all")[0] == 400
    assert call(server, "PUT", f"/api/subtitles?for={'0' * 32}", raw=SRT.encode())[0] == 400  # unknown upload
    assert call(server, "PUT", f"/api/subtitles?for={up}", raw=b"")[0] in (400, 413)
    status, body = call(server, "PUT", f"/api/subtitles?for={up}", raw=SRT.encode())
    assert status == 200 and json.loads(body)["cues"] == 2
    saved = server.state.upload_srt(up)
    assert saved is not None and "第一句" in saved.read_text(encoding="utf-8")
    assert server.state.upload_file(up).name == "ep.mp3"          # the subtitle file is not mistaken for the audio
    argv = web.build_argv("plan", {"use_srt": True, "no_ai": True}, server.state.upload_file(up), server.state.workdir / "j")
    assert argv[argv.index("--srt") + 1] == str(saved)
    assert "--srt" not in web.build_argv("plan", {}, server.state.upload_file(up), server.state.workdir / "j")


def test_use_srt_without_a_file_is_rejected(server):
    up = _upload_audio(server)
    with pytest.raises(web.ApiError):
        web.build_argv("clips", {"use_srt": True, "formats": ["audio"]}, server.state.upload_file(up), server.state.workdir / "j")


def test_estimate_endpoint(server, monkeypatch):
    up = _upload_audio(server)
    monkeypatch.setattr(web, "audio_duration", lambda _p: 3744.0)
    status, body = call(server, "POST", "/api/estimate", {"kind": "plan", "upload_id": up, "options": {"whisper_model": "small"}})
    data = json.loads(body)
    assert status == 200 and data["estimate"]["ai_calls"] == 4 and data["estimate"]["transcribe_sec"] > 0
    call(server, "PUT", f"/api/subtitles?for={up}", raw=SRT.encode())
    data = json.loads(call(server, "POST", "/api/estimate", {"kind": "clips", "upload_id": up, "options": {"use_srt": True}})[1])
    assert data["estimate"]["transcribe_sec"] == 0 and data["estimate"]["ai_calls"] == 2
    assert call(server, "POST", "/api/estimate", {"kind": "notes", "upload_id": up})[0] == 400
    assert call(server, "POST", "/api/estimate", {"kind": "clips", "upload_id": up, "options": {"whisper_model": "--x"}})[0] == 400
    monkeypatch.setattr(web, "audio_duration", lambda _p: None)
    assert json.loads(call(server, "POST", "/api/estimate", {"kind": "clips", "upload_id": up})[1])["estimate"] is None


def test_doctor_endpoint(server, monkeypatch):
    status, body = call(server, "GET", "/api/doctor")
    assert status == 200 and any(c["id"] == "python" for c in json.loads(body)["checks"])
    assert call(server, "GET", "/api/doctor?backend=rm")[0] == 400
    assert call(server, "GET", "/api/doctor", token=False)[0] == 403


def test_speaker_option_is_a_small_whole_number(tmp_path):
    audio = tmp_path / "a.mp3"
    argv = web.build_argv("plan", {"speakers": 3}, audio, tmp_path)
    assert argv[argv.index("--speakers") + 1] == "3"
    assert "--speakers" not in web.build_argv("plan", {}, audio, tmp_path)
    assert "--speakers" not in web.build_argv("clips", {"formats": ["audio"], "speakers": 0}, audio, tmp_path)
    for bad in (1, 9, 2.5, "3", True, [3]):
        with pytest.raises(web.ApiError):
            web.build_argv("clips", {"formats": ["audio"], "speakers": bad}, audio, tmp_path)


def test_speaker_rename_rewrites_every_subtitle_file_and_nothing_else(server, tmp_path):
    from podclip import srt
    folder = tmp_path / "job"
    (folder / "out" / "01_clip").mkdir(parents=True)
    cues = [srt.Cue(0, 30, "第一句夠長的範例句子", "講者1"), srt.Cue(30, 60, "第二句夠長的範例句子", "講者2")]
    srt.write(folder / "out" / "ep.srt", cues)
    srt.write(folder / "out" / "01_clip" / "clip.srt", cues[:1])
    srt.write(folder / "out" / "01_clip" / ".video.srt", cues[:1], labels=False)  # hidden helper file, never touched
    job = web.Job("clips", folder)
    job.status = "done"
    server.state.jobs[job.id] = job
    status, body = call(server, "GET", f"/api/speakers/{job.id}")
    assert status == 200 and [s["label"] for s in json.loads(body)["speakers"]] == ["講者1", "講者2"]
    assert call(server, "POST", f"/api/speakers/{job.id}", {"names": "x"})[0] == 400
    assert call(server, "POST", f"/api/speakers/{job.id}", {"names": {"講者1": "含【】"}})[0] == 400
    assert call(server, "POST", f"/api/speakers/{job.id}", {"names": {"講者1": "小明", "講者2": "  "}})[0] == 200
    assert [c.speaker for c in srt.read(folder / "out" / "ep.srt")] == ["小明", "講者2"]
    assert srt.read(folder / "out" / "01_clip" / "clip.srt")[0].speaker == "小明"
    assert srt.read(folder / "out" / "01_clip" / ".video.srt")[0].speaker == ""
    assert call(server, "GET", f"/api/speakers/{job.id}", token=False)[0] == 403


def test_a_job_without_labels_has_no_speakers(server, tmp_path):
    from podclip import srt
    folder = tmp_path / "job"
    (folder / "out").mkdir(parents=True)
    srt.write(folder / "out" / "ep.srt", [srt.Cue(0, 5, "沒有講者標籤的字幕")])
    job = web.Job("plan", folder)
    server.state.jobs[job.id] = job
    assert json.loads(call(server, "GET", f"/api/speakers/{job.id}")[1])["speakers"] == []


def test_estimate_counts_speaker_labelling(server, monkeypatch):
    up = _upload_audio(server)
    monkeypatch.setattr(web, "audio_duration", lambda _p: 3600.0)
    base = json.loads(call(server, "POST", "/api/estimate", {"kind": "clips", "upload_id": up, "options": {}})[1])["estimate"]
    withs = json.loads(call(server, "POST", "/api/estimate", {"kind": "clips", "upload_id": up, "options": {"speakers": 3}})[1])["estimate"]
    assert base["speaker_sec"] == 0 and withs["speaker_sec"] > 0 and withs["total_sec"] > base["total_sec"]
    assert call(server, "POST", "/api/estimate", {"kind": "clips", "upload_id": up, "options": {"speakers": 99}})[0] == 400


def test_videos_are_a_separate_step_that_needs_a_finished_clips_run(server, tmp_path):
    assert web.build_argv("videos", {}, None, tmp_path)[0] == "videos"
    folder = tmp_path / "job"
    (folder / "out").mkdir(parents=True)
    parent = web.Job("clips", folder)
    parent.status = "done"
    server.state.jobs[parent.id] = parent
    assert web.wants_video(parent) is None  # no clips.json yet
    assert call(server, "POST", "/api/start", {"kind": "videos", "plan_job": parent.id})[0] == 400
    (folder / "out" / "clips.json").write_text(json.dumps({"options": {"formats": ["audio", "srt", "video"]}, "clips": [], "alternates": []}), encoding="utf-8")
    assert web.wants_video(parent) is True
    status, body = call(server, "GET", f"/api/job/{parent.id}")
    assert status == 200 and json.loads(body)["video"] is True
    (folder / "out" / "clips.json").write_text(json.dumps({"options": {"formats": ["audio"]}, "clips": [], "alternates": []}), encoding="utf-8")
    assert web.wants_video(parent) is False


def test_env_reports_whether_speaker_labels_are_installed(server):
    assert "speakers" in json.loads(call(server, "GET", "/api/env")[1])


def _job_with_original_and_edited(server, tmp_path, stem):
    from podclip import srt
    folder = tmp_path / "job"
    (folder / "out").mkdir(parents=True)
    srt.write(folder / "out" / f"{stem}.srt", [srt.Cue(100, 110, "原始字幕夠長的一句", "講者1"), srt.Cue(110, 120, "另一人的一句話", "講者2")])
    srt.write(folder / "out" / "episode_edited.srt", [srt.Cue(60, 70, "剪輯後字幕", "講者1")])
    job = web.Job("plan", folder)
    job.status = "done"
    server.state.jobs[job.id] = job
    return job, folder


@pytest.mark.parametrize("stem", ["第五集", "podcast_01"])  # both sort after "episode_edited"
def test_edited_subtitles_are_never_mistaken_for_the_original(server, tmp_path, stem, monkeypatch):
    from podclip import voices
    job, folder = _job_with_original_and_edited(server, tmp_path, stem)
    speakers = web.read_speakers(job)
    assert [s["label"] for s in speakers] == ["講者1", "講者2"] and speakers[0]["clips"][0]["start"] == 100.0
    argv = web.build_argv("render", {"format": ".mp3"}, None, folder)
    assert argv[argv.index("--srt") + 1].endswith(f"{stem}.srt")
    (folder / "out" / "plan.json").write_text(json.dumps({"duration": 200.0, "cuts": [{"start": 105, "end": 108, "kind": "silence"}]}), encoding="utf-8")
    assert web.read_plan(job)["cuts"][0]["text"] == "原始字幕夠長的一句"  # the excerpt comes from the original timeline
    seen = {}
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x")
    job.source = audio
    monkeypatch.setattr(voices, "remember", lambda a, cues, m, where=None: seen.update(first=cues[0].start) or {"小明": True})
    web.rename_speakers(job, {"講者1": "小明"}, remember=True, voices_file=tmp_path / "v.json")
    assert seen["first"] == 100.0  # the voice is learned from the original audio's times
