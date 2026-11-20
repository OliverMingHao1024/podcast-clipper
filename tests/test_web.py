import http.client
import json
import threading
from pathlib import Path

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
