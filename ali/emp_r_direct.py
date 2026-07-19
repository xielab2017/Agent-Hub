"""Opt-in R Direct adapter with a fixed JSON contract and operation allowlist."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


ALLOWED_OPERATIONS = {"preflight", "summarize_table", "preview_dataset"}


@dataclass(frozen=True)
class RDirectResult:
    success: bool
    operation: str
    data: dict[str, Any]
    artifacts: tuple[dict[str, Any], ...] = ()
    versions: dict[str, str] | None = None
    log: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RDirectResult":
        return cls(
            success=payload.get("success") is True,
            operation=str(payload.get("operation") or ""),
            data=dict(payload.get("data") or {}),
            artifacts=tuple(dict(item) for item in payload.get("artifacts") or []),
            versions={str(k): str(v) for k, v in (payload.get("versions") or {}).items()},
            log=str(payload.get("log") or ""),
        )


class RDirectError(RuntimeError):
    pass


def _allowed_path(path: Path, roots: Iterable[Path]) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("R Direct input must be a regular file")
    allowed = [root.expanduser().resolve(strict=True) for root in roots]
    resolved_text = os.path.normcase(str(resolved))
    if not any(
        os.path.commonpath([os.path.normcase(str(root)), resolved_text]) == os.path.normcase(str(root))
        for root in allowed
    ):
        raise ValueError("R Direct input is outside allowed roots")
    return resolved


def _stop_process(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        break_event = getattr(signal, "CTRL_BREAK_EVENT", None)
        if break_event is not None:
            try:
                process.send_signal(break_event)
                return
            except OSError:
                pass
        process.terminate()
        return
    os.killpg(process.pid, signal.SIGTERM)


def _kill_process(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        process.kill()
    else:
        os.killpg(process.pid, signal.SIGKILL)


class RDirectRunner:
    def __init__(
        self,
        runner_script: Path,
        *,
        enabled: bool = False,
        rscript: str = "Rscript",
        allowed_roots: Iterable[Path] = (),
        timeout_seconds: int = 300,
        state_dir: Optional[Path] = None,
    ) -> None:
        self.runner_script = runner_script.expanduser().resolve(strict=True)
        self.enabled = bool(enabled)
        self.rscript = rscript
        self.allowed_roots = tuple(allowed_roots)
        self.timeout_seconds = max(1, min(int(timeout_seconds), 7200))
        self.state_dir = state_dir.expanduser().resolve() if state_dir else None

    def preflight(self) -> dict[str, Any]:
        executable = shutil.which(self.rscript)
        return {
            "enabled": self.enabled,
            "rscript": executable or "",
            "runner": str(self.runner_script),
            "ready": self.enabled and bool(executable) and self.runner_script.is_file(),
            "operations": sorted(ALLOWED_OPERATIONS),
        }

    def run(self, operation: str, params: Optional[dict[str, Any]] = None) -> RDirectResult:
        if not self.enabled:
            raise RDirectError("R Direct is disabled")
        if operation not in ALLOWED_OPERATIONS:
            raise ValueError("R Direct operation is not allowlisted")
        if not shutil.which(self.rscript):
            raise RDirectError("Rscript is unavailable")
        values = dict(params or {})
        path_fields = {"summarize_table": ("path",), "preview_dataset": ("data_path", "metadata_path")}
        for field in path_fields.get(operation, ()):
            raw_path = Path(str(values.get(field) or ""))
            if not self.allowed_roots:
                raise ValueError("R Direct allowed roots are not configured")
            values[field] = str(_allowed_path(raw_path, self.allowed_roots))
        if operation in {"summarize_table", "preview_dataset"}:
            delimiter = str(values.get("delimiter") or "auto")
            if delimiter not in {"auto", ",", "\t", ";"}:
                raise ValueError("unsupported table delimiter")
            values["delimiter"] = delimiter
        if operation == "preview_dataset":
            data_type = str(values.get("data_type") or "normal")
            if data_type not in {"tax", "normal"}:
                raise ValueError("unsupported data_type")
            values["data_type"] = data_type
        payload = {"contract_version": "1.0", "operation": operation, "params": values}
        root = self.state_dir
        if root:
            root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="emp-r-direct-", dir=str(root) if root else None) as temporary:
            popen_options: dict[str, Any] = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "cwd": temporary,
                "text": True,
                "env": {**os.environ, "R_PROFILE_USER": "", "R_ENVIRON_USER": ""},
            }
            if os.name == "nt":
                popen_options["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            else:
                popen_options["start_new_session"] = True
            process = subprocess.Popen(
                [self.rscript, "--vanilla", str(self.runner_script)],
                **popen_options,
            )
            try:
                stdout, stderr = process.communicate(json.dumps(payload), timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                _stop_process(process)
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    _kill_process(process)
                    process.communicate()
                raise RDirectError("R Direct operation timed out") from exc
        if process.returncode != 0:
            raise RDirectError(f"R Direct failed: {stderr[-1000:]}")
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RDirectError("R Direct returned invalid JSON") from exc
        if not isinstance(result, dict) or result.get("success") is not True:
            raise RDirectError(str(result.get("error") if isinstance(result, dict) else "R Direct failed"))
        result["log"] = stderr[-4000:]
        return RDirectResult.from_dict(result)
