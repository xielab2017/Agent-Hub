"""Constrained HTTP adapter for the EasyMultiProfiler Agent API."""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional


ERROR_MESSAGES = {
    "EMP_UNAVAILABLE": ("EasyMultiProfiler 服务不可用。请先启动本机 EMP API。", "EasyMultiProfiler is unavailable. Start the local EMP API first."),
    "EMP_VERSION_INCOMPATIBLE": ("EMP API 版本不兼容。", "The EMP API version is incompatible."),
    "EMP_AUTH_REQUIRED": ("EMP 服务需要认证。", "EMP authentication is required."),
    "EMP_PATH_NOT_ALLOWED": ("所选路径不在允许的数据目录中。", "The selected path is outside the allowed data roots."),
    "EMP_FILE_TOO_LARGE": ("文件超过 EMP 允许的大小。", "The file exceeds the EMP size limit."),
    "EMP_DATA_VALIDATION_FAILED": ("EMP 数据校验失败。", "EMP data validation failed."),
    "EMP_SESSION_NOT_FOUND": ("EMP 分析会话不存在或已失效。", "The EMP analysis session is missing or expired."),
    "EMP_JOB_FAILED": ("EMP 分析任务失败。", "The EMP analysis job failed."),
    "EMP_JOB_TIMEOUT": ("EMP 分析任务超时。", "The EMP analysis job timed out."),
    "EMP_RESULT_MISSING": ("EMP 未返回预期结果。", "EMP did not return the expected result."),
    "EMP_CANCELLED": ("EMP 分析任务已取消。", "The EMP analysis job was cancelled."),
}


class EmpClientError(RuntimeError):
    def __init__(
        self,
        error_code: str,
        message: str = "",
        *,
        retryable: bool = False,
        status: int = 0,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        zh, en = ERROR_MESSAGES.get(error_code, ("EMP 请求失败。", "EMP request failed."))
        super().__init__(message or en)
        self.error_code = error_code
        self.message = message or en
        self.retryable = retryable
        self.status = status
        self.details = details or {}
        self.user_message_zh = zh
        self.user_message_en = en

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "user_message_zh": self.user_message_zh,
            "user_message_en": self.user_message_en,
            "retryable": self.retryable,
            "source": "emp",
            "details": self.details,
        }


Transport = Callable[[urllib.request.Request, float], tuple[int, dict[str, str], bytes]]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _default_transport(request: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(request, timeout=timeout) as response:  # noqa: S310
        headers = {key.lower(): value for key, value in response.headers.items()}
        raw = response.read(512 * 1024 * 1024 + 1)
        if len(raw) > 512 * 1024 * 1024:
            raise EmpClientError("EMP_FILE_TOO_LARGE")
        return response.status, headers, raw


def _loopback_origin(base_url: str) -> str:
    parsed = urllib.parse.urlparse(str(base_url or "").strip().rstrip("/"))
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("local EMP URL must be an http loopback origin")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("local EMP URL cannot contain a path, query, or fragment")
    hostname = parsed.hostname.lower()
    is_loopback = hostname == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise ValueError("Phase 1 EMP integration only permits a loopback endpoint")
    port = parsed.port or 80
    host = f"[{hostname}]" if ":" in hostname else hostname
    return f"http://{host}:{port}"


class EmpClient:
    """HTTP client restricted to the configured local EMP origin."""

    API_VERSION = "1.0"
    STEP_ENDPOINTS = {
        "emp.workflow.validate": "/api/workflows/microbiome_16s/validate",
        "emp.prepare.taxonomy": "/api/workflows/microbiome_16s/prepare/taxonomy",
        "emp.analyze.alpha": "/api/analyze/alpha",
        "emp.visualize.alpha": "/api/visualize/alpha",
    }

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 60,
        token_env: str = "EMP_API_TOKEN",
        transport: Optional[Transport] = None,
    ) -> None:
        self.base_url = _loopback_origin(base_url)
        self.timeout = max(1.0, min(float(timeout), 600.0))
        self.token_env = str(token_env or "EMP_API_TOKEN").strip()
        self._transport = transport or _default_transport

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "Agent-Hub-EMP/1.0"}
        token = os.environ.get(self.token_env, "").strip() if self.token_env else ""
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[dict[str, Any]] = None,
        *,
        expect_json: bool = True,
    ) -> Any:
        if not path.startswith("/api/"):
            raise ValueError("EMP path must use the registered /api namespace")
        body = None
        headers = self._headers()
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=body, method=method, headers=headers)
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                status, response_headers, raw = self._transport(request, self.timeout)
                if status >= 400:
                    raise urllib.error.HTTPError(request.full_url, status, "EMP HTTP error", None, None)
                if not expect_json:
                    return raw, response_headers.get("content-type", "application/octet-stream")
                try:
                    result = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise EmpClientError("EMP_RESULT_MISSING", "EMP returned invalid JSON") from exc
                if not isinstance(result, dict):
                    raise EmpClientError("EMP_RESULT_MISSING", "EMP returned a non-object response")
                if result.get("success") is False:
                    message = str(result.get("error") or result.get("message") or "EMP request failed")
                    raise self._business_error(message, details=result)
                return result
            except EmpClientError:
                raise
            except urllib.error.HTTPError as exc:
                if 300 <= exc.code < 400:
                    raise EmpClientError("EMP_UNAVAILABLE", "EMP redirects are not permitted") from exc
                body: dict[str, Any] = {}
                try:
                    body = json.loads(exc.read(1024 * 1024).decode("utf-8"))
                except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
                    body = {}
                message = str(body.get("error") or body.get("message") or "")
                if exc.code in (401, 403):
                    if message and any(token in message.lower() for token in ("allowed root", "not allowed", "outside")):
                        raise EmpClientError("EMP_PATH_NOT_ALLOWED", message, status=exc.code) from exc
                    raise EmpClientError("EMP_AUTH_REQUIRED", message, status=exc.code) from exc
                if exc.code == 404:
                    raise EmpClientError("EMP_RESULT_MISSING", message, status=404) from exc
                if exc.code == 413:
                    raise EmpClientError("EMP_FILE_TOO_LARGE", status=413) from exc
                if message:
                    error = self._business_error(message, details=body)
                    error.status = exc.code
                    raise error from exc
                raise EmpClientError("EMP_JOB_FAILED", f"HTTP {exc.code}", status=exc.code, retryable=exc.code >= 500) from exc
            except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
                if attempt + 1 < attempts:
                    time.sleep(0.15 * (attempt + 1))
                    continue
                raise EmpClientError("EMP_UNAVAILABLE", str(getattr(exc, "reason", exc)), retryable=True) from exc
        raise EmpClientError("EMP_UNAVAILABLE", retryable=True)

    @staticmethod
    def _business_error(message: str, *, details: dict[str, Any]) -> EmpClientError:
        lowered = message.lower()
        if any(token in lowered for token in ("allowed root", "not allowed", "outside")):
            code = "EMP_PATH_NOT_ALLOWED"
        elif "session" in lowered and any(token in lowered for token in ("not found", "missing", "invalid")):
            code = "EMP_SESSION_NOT_FOUND"
        elif any(token in lowered for token in ("validation", "metadata", "sample", "group")):
            code = "EMP_DATA_VALIDATION_FAILED"
        else:
            code = "EMP_JOB_FAILED"
        return EmpClientError(code, message, details=details)

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/api/health")

    def capabilities(self) -> dict[str, Any]:
        result = self._request("GET", "/api/capabilities")
        if str(result.get("api_version") or "") != self.API_VERSION:
            raise EmpClientError(
                "EMP_VERSION_INCOMPATIBLE",
                f"expected API {self.API_VERSION}, received {result.get('api_version') or 'unknown'}",
            )
        return result

    def create_session(self) -> str:
        result = self._request("POST", "/api/session", {})
        session_id = str(result.get("session_id") or "")
        if not session_id:
            raise EmpClientError("EMP_RESULT_MISSING", "session_id missing")
        return session_id

    def preview_path(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/import/path/preview", payload)

    def import_path(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/import/path", payload)

    def list_experiments(self, session_id: str) -> list[dict[str, Any]]:
        result = self._request("GET", f"/api/session/{urllib.parse.quote(session_id)}/experiments")
        values = result.get("experiments") or []
        return values if isinstance(values, list) else []

    def run_step(self, tool: str, params: dict[str, Any]) -> dict[str, Any]:
        endpoint = self.STEP_ENDPOINTS.get(tool)
        if endpoint is None:
            raise ValueError(f"unregistered EMP tool: {tool}")
        return self._request("POST", endpoint, params)

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/jobs/{urllib.parse.quote(job_id)}")

    def get_job_result(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/jobs/{urllib.parse.quote(job_id)}/result")

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        try:
            return self._request("POST", f"/api/jobs/{urllib.parse.quote(job_id)}/cancel", {})
        except EmpClientError as exc:
            if exc.status == 404:
                return {"success": False, "status": "not_cancellable", "job_id": job_id}
            raise

    def download_artifact(self, path: str, destination: Path, *, max_bytes: int = 512 * 1024 * 1024) -> Path:
        parsed = urllib.parse.urlparse(path)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("/api/"):
            raise ValueError("artifact path must be a relative registered EMP API path")
        destination = destination.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        raw, _mime = self._request("GET", parsed.path, expect_json=False)
        if len(raw) > max_bytes:
            raise EmpClientError("EMP_FILE_TOO_LARGE")
        destination.write_bytes(raw)
        return destination

    @staticmethod
    def content_type(path: Path) -> str:
        return mimetypes.guess_type(path.name)[0] or "application/octet-stream"
