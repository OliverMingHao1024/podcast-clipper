"""LLM access.

The pipeline only needs ``backend.complete(system, user) -> str``. Backends:

* ``ClaudeCLI``  - the locally installed, already logged-in ``claude`` CLI in print mode, so the
  user's own subscription is used through the vendor's official client. This program never reads,
  stores or forwards credentials. All tools are disabled: the model can only answer with text.
* ``CommandBackend`` - any command that reads the prompt on stdin and prints the answer on stdout
  (wrap another vendor CLI, or a script that calls an API). Named commands come from PRESETS (verified
  ones) and from a machine-local ``podclip-backends.json``; the user logs in to whichever CLI they use,
  this program never touches credentials.

The transcript is untrusted input, so callers must validate whatever comes back (finder.py does).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Protocol


class LLMError(RuntimeError):
    pass


class LLMBackend(Protocol):
    def complete(self, system: str, user: str) -> str: ...


def _clean_env() -> dict[str, str]:
    """Environment for the claude CLI without CLAUDE*/ANTHROPIC* variables.

    When podclip is started from inside another Claude session those variables point the child at
    the parent's endpoint and auth, so the CLI would ignore the user's own stored login."""
    return {k: v for k, v in os.environ.items() if not k.upper().startswith(("CLAUDE", "ANTHROPIC"))}


def _run(cmd: list[str], stdin: str, timeout: float, env: dict[str, str] | None = None) -> str:
    try:
        proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True, encoding="utf-8",
                              timeout=timeout, env=env)
    except FileNotFoundError as error:
        raise LLMError(f"command not found: {cmd[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise LLMError(f"{cmd[0]} timed out after {timeout:.0f}s") from error
    if proc.returncode != 0:
        detail = proc.stderr.strip()
        if not detail:  # the claude CLI reports errors as JSON on stdout
            try:
                detail = str(json.loads(proc.stdout).get("result", ""))
            except (json.JSONDecodeError, AttributeError):
                detail = proc.stdout.strip()
        raise LLMError(f"{cmd[0]} exited {proc.returncode}: {detail[:300]}")
    return proc.stdout


class ClaudeCLI:
    def __init__(self, model: str | None = None, timeout: float = 600, executable: str = "claude"):
        self.model, self.timeout, self.executable = model, timeout, executable

    def complete(self, system: str, user: str) -> str:
        exe = shutil.which(self.executable)
        if not exe:
            raise LLMError("claude CLI not found on PATH; install Claude Code and log in first")
        cmd = [exe, "-p", "--output-format", "json", "--tools", "", "--disable-slash-commands",
               "--no-session-persistence", "--strict-mcp-config", "--setting-sources", "",
               "--append-system-prompt", system]
        if self.model:
            cmd += ["--model", self.model]
        raw = _run(cmd, user, self.timeout, env=_clean_env())
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise LLMError("claude CLI did not return JSON") from error
        if payload.get("is_error"):
            raise LLMError(f"claude CLI error: {str(payload.get('result'))[:300]}")
        result = payload.get("result")
        if not isinstance(result, str):
            raise LLMError("claude CLI JSON has no text result")
        return result


class CommandBackend:
    def __init__(self, command: list[str], timeout: float = 600):
        if not command:
            raise ValueError("empty command")
        self.command, self.timeout = command, timeout

    def complete(self, system: str, user: str) -> str:
        return _run(self.command, f"{system}\n\n{user}", self.timeout)


# --------------------------------------------------------------- named backends ---

# Only commands that were run end to end belong here. codex is an agent, so it is pinned to a read-only
# sandbox and given no persisted session or user config; claude is handled by ClaudeCLI (tools disabled).
PRESETS: dict[str, list[str]] = {
    "codex": ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only",
              "--ignore-user-config", "--color", "never", "-"],
}
RESERVED = ("claude", "cmd")
_NAME = re.compile(r"[a-z][a-z0-9_-]{0,19}")


def custom_config_path() -> Path:
    env = os.environ.get("PODCLIP_BACKENDS")
    return Path(env) if env else Path(__file__).resolve().parent.parent / "podclip-backends.json"


def custom_backends() -> dict[str, list[str]]:
    """Machine-local ``{"name": ["command", "arg", ...]}``; the command reads the prompt on stdin and prints
    the answer on stdout. Never taken from the browser. Bad entries are ignored."""
    path = custom_config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {name: argv for name, argv in data.items()
            if isinstance(name, str) and _NAME.fullmatch(name) and name not in RESERVED
            and isinstance(argv, list) and argv and all(isinstance(a, str) and a for a in argv)}


def named_commands() -> dict[str, list[str]]:
    return {**PRESETS, **custom_backends()}


def backend_status() -> list[dict]:
    """Every selectable backend and whether its program is on PATH right now."""
    rows = [("claude", "claude")] + [(n, argv[0]) for n, argv in named_commands().items()]
    return [{"name": n, "ready": shutil.which(exe) is not None} for n, exe in rows]


def make_backend(name: str, *, model: str | None = None, cmd: str | None = None) -> LLMBackend:
    if name == "claude":
        return ClaudeCLI(model=model)
    if name == "cmd":
        if not cmd:
            raise ValueError("--backend cmd needs --cmd, e.g. --cmd \"mytool --stdin\"")
        return CommandBackend(shlex.split(cmd))
    argv = named_commands().get(name)
    if argv is None:
        raise ValueError(f"unknown backend {name!r}; known: {', '.join(['claude', 'cmd', *named_commands()])}")
    exe = shutil.which(argv[0])
    if exe is None:
        raise LLMError(f"{argv[0]} not found on PATH; install it and log in first")
    return CommandBackend([exe, *argv[1:]])
