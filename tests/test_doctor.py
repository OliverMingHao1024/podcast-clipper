from podclip import doctor
from podclip.llm import LLMError


def test_rows_are_well_formed(tmp_path):
    rows = doctor.run_checks(tmp_path / "work")
    assert rows and len({r["id"] for r in rows}) == len(rows)
    assert all(r["status"] in {"ok", "warn", "fail", "info"} and r["name"] for r in rows)
    assert all(r["fix"] for r in rows if r["status"] == "fail")  # every failure says what to do


def test_missing_ffmpeg_is_a_failure_with_an_install_hint(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
    row = doctor.check_ffmpeg()[0]
    assert row["status"] == "fail" and "ffmpeg" in row["fix"]


def test_ai_check_reports_login_problems(monkeypatch):
    class Broken:
        timeout = 600

        def complete(self, system, user):
            raise LLMError("OAuth session expired")

    monkeypatch.setattr(doctor, "make_backend", lambda name: Broken())
    row = doctor.check_ai("claude")
    assert row["status"] == "fail" and "expired" in row["detail"] and "登入" in row["fix"]

    class Fine:
        timeout = 600

        def complete(self, system, user):
            return '{"ok": true}'

    monkeypatch.setattr(doctor, "make_backend", lambda name: Fine())
    assert doctor.check_ai("claude")["status"] == "ok"


def test_unwritable_workdir_fails(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert doctor.check_workdir(blocker / "sub")["status"] == "fail"
