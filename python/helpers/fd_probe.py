import json
import os
import platform
import resource
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import importlib.metadata as importlib_metadata
except Exception:  # pragma: no cover
    importlib_metadata = None  # type: ignore


_LOCK = threading.Lock()
_HEADER_WRITTEN = False
_LOG_PATH: Path | None = None


def enabled() -> bool:
    return os.getenv("A0_FD_PROBE", "").strip() in {"1", "true", "TRUE", "yes", "YES"}


def _fd_dir() -> str | None:
    if os.path.isdir("/proc/self/fd"):
        return "/proc/self/fd"
    if os.path.isdir("/dev/fd"):
        return "/dev/fd"
    return None


def _safe_readlink(path: str) -> str:
    try:
        return os.readlink(path)
    except Exception:
        return "unknown"


def _classify_target(target: str) -> str:
    if target.startswith("socket:"):
        return "socket"
    if target.startswith("pipe:"):
        return "pipe"
    if "pty" in target or target.startswith("/dev/pts/"):
        return "pty"
    if target.startswith("anon_inode:"):
        return "anon_inode"
    return "file"


def _git_sha() -> str | None:
    head_path = Path(".git/HEAD")
    try:
        if not head_path.exists():
            return None
        head = head_path.read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref_path = Path(".git") / head.removeprefix("ref: ").strip()
            if ref_path.exists():
                return ref_path.read_text(encoding="utf-8").strip()[:40]
            return None
        return head[:40]
    except Exception:
        return None


def _version(pkg: str) -> str | None:
    if importlib_metadata is None:
        return None
    try:
        return importlib_metadata.version(pkg)
    except Exception:
        return None


def _snapshot_fd_state() -> dict[str, Any]:
    fd_root = _fd_dir()
    if fd_root is None:
        return {"fd_count": -1, "fd_types": {}, "top_targets": []}

    entries = []
    try:
        entries = os.listdir(fd_root)
    except Exception:
        return {"fd_count": -1, "fd_types": {}, "top_targets": []}

    fd_types: dict[str, int] = {}
    target_counts: dict[str, int] = {}
    for fd in entries:
        target = _safe_readlink(os.path.join(fd_root, fd))
        kind = _classify_target(target)
        fd_types[kind] = fd_types.get(kind, 0) + 1
        target_counts[target] = target_counts.get(target, 0) + 1

    top_targets = sorted(target_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    return {
        "fd_count": len(entries),
        "fd_types": fd_types,
        "top_targets": [{"target": target, "count": count} for target, count in top_targets],
    }


def _log_file() -> Path:
    global _LOG_PATH
    if _LOG_PATH is not None:
        return _LOG_PATH
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = Path("tmp/fd-probe")
    out_dir.mkdir(parents=True, exist_ok=True)
    _LOG_PATH = out_dir / f"{ts}-{os.getpid()}.jsonl"
    return _LOG_PATH


def _write_event(payload: dict[str, Any]) -> None:
    path = _log_file()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _write_header_once() -> None:
    global _HEADER_WRITTEN
    if _HEADER_WRITTEN:
        return
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    _write_event(
        {
            "event": "probe_header",
            "ts": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
            "os": platform.platform(),
            "ulimit_soft": soft,
            "ulimit_hard": hard,
            "git_sha": _git_sha(),
            "litellm_version": _version("litellm"),
            "httpx_version": _version("httpx"),
        }
    )
    _HEADER_WRITTEN = True


def snapshot(phase: str, subsystem: str, **extra: Any) -> None:
    if not enabled():
        return
    with _LOCK:
        _write_header_once()
        payload = {
            "event": "fd_snapshot",
            "ts": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
            "phase": phase,
            "subsystem": subsystem,
            "monotonic_s": round(time.monotonic(), 3),
            **_snapshot_fd_state(),
            "extra": extra or {},
        }
        _write_event(payload)
