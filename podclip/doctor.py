"""Self-check: is this computer ready to run podclip, and if not, what should the user do?

Each check returns {"id", "name", "status", "detail", "fix"} with status ok / warn / fail / info. Nothing is
installed or changed; the optional AI test sends one tiny prompt to the chosen backend.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from importlib.util import find_spec
from pathlib import Path

from .llm import LLMError, backend_status, make_backend

MIN_FREE_GB = 5
WHISPER_MODELS = ("tiny", "base", "small", "medium")


def _row(id_: str, name: str, status: str, detail: str = "", fix: str = "") -> dict:
    return {"id": id_, "name": name, "status": status, "detail": detail, "fix": fix}


def _ffmpeg_text(exe: str, *args: str) -> str:
    try:
        proc = subprocess.run([exe, "-hide_banner", *args], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout + proc.stderr


def _install_hint(tool: str) -> str:
    if sys.platform == "darwin":
        return f"macOS：在終端機執行 brew install {tool}"
    if sys.platform == "win32":
        return f"Windows：在命令提示字元執行 winget install ffmpeg，裝完重新開啟啟動檔"
    return f"請用系統的套件管理員安裝 {tool}"


def check_python() -> dict:
    ok = sys.version_info >= (3, 10)
    version = platform.python_version()
    return _row("python", "Python", "ok" if ok else "fail", f"{version}（{platform.system()} {platform.machine()}）",
                "" if ok else "需要 Python 3.10 以上，請到 python.org 安裝新版")


def check_ffmpeg() -> list[dict]:
    rows = []
    exe, probe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not exe:
        return [_row("ffmpeg", "ffmpeg", "fail", "找不到", _install_hint("ffmpeg"))]
    first = _ffmpeg_text(exe, "-version").splitlines()[:1]
    rows.append(_row("ffmpeg", "ffmpeg", "ok", first[0] if first else exe))
    rows.append(_row("ffprobe", "ffprobe", "ok" if probe else "fail", probe or "找不到", "" if probe else _install_hint("ffmpeg")))
    encoders, filters = _ffmpeg_text(exe, "-encoders"), _ffmpeg_text(exe, "-filters")
    for ident, label, haystack, needle, why in (
        ("mp3", "mp3 編碼（libmp3lame）", encoders, "libmp3lame", "輸出 mp3 需要"),
        ("x264", "影片編碼（libx264）", encoders, "libx264", "輸出波形影片需要"),
        ("subtitles", "字幕燒錄（libass）", filters, " subtitles ", "波形影片燒入字幕需要"),
    ):
        found = needle in haystack
        rows.append(_row(ident, label, "ok" if found else "warn", "可用" if found else f"這份 ffmpeg 沒有，{why}",
                         "" if found else "改用完整版 ffmpeg（例如 Homebrew 或 winget 版）"))
    return rows


def check_whisper() -> list[dict]:
    if find_spec("faster_whisper") is None:
        return [_row("whisper", "語音辨識（faster-whisper）", "fail", "尚未安裝",
                     "用 start.bat／start.command 啟動會自動安裝，或執行 pip install -e \".[asr]\"")]
    rows = [_row("whisper", "語音辨識（faster-whisper）", "ok", "已安裝")]
    try:
        import ctranslate2
        gpus = ctranslate2.get_cuda_device_count()
    except Exception:  # noqa: BLE001 - optional detail only
        gpus = 0
    rows.append(_row("gpu", "顯示卡加速（CUDA）", "info", f"偵測到 {gpus} 張可用" if gpus else "未偵測到，會使用 CPU",
                     "" if gpus else "沒有 NVIDIA 顯示卡也能用，只是辨識較慢"))
    hub = Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub"
    cached = [m for m in WHISPER_MODELS if (hub / f"models--Systran--faster-whisper-{m}").is_dir()]
    rows.append(_row("models", "已下載的辨識模型", "info", "、".join(cached) if cached else "尚無",
                     "" if cached else "第一次辨識時會自動從網路下載所選模型"))
    return rows


def check_speakers() -> dict:
    from . import diarize
    if not diarize.available():
        return _row("speakers", "說話者辨識（選用）", "info", "尚未安裝",
                    "用 start.bat／start.command 重新啟動會自動安裝，或執行 pip install -e \".[speakers]\"")
    folder = diarize.model_dir()
    have = all((folder / spec["name"]).is_file() for spec in (diarize.SEGMENTATION, diarize.EMBEDDING))
    return _row("speakers", "說話者辨識（選用）", "ok", "已安裝，模型已下載" if have else "已安裝，第一次使用時會下載約 46 MB 的模型")


def check_backends() -> dict:
    status = backend_status()
    ready = [b["name"] for b in status if b["ready"]]
    missing = [b["name"] for b in status if not b["ready"]]
    if ready:
        return _row("ai", "AI 命令列工具", "ok", "可用：" + "、".join(ready) + (f"；未安裝：{'、'.join(missing)}" if missing else ""),
                    "已安裝不代表已登入，可用「連 AI 一起測」確認登入狀態")
    return _row("ai", "AI 命令列工具", "warn", "找不到任何一個（" + "、".join(missing) + "）",
                "安裝並登入 claude 或 codex；沒有也能做整集剪輯的沉默與贅詞（取消「AI 協助」）")


def check_ai(backend_name: str) -> dict:
    """One tiny real call, so an expired login shows up here instead of in the middle of a long run."""
    name = f"AI 連線測試（{backend_name}）"
    try:
        backend = make_backend(backend_name)
        backend.timeout = 90  # type: ignore[attr-defined]
        start = time.time()
        reply = backend.complete("只輸出 JSON，不要其他文字。", '請回覆 {"ok": true}')
    except (LLMError, ValueError) as error:
        return _row("ai-call", name, "fail", str(error)[:300], "常見原因是登入過期：請在終端機重新登入該工具後再試")
    if not reply.strip():
        return _row("ai-call", name, "fail", "回覆是空的", "請在終端機直接執行該工具確認是否正常")
    return _row("ai-call", name, "ok", f"正常，約 {time.time() - start:.0f} 秒")


def check_workdir(workdir: Path) -> dict:
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        probe = workdir / ".write-test"
        probe.write_text("x")
        probe.unlink()
        free = shutil.disk_usage(workdir).free / 1024 ** 3
    except OSError as error:
        return _row("workdir", "工作資料夾", "fail", f"{workdir}：{error}", "確認資料夾可寫入")
    if free < MIN_FREE_GB:
        return _row("workdir", "工作資料夾", "warn", f"{workdir}（剩餘 {free:.1f} GB）", "剩餘空間偏少，長節目的成品可能放不下")
    return _row("workdir", "工作資料夾", "ok", f"{workdir}（剩餘 {free:.0f} GB）")


def run_checks(workdir: Path, *, ai: bool = False, backend: str = "claude") -> list[dict]:
    rows = [check_python(), *check_ffmpeg(), *check_whisper(), check_speakers(), check_backends(), check_workdir(workdir)]
    if ai:
        rows.append(check_ai(backend))
    return rows
