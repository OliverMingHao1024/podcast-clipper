import json

import pytest

from podclip import llm


def test_custom_backends_are_validated(tmp_path, monkeypatch):
    cfg = tmp_path / "b.json"
    cfg.write_text(json.dumps({"mine": ["mytool", "--stdin"], "claude": ["x"], "cmd": ["x"], "Bad Name": ["x"],
                               "empty": [], "nonstr": ["a", 3]}), encoding="utf-8")
    monkeypatch.setenv("PODCLIP_BACKENDS", str(cfg))
    assert llm.custom_backends() == {"mine": ["mytool", "--stdin"]}
    names = [b["name"] for b in llm.backend_status()]
    assert names[0] == "claude" and "codex" in names and "mine" in names


def test_missing_or_broken_config_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("PODCLIP_BACKENDS", str(tmp_path / "nope.json"))
    assert llm.custom_backends() == {}
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("PODCLIP_BACKENDS", str(tmp_path / "bad.json"))
    assert llm.custom_backends() == {}


def test_make_backend_resolves_names(tmp_path, monkeypatch):
    monkeypatch.setenv("PODCLIP_BACKENDS", str(tmp_path / "none.json"))
    assert isinstance(llm.make_backend("claude"), llm.ClaudeCLI)
    with pytest.raises(ValueError):
        llm.make_backend("nonexistent")
    with pytest.raises(ValueError):
        llm.make_backend("cmd")
    monkeypatch.setattr(llm.shutil, "which", lambda exe: None)
    with pytest.raises(llm.LLMError):
        llm.make_backend("codex")
    monkeypatch.setattr(llm.shutil, "which", lambda exe: f"/bin/{exe}")
    backend = llm.make_backend("codex")
    assert backend.command[0] == "/bin/codex" and backend.command[-1] == "-" and "read-only" in backend.command
