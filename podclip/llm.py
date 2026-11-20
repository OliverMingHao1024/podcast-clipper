"""LLM access.

The pipeline only needs ``backend.complete(system, user) -> str``. Backends:

* ``ClaudeCLI``  - the locally installed, already logged-in ``claude`` CLI in print mode, so the
  user's own subscription is used through the vendor's official client. This program never reads,
  stores or forwards credentials. All tools are disabled: the model can only answer with text.
* ``CommandBackend`` - any command that reads the prompt on stdin and prints the answer on stdout
  (wrap another vendor CLI, or a script that calls an API).

The transcript is untrusted input, so callers must validate whatever comes back (finder.py does).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
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
