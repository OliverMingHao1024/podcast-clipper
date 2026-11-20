"""podclip web: a browser front end for people who do not use a terminal.

It is a thin wrapper that runs the existing CLI as a subprocess, so the pipeline logic lives in one place.
Safety properties (the project otherwise has no server):

* binds 127.0.0.1 only; requests whose Host / Origin is not this server are refused (DNS rebinding, CSRF);
* every API call needs a random per-run token, served only inside the page itself;
* the browser can only choose from whitelisted options; it can never pass a path, a command or --cmd;
* downloads are limited to files under one job's ``out`` folder;
* model-written text is only ever put into the page with ``textContent``.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.util import find_spec
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from .cli import AUDIO_EXT
from .llm import backend_status
from .render import ASPECTS
from .web_page import PAGE

MAX_UPLOAD = 4 * 1024 ** 3
MAX_LOG_LINES = 2000
_HEX = re.compile(r"[0-9a-f]{32}")
WHISPER_MODELS = ("tiny", "base", "small", "medium")
LANGUAGES = ("", "zh", "en", "ja", "ko")
TITLE_LANGUAGES = ("繁體中文", "简体中文", "English", "日本語")
OUT_EXT = (".mp3", ".m4a", ".wav")
SUBTITLES = "subtitles.srt"  # the optional subtitle file attached to an upload
MAX_SUBTITLES = 20 * 1024 * 1024
_WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


AUDIO_TYPES = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav", ".flac": "audio/flac", ".ogg": "audio/ogg",
               ".opus": "audio/ogg", ".aac": "audio/aac", ".mp4": "audio/mp4", ".webm": "audio/webm"}


def audio_duration(path: Path) -> float | None:
    """Length in seconds via ffprobe, or None when it cannot be read (the page then shows no estimate)."""
    from .edit import probe_duration
    from .render import RenderError
    try:
        return probe_duration(path)
    except (RenderError, OSError):
        return None


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """(start, end) for a single ``bytes=a-b`` / ``bytes=a-`` / ``bytes=-n`` range, None for no or an unusable header
    (the whole file is then sent), ValueError when the range lies outside the file."""
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", (header or "").strip())
    if not match or not (match[1] or match[2]) or size == 0:
        return None
    if not match[1]:  # last n bytes
        n = int(match[2])
        if n == 0:
            raise ValueError("empty range")
        return max(size - n, 0), size - 1
    start = int(match[1])
    end = min(int(match[2]) if match[2] else size - 1, size - 1)
    if start >= size or start > end:
        raise ValueError("unsatisfiable range")
    return start, end


class Job:
    def __init__(self, kind: str, folder: Path):
        self.source: Path | None = None  # the uploaded audio this job works on (set by start_job)
        self.id = uuid.uuid4().hex
        self.kind = kind
        self.folder = folder
        self.status = "running"
        self.lines: list[str] = []
        self.dropped = 0
        self.started = time.time()
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()

    def add(self, line: str) -> None:
        with self.lock:
            self.lines.append(line)
            if len(self.lines) > MAX_LOG_LINES:
                del self.lines[0]
                self.dropped += 1


class State:
    def __init__(self, workdir: Path, token: str):
        self.workdir = workdir
        self.token = token
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def job(self, job_id: str) -> Job:
        if not _HEX.fullmatch(job_id) or job_id not in self.jobs:
            raise ApiError(404, "unknown job")
        return self.jobs[job_id]

    def busy(self) -> bool:
        return any(j.status == "running" for j in self.jobs.values())

    def upload_file(self, upload_id: str) -> Path:
        folder = self.workdir / "uploads" / upload_id
        if not _HEX.fullmatch(upload_id) or not folder.is_dir():
            raise ApiError(400, "unknown upload")
        files = [p for p in folder.iterdir() if p.is_file() and p.name != SUBTITLES]
        if len(files) != 1:
            raise ApiError(400, "unknown upload")
        return files[0]

    def upload_srt(self, upload_id: str) -> Path | None:
        path = self.upload_file(upload_id).parent / SUBTITLES
        return path if path.is_file() else None


# ----------------------------------------------------------------- option checks ---

def _choice(o: dict, key: str, allowed: tuple, default):
    value = o.get(key, default)
    if value not in allowed:
        raise ApiError(400, f"bad value for {key}")
    return value


def _number(o: dict, key: str, low: float, high: float, default: float) -> float:
    value = o.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ApiError(400, f"bad value for {key}")
    return value


def _backend_arg(o: dict) -> list[str]:
    names = tuple(b["name"] for b in backend_status())
    return ["--backend", _choice(o, "backend", names, "claude")]


def _srt_arg(o: dict, audio: Path) -> list[str]:
    """``--srt`` for the subtitle file attached to this upload, when the page asked to use it."""
    if not o.get("use_srt"):
        return []
    path = audio.parent / SUBTITLES
    if not path.is_file():
        raise ApiError(400, "no subtitle file was attached")
    return ["--srt", str(path)]


def _common(o: dict) -> list[str]:
    args = [*_backend_arg(o),
            "--device", _choice(o, "device", ("cpu", "cuda"), "cpu"),
            "--whisper-model", _choice(o, "whisper_model", WHISPER_MODELS, "small"),
            "--title-language", _choice(o, "title_language", TITLE_LANGUAGES, "繁體中文")]
    if language := _choice(o, "language", LANGUAGES, ""):
        args += ["--language", language]
    return args


def build_argv(kind: str, o: dict, audio: Path | None, folder: Path) -> list[str]:
    out = folder / "out"
    if kind == "clips":
        formats = [f for f in ("audio", "srt", "video") if f in (o.get("formats") or [])]
        if not formats:
            raise ApiError(400, "choose at least one output")
        low, high = _number(o, "min_sec", 10, 600, 45), _number(o, "max_sec", 10, 900, 180)
        if low > high:
            raise ApiError(400, "min_sec is larger than max_sec")
        return ["run", str(audio), "--out", str(out), *_srt_arg(o, audio), "--formats", ",".join(formats),
                "--max-clips", str(int(_number(o, "max_clips", 1, 30, 10))),
                "--min-sec", str(low), "--max-sec", str(high), "--aspect", _choice(o, "aspect", tuple(ASPECTS), "9:16"),
                *_common(o)]
    if kind == "plan":
        return ["edit-plan", str(audio), "--out", str(out), *_srt_arg(o, audio), *_common(o), *(["--no-ai"] if o.get("no_ai") else [])]
    if kind == "render":
        ext = _choice(o, "format", OUT_EXT, ".mp3")
        srts = sorted(out.glob("*.srt"))
        return ["edit-render", str(out / "plan.json"), "--out", str(out / f"episode_edited{ext}"),
                *(["--srt", str(srts[0])] if srts else []), *(["--no-loudnorm"] if o.get("no_loudnorm") else [])]
    if kind == "notes":
        subs = next((p for p in (out / "episode_edited.srt", *sorted(out.glob("*.srt"))) if p.is_file()), None)
        if subs is None:
            raise ApiError(400, "no subtitles to write notes from")
        return ["notes", str(subs), "--out", str(out / "episode_notes.txt"), *_backend_arg(o),
                "--title-language", _choice(o, "title_language", TITLE_LANGUAGES, "繁體中文")]
    if kind == "more":
        return ["more", str(out), "--count", "1"]
    raise ApiError(400, "unknown kind")


# ------------------------------------------------------------------------- jobs ---

def _pump(job: Job) -> None:
    assert job.proc and job.proc.stdout
    for line in job.proc.stdout:
        job.add(line.rstrip())
    code = job.proc.wait()
    if job.status == "running":
        job.status = "done" if code == 0 else "failed"


def start_job(state: State, kind: str, o: dict) -> Job:
    with state.lock:
        if state.busy():
            raise ApiError(409, "another job is still running")
        audio = None
        source = None
        if kind in ("render", "notes", "more"):
            parent = state.job(str(o.get("plan_job", "")))
            folder, source = parent.folder, parent.source
            needed = {"render": "plan.json", "more": "clips.json"}.get(kind)
            if not (folder / "out").is_dir() or (needed and not (folder / "out" / needed).is_file()):
                raise ApiError(400, "that job has no output to work from")
        else:
            audio = source = state.upload_file(str(o.get("upload_id", "")))
            folder = state.workdir / "jobs" / uuid.uuid4().hex
            folder.mkdir(parents=True)
        argv = build_argv(kind, o, audio, folder)
        job = Job(kind, folder)
        job.source = source
        env ={**os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1", "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
               "HF_HUB_DISABLE_TELEMETRY": "1", "HF_HUB_VERBOSITY": "error", "PYTHONWARNINGS": "ignore",
               "PODCLIP_STATS": str(state.workdir / "speed.json"),
               "PYTHONPATH": os.pathsep.join(filter(None, [str(Path(__file__).resolve().parent.parent),
                                                           os.environ.get("PYTHONPATH", "")]))}
        job.proc = subprocess.Popen([sys.executable, "-m", "podclip.cli", *argv], cwd=folder, env=env, text=True,
                                    encoding="utf-8", errors="replace", stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    start_new_session=sys.platform != "win32")  # own process group, so cancel reaches children
        state.jobs[job.id] = job
        threading.Thread(target=_pump, args=(job,), daemon=True).start()
        return job


def cancel_job(job: Job) -> None:
    if job.proc and job.status == "running":
        job.status = "cancelled"
        if sys.platform == "win32":  # also stop ffmpeg / claude children
            subprocess.run(["taskkill", "/PID", str(job.proc.pid), "/T", "/F"], capture_output=True)
        else:
            try:
                os.killpg(job.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def job_files(job: Job) -> list[dict]:
    out = job.folder / "out"
    if not out.is_dir():
        return []
    return [{"path": p.relative_to(out).as_posix(), "size": p.stat().st_size}
            for p in sorted(out.rglob("*")) if p.is_file() and not any(part.startswith(".") for part in p.relative_to(out).parts)]


def alternates_left(job: Job) -> int | None:
    """How many alternate clips an earlier `run` kept, or None when this job has no clips.json."""
    try:
        data = json.loads((job.folder / "out" / "clips.json").read_text(encoding="utf-8"))
        return len(data.get("alternates") or [])
    except (OSError, ValueError, AttributeError):
        return None


def bundle_files(job: Job) -> list[Path]:
    """Files for the "download everything" ZIP: the edited episode and its extras, or every clip file."""
    out = (job.folder / "out").resolve()
    files = [p for p in sorted(out.rglob("*"))
             if p.is_file() and not p.is_symlink() and not any(part.startswith(".") for part in p.relative_to(out).parts)]
    edited = [p for p in files if p.name.startswith("episode_edited")]
    if edited:
        return edited + [p for p in files if p.name in ("episode_notes.txt", "plan.md")]
    return [p for p in files if p.name != "plan.json"]


def read_plan(job: Job) -> dict:
    from . import edit, srt
    out = job.folder / "out"
    try:
        data = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ApiError(400, "no readable plan yet") from error
    srts = sorted(out.glob("*.srt"))
    cues = srt.read(srts[0]) if srts else []
    cuts = [{"i": i, "start": c["start"], "end": c["end"], "kind": c["kind"], "reason": c.get("reason", ""),
             "apply": bool(c.get("apply", True)), "text": edit._excerpt(cues, c["start"], c["end"], 60)}
            for i, c in enumerate(data["cuts"])]
    return {"duration": data["duration"], "cuts": cuts, "outline": data.get("outline") or []}


def save_plan_flags(job: Job, flags: list) -> None:
    path = job.folder / "out" / "plan.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(flags, list) or len(flags) != len(data["cuts"]) or not all(isinstance(f, bool) for f in flags):
        raise ApiError(400, "apply list does not match the plan")
    for cut, flag in zip(data["cuts"], flags):
        cut["apply"] = flag
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def environment() -> dict:
    return {"ffmpeg": bool(shutil.which("ffmpeg")), "backends": backend_status(),
            "whisper": find_spec("faster_whisper") is not None, "platform": sys.platform}


# ---------------------------------------------------------------------- handler ---

class Handler(BaseHTTPRequestHandler):
    server_version = "podclip"
    protocol_version = "HTTP/1.1"

    @property
    def state(self) -> State:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, *_args) -> None:
        pass

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _check_origin(self) -> None:
        if self.headers.get("Host", "") not in self.server.allowed_hosts:  # type: ignore[attr-defined]
            raise ApiError(403, "bad host")
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{h}" for h in self.server.allowed_hosts}:  # type: ignore[attr-defined]
            raise ApiError(403, "bad origin")

    def _check_token(self, supplied: str | None) -> None:
        if not supplied or not secrets.compare_digest(supplied, self.state.token):
            raise ApiError(403, "bad token")

    def _body(self, limit: int = 1_000_000) -> dict:
        self._body_read = True
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            raise ApiError(413, "body too large")
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError as error:
            raise ApiError(400, "bad json") from error
        if not isinstance(data, dict):
            raise ApiError(400, "bad json")
        return data

    def _dispatch(self, method: str) -> None:
        self._body_read = False
        try:
            self._route(method)
        finally:
            # Keep-alive: a request body nobody read would be parsed as the next request line
            # (the browser's cancel button posts "{}" and then polls on the same connection).
            length = int(self.headers.get("Content-Length") or 0) if method in ("POST", "PUT") else 0
            if length and not self._body_read:
                if length <= 1_000_000:
                    try:
                        self.rfile.read(length)
                    except OSError:
                        self.close_connection = True
                else:
                    self.close_connection = True

    def _route(self, method: str) -> None:
        try:
            self._check_origin()
            url = urlparse(self.path)
            parts = [unquote(p) for p in url.path.split("/")[1:]]
            query = parse_qs(url.query)
            if method == "GET" and url.path == "/":
                return self._send(200, PAGE.replace("__TOKEN__", self.state.token).encode("utf-8"),
                                  "text/html; charset=utf-8")
            if method == "GET" and parts[0] == "zip" and len(parts) == 2:
                self._check_token((query.get("t") or [None])[0])
                return self._zip(parts[1])
            if method == "GET" and parts[0] == "source" and len(parts) == 2:
                self._check_token((query.get("t") or [None])[0])
                return self._source(parts[1])
            if method == "GET" and parts[0] == "files" and len(parts) >= 3:
                self._check_token((query.get("t") or [None])[0])
                return self._file(parts[1], "/".join(parts[2:]), inline=(query.get("inline") or [""])[0] == "1")
            if parts[0] != "api":
                raise ApiError(404, "not found")
            self._check_token(self.headers.get("X-Token"))
            return self._api(method, parts[1:], query)
        except ApiError as error:
            self._json({"error": str(error)}, error.status)
        except ConnectionError:  # the browser closed the connection (seeking an <audio> does this a lot)
            pass
        except Exception as error:  # noqa: BLE001 - never leak a traceback to the browser
            self._json({"error": f"internal error: {type(error).__name__}"}, 500)

    def _api(self, method: str, parts: list[str], query: dict) -> None:
        st = self.state
        route = (method, parts[0] if parts else "")
        if route == ("GET", "env"):
            return self._json({**environment(), "workdir": str(st.workdir)})
        if route == ("GET", "doctor"):
            from .doctor import run_checks
            backend = (query.get("backend") or ["claude"])[0]
            if backend not in tuple(b["name"] for b in backend_status()):
                raise ApiError(400, "unknown backend")
            ai = (query.get("ai") or [""])[0] == "1"
            return self._json({"checks": run_checks(st.workdir, ai=ai, backend=backend)})
        if route == ("POST", "estimate"):
            return self._json(self._estimate(self._body()))
        if route == ("PUT", "subtitles"):
            return self._subtitles((query.get("for") or [""])[0])
        if route == ("PUT", "upload"):
            return self._upload((query.get("name") or [""])[0])
        if route == ("POST", "start"):
            data = self._body()
            kind = data.get("kind")
            options = data.get("options") if isinstance(data.get("options"), dict) else {}
            job = start_job(st, str(kind), {**options, "upload_id": data.get("upload_id"),
                                            "plan_job": data.get("plan_job")})
            return self._json({"job": job.id})
        if len(parts) == 2:
            job = st.job(parts[1])
            if route == ("GET", "job"):
                since = int((query.get("since") or ["0"])[0] or 0)
                with job.lock:
                    start = max(since - job.dropped, 0)
                    lines, total = job.lines[start:], job.dropped + len(job.lines)
                return self._json({"status": job.status, "kind": job.kind, "lines": lines, "next": total,
                                   "alternates": alternates_left(job) if job.status != "running" else None,
                                   "elapsed": int(time.time() - job.started),
                                   "files": job_files(job) if job.status != "running" else []})
            if route == ("POST", "cancel"):
                cancel_job(job)
                return self._json({"ok": True})
            if route == ("GET", "plan"):
                return self._json(read_plan(job))
            if route == ("POST", "plan"):
                save_plan_flags(job, self._body().get("apply"))
                return self._json({"ok": True})
        raise ApiError(404, "not found")

    def _upload(self, name: str) -> None:
        clean = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", Path(name).name).strip(". ")
        if Path(clean).suffix.lower() not in AUDIO_EXT:
            raise ApiError(400, "unsupported file type")
        if clean.split(".")[0].upper() in _WINDOWS_DEVICES:  # "NUL.mp3" would name a device on Windows
            clean = "_" + clean
        self._body_read = True
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_UPLOAD:
            self.close_connection = True  # the body is left unread
            raise ApiError(413, "file is empty or too large")
        upload_id = uuid.uuid4().hex
        folder = self.state.workdir / "uploads" / upload_id
        folder.mkdir(parents=True)
        target, remaining = folder / clean, length
        try:
            with target.open("wb") as fh:
                while remaining:
                    chunk = self.rfile.read(min(1 << 20, remaining))
                    if not chunk:
                        raise ApiError(400, "upload interrupted")
                    fh.write(chunk)
                    remaining -= len(chunk)
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        self._json({"upload_id": upload_id, "name": clean, "duration": audio_duration(target)})

    def _estimate(self, data: dict) -> dict:
        from .estimate import estimate
        kind = data.get("kind")
        if kind not in ("clips", "plan"):
            raise ApiError(400, "unknown kind")
        o = data.get("options") if isinstance(data.get("options"), dict) else {}
        audio = self.state.upload_file(str(data.get("upload_id", "")))
        duration = audio_duration(audio)
        if not duration:
            return {"estimate": None, "duration": None}
        has_srt = bool(o.get("use_srt")) and self.state.upload_srt(str(data["upload_id"])) is not None
        result = estimate(kind, duration, model=_choice(o, "whisper_model", WHISPER_MODELS, "small"),
                          device=_choice(o, "device", ("cpu", "cuda"), "cpu"), has_srt=has_srt,
                          use_ai=not o.get("no_ai"), stats_path=self.state.workdir / "speed.json")
        return {"estimate": result, "duration": duration}

    def _subtitles(self, upload_id: str) -> None:
        """Attach a subtitle file to an upload so the run can skip speech recognition."""
        from . import srt
        audio = self.state.upload_file(upload_id)
        self._body_read = True
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_SUBTITLES:
            self.close_connection = True
            raise ApiError(413, "subtitle file is empty or too large")
        cues = srt.parse(self.rfile.read(length).decode("utf-8-sig", errors="replace"))
        if not cues:
            raise ApiError(400, "cannot read any subtitles from that file")
        srt.write(audio.parent / SUBTITLES, cues)
        duration = audio_duration(audio)
        mismatch = bool(duration and cues[-1].end > duration * 1.05 + 30)
        self._json({"cues": len(cues), "last": cues[-1].end, "duration": duration, "mismatch": mismatch})

    def _zip(self, job_id: str) -> None:
        job = self.state.job(job_id)
        files = bundle_files(job)
        if not files:
            raise ApiError(404, "nothing to download")
        root = (job.folder / "out").resolve()
        with tempfile.TemporaryFile() as tmp:  # anonymous: nothing is left behind on disk
            with zipfile.ZipFile(tmp, "w", allowZip64=True) as zf:
                for path in files:
                    stored = path.suffix.lower() in (".mp3", ".m4a", ".mp4", ".wav", ".ogg", ".flac", ".aac", ".opus")
                    zf.write(path, path.relative_to(root).as_posix(),
                             compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED)
            size = tmp.tell()
            tmp.seek(0)
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''podclip-results.zip")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            shutil.copyfileobj(tmp, self.wfile, 1 << 20)

    def _file(self, job_id: str, rel: str, inline: bool = False) -> None:
        job = self.state.job(job_id)
        root = (job.folder / "out").resolve()
        path = (root / rel).resolve()
        if root not in path.parents or not path.is_file() or any(p.startswith(".") for p in path.relative_to(root).parts):
            raise ApiError(404, "not found")
        self._serve(path, inline=inline)

    def _source(self, job_id: str) -> None:
        """The uploaded audio of a job, for listening in the page. The path is chosen by the server, never the browser."""
        job = self.state.job(job_id)
        if job.source is None or not job.source.is_file() or job.source.suffix.lower() not in AUDIO_TYPES:
            raise ApiError(404, "no playable source")
        self._serve(job.source, inline=True)

    def _serve(self, path: Path, *, inline: bool) -> None:
        """Send a file, honouring one Range so <audio> can seek. Only known audio types are ever shown inline."""
        size = path.stat().st_size
        ctype = AUDIO_TYPES.get(path.suffix.lower()) if inline else None
        try:
            span = parse_range(self.headers.get("Range"), size)
        except ValueError:
            raise ApiError(416, "range not satisfiable")
        start, end = span or (0, size - 1)
        self.send_response(206 if span else 200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(end - start + 1 if size else 0))
        self.send_header("Accept-Ranges", "bytes")
        if span:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        kind = "inline" if ctype else "attachment"
        self.send_header("Content-Disposition", f"{kind}; filename*=UTF-8''{quote(path.name)}")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        remaining = end - start + 1 if size else 0
        with path.open("rb") as fh:
            fh.seek(start)
            while remaining:
                chunk = fh.read(min(1 << 20, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")


def make_server(workdir: Path, port: int = 0) -> ThreadingHTTPServer:
    workdir.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    bound = server.server_address[1]
    server.state = State(workdir.resolve(), secrets.token_urlsafe(24))  # type: ignore[attr-defined]
    server.allowed_hosts = {f"127.0.0.1:{bound}", f"localhost:{bound}"}  # type: ignore[attr-defined]
    return server


def serve(workdir: Path, port: int = 0, open_browser: bool = True) -> int:
    server = make_server(workdir, port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"podclip 已啟動：{url}\n資料夾：{server.state.workdir}\n關閉這個視窗即可停止。", file=sys.stderr)  # type: ignore[attr-defined]
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
