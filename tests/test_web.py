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
