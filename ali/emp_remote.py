"""Secure, streaming transport primitives for configured remote EMP services."""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import mimetypes
import os
import re
import secrets
import ssl
import time
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Optional, Protocol, Sequence


DEFAULT_UPLOAD_LIMIT = 2 * 1024 * 1024 * 1024
DEFAULT_DOWNLOAD_LIMIT = 512 * 1024 * 1024
DEFAULT_RESPONSE_LIMIT = 8 * 1024 * 1024
DEFAULT_CHUNK_SIZE = 1024 * 1024
APPROVAL_VERSION = "1.0"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TOKEN_REF = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DATA_POLICIES = {"public", "internal", "confidential", "restricted"}


class EmpRemoteError(RuntimeError):
    """Normalized failure raised at the remote-transfer trust boundary."""

    def __init__(self, code: str, message: str, *, status: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class EmpRemoteEndpoint:
    """A remote origin selected by stable ID, never by request-time URL."""

    endpoint_id: str
    origin: str
    token_env: str
    timeout_seconds: float = 60.0
    upload_limit_bytes: int = DEFAULT_UPLOAD_LIMIT
    download_limit_bytes: int = DEFAULT_DOWNLOAD_LIMIT

    def __post_init__(self) -> None:
        if any(character in self.origin for character in "\r\n\t"):
            raise ValueError("remote EMP endpoint contains invalid control characters")
        if not _IDENTIFIER.fullmatch(self.endpoint_id):
            raise ValueError("invalid EMP endpoint_id")
        if not _TOKEN_REF.fullmatch(self.token_env):
            raise ValueError("remote EMP token_env must name an environment secret")
        parsed = urllib.parse.urlsplit(self.origin.strip())
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise ValueError("remote EMP endpoints must use HTTPS")
        if parsed.username or parsed.password:
            raise ValueError("remote EMP endpoint credentials are not allowed in URLs")
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("remote EMP endpoint must be an HTTPS origin without path, query, or fragment")
        try:
            port = parsed.port or 443
        except ValueError as exc:
            raise ValueError("invalid remote EMP endpoint port") from exc
        host = parsed.hostname.lower()
        authority = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        object.__setattr__(self, "origin", f"https://{authority}")
        object.__setattr__(self, "timeout_seconds", max(1.0, min(float(self.timeout_seconds), 600.0)))
        if self.upload_limit_bytes <= 0 or self.download_limit_bytes <= 0:
            raise ValueError("remote EMP transfer limits must be positive")

    @classmethod
    def from_config(cls, endpoint_id: str, config: Mapping[str, Any]) -> "EmpRemoteEndpoint":
        forbidden = {"token", "api_token", "bearer_token"} & set(config)
        if forbidden:
            raise ValueError("remote EMP configuration may contain only a token environment reference")
        return cls(
            endpoint_id=endpoint_id,
            origin=str(config.get("origin") or config.get("api_base") or ""),
            token_env=str(config.get("token_env") or config.get("api_token_env") or ""),
            timeout_seconds=float(config.get("timeout_seconds") or 60),
            upload_limit_bytes=int(config.get("upload_limit_bytes") or DEFAULT_UPLOAD_LIMIT),
            download_limit_bytes=int(config.get("download_limit_bytes") or DEFAULT_DOWNLOAD_LIMIT),
        )


class EmpRemoteEndpointRegistry:
    """Resolve only administrator-configured endpoint IDs."""

    def __init__(self, configs: Mapping[str, Mapping[str, Any]]) -> None:
        self._endpoints = {key: EmpRemoteEndpoint.from_config(key, value) for key, value in configs.items()}

    def get(self, endpoint_id: str) -> EmpRemoteEndpoint:
        try:
            return self._endpoints[endpoint_id]
        except KeyError as exc:
            raise EmpRemoteError("EMP_REMOTE_ENDPOINT_NOT_CONFIGURED", "remote EMP endpoint is not configured") from exc


@dataclass(frozen=True)
class UploadApproval:
    approval_id: str
    endpoint_id: str
    endpoint_origin: str
    manifest_fingerprint: str
    hub_session_id: str
    file_count: int
    total_bytes: int
    data_policy: str
    approver: str
    issued_at: int
    expires_at: int
    version: str = APPROVAL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UploadApprovalSigner:
    """Issue and verify compact HMAC approvals for one exact transfer."""

    def __init__(
        self,
        secret: bytes,
        *,
        max_ttl_seconds: int = 900,
        clock: Callable[[], float] = time.time,
        allow_restricted: bool = False,
    ) -> None:
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError("upload approval signing secret must contain at least 32 bytes")
        self._secret = secret
        self._max_ttl = max(1, min(int(max_ttl_seconds), 3600))
        self._clock = clock
        self._allow_restricted = bool(allow_restricted)

    def issue(
        self,
        *,
        endpoint_id: str,
        endpoint_origin: str,
        manifest_fingerprint: str,
        hub_session_id: str,
        file_count: int,
        total_bytes: int,
        data_policy: str,
        approver: str,
        ttl_seconds: int = 300,
    ) -> str:
        self._validate_binding(
            endpoint_id, endpoint_origin, manifest_fingerprint, hub_session_id, file_count, total_bytes, data_policy
        )
        if not str(approver or "").strip():
            raise ValueError("approver is required")
        now = int(self._clock())
        approval = UploadApproval(
            approval_id=f"emp-upload-{secrets.token_hex(16)}",
            endpoint_id=endpoint_id,
            endpoint_origin=_https_origin(endpoint_origin),
            manifest_fingerprint=manifest_fingerprint,
            hub_session_id=hub_session_id,
            file_count=int(file_count),
            total_bytes=int(total_bytes),
            data_policy=data_policy,
            approver=str(approver).strip(),
            issued_at=now,
            expires_at=now + min(max(1, int(ttl_seconds)), self._max_ttl),
        )
        payload = _canonical_json(approval.to_dict())
        signature = hmac.new(self._secret, payload, hashlib.sha256).digest()
        return f"{_b64encode(payload)}.{_b64encode(signature)}"

    def verify(
        self,
        token: str,
        *,
        endpoint_id: str,
        endpoint_origin: str,
        manifest_fingerprint: str,
        hub_session_id: str,
        file_count: int,
        total_bytes: int,
        data_policy: str,
    ) -> UploadApproval:
        try:
            encoded_payload, encoded_signature = str(token).split(".", 1)
            payload = _b64decode(encoded_payload)
            signature = _b64decode(encoded_signature)
        except (ValueError, TypeError) as exc:
            raise EmpRemoteError("EMP_UPLOAD_APPROVAL_INVALID", "upload approval is malformed") from exc
        expected = hmac.new(self._secret, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise EmpRemoteError("EMP_UPLOAD_APPROVAL_INVALID", "upload approval signature is invalid")
        try:
            values = json.loads(payload.decode("utf-8"))
            approval = UploadApproval(**values)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise EmpRemoteError("EMP_UPLOAD_APPROVAL_INVALID", "upload approval payload is invalid") from exc
        self._validate_binding(
            endpoint_id, endpoint_origin, manifest_fingerprint, hub_session_id, file_count, total_bytes, data_policy
        )
        expected_binding = {
            "endpoint_id": endpoint_id,
            "endpoint_origin": _https_origin(endpoint_origin),
            "manifest_fingerprint": manifest_fingerprint,
            "hub_session_id": hub_session_id,
            "file_count": int(file_count),
            "total_bytes": int(total_bytes),
            "data_policy": data_policy,
        }
        if approval.version != APPROVAL_VERSION or any(
            getattr(approval, key) != value for key, value in expected_binding.items()
        ):
            raise EmpRemoteError("EMP_UPLOAD_APPROVAL_MISMATCH", "upload approval does not match this transfer")
        now = int(self._clock())
        if approval.issued_at > now + 30 or approval.expires_at <= now:
            raise EmpRemoteError("EMP_UPLOAD_APPROVAL_EXPIRED", "upload approval has expired")
        if approval.expires_at - approval.issued_at > self._max_ttl:
            raise EmpRemoteError("EMP_UPLOAD_APPROVAL_INVALID", "upload approval lifetime exceeds policy")
        return approval

    def _validate_binding(
        self,
        endpoint_id: str,
        endpoint_origin: str,
        manifest_fingerprint: str,
        hub_session_id: str,
        file_count: int,
        total_bytes: int,
        data_policy: str,
    ) -> None:
        if not _IDENTIFIER.fullmatch(str(endpoint_id or "")):
            raise ValueError("invalid endpoint_id")
        _https_origin(endpoint_origin)
        if not _SHA256.fullmatch(str(manifest_fingerprint or "").lower()):
            raise ValueError("manifest_fingerprint must be a SHA-256 digest")
        if not str(hub_session_id or "").strip():
            raise ValueError("hub_session_id is required")
        if int(file_count) <= 0 or int(total_bytes) < 0:
            raise ValueError("approval must bind a positive file count and non-negative byte count")
        if data_policy not in _DATA_POLICIES:
            raise ValueError("unsupported data policy")
        if data_policy == "restricted" and not self._allow_restricted:
            raise EmpRemoteError("EMP_REMOTE_RESTRICTED_DENIED", "restricted data cannot be uploaded remotely")


@dataclass(frozen=True)
class RemoteUploadFile:
    field_name: str
    path: Path
    sha256: str
    filename: str = ""
    content_type: str = ""


class StreamingResponse(Protocol):
    status: int
    headers: Mapping[str, str]

    def read(self, size: int = -1) -> bytes: ...

    def close(self) -> None: ...


RemoteTransport = Callable[
    [EmpRemoteEndpoint, str, str, Mapping[str, str], Optional[Iterable[bytes]], Optional[int], float],
    StreamingResponse,
]
TokenResolver = Callable[[str], Any]


class _HttpStreamingResponse:
    def __init__(self, connection: http.client.HTTPSConnection, response: http.client.HTTPResponse) -> None:
        self._connection = connection
        self._response = response
        self.status = response.status
        self.headers = {key.lower(): value for key, value in response.getheaders()}

    def read(self, size: int = -1) -> bytes:
        return self._response.read(size)

    def close(self) -> None:
        try:
            self._response.close()
        finally:
            self._connection.close()


def _https_transport(
    endpoint: EmpRemoteEndpoint,
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: Optional[Iterable[bytes]],
    content_length: Optional[int],
    timeout: float,
) -> StreamingResponse:
    parsed = urllib.parse.urlsplit(endpoint.origin)
    connection = http.client.HTTPSConnection(
        parsed.hostname,
        parsed.port or 443,
        timeout=timeout,
        context=ssl.create_default_context(),
    )
    try:
        connection.putrequest(method, path, skip_accept_encoding=True)
        for key, value in headers.items():
            connection.putheader(key, value)
        if content_length is not None:
            connection.putheader("Content-Length", str(content_length))
        connection.endheaders()
        if body is not None:
            for chunk in body:
                if chunk:
                    connection.send(chunk)
        return _HttpStreamingResponse(connection, connection.getresponse())
    except Exception:
        connection.close()
        raise


class EmpRemoteClient:
    """Remote EMP transfer client with approval and origin confinement."""

    def __init__(
        self,
        endpoint: EmpRemoteEndpoint,
        *,
        approval_signer: UploadApprovalSigner,
        allowed_roots: Sequence[Path],
        token_resolver: Optional[TokenResolver] = None,
        transport: Optional[RemoteTransport] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        self.endpoint = endpoint
        self._approval_signer = approval_signer
        self._allowed_roots = tuple(Path(root).resolve(strict=True) for root in allowed_roots)
        self._token_resolver = token_resolver
        self._transport = transport or _https_transport
        self._chunk_size = max(4096, min(int(chunk_size), 8 * 1024 * 1024))

    def upload_multipart(
        self,
        path: str,
        *,
        files: Sequence[RemoteUploadFile],
        fields: Optional[Mapping[str, Any]],
        approval_token: str,
        manifest_fingerprint: str,
        hub_session_id: str,
        data_policy: str,
    ) -> dict[str, Any]:
        api_path = _api_path(path)
        prepared = [self._prepare_upload_file(item) for item in files]
        total_bytes = sum(item.size for item in prepared)
        if total_bytes > self.endpoint.upload_limit_bytes:
            raise EmpRemoteError("EMP_FILE_TOO_LARGE", "remote upload exceeds the configured byte limit")
        self._approval_signer.verify(
            approval_token,
            endpoint_id=self.endpoint.endpoint_id,
            endpoint_origin=self.endpoint.origin,
            manifest_fingerprint=manifest_fingerprint,
            hub_session_id=hub_session_id,
            file_count=len(prepared),
            total_bytes=total_bytes,
            data_policy=data_policy,
        )
        boundary = f"agent-hub-{secrets.token_hex(18)}"
        body = _MultipartBody(
            boundary=boundary,
            fields=fields or {},
            files=prepared,
            chunk_size=self._chunk_size,
        )
        headers = self._headers()
        headers.update(
            {
                "Accept": "application/json",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-Agent-Hub-Upload-Approval": approval_token,
            }
        )
        response = self._request("POST", api_path, headers, body, body.content_length)
        try:
            body.ensure_complete()
        except Exception:
            response.close()
            raise
        return _read_json_response(response, DEFAULT_RESPONSE_LIMIT)

    def request_json(self, method: str, path: str, payload: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        """Call a registered relative EMP API path without following redirects."""
        api_path = _api_path(path)
        body = None
        content_length = None
        headers = {**self._headers(), "Accept": "application/json"}
        if payload is not None:
            raw = _canonical_json(payload)
            body = (chunk for chunk in (raw,))
            content_length = len(raw)
            headers["Content-Type"] = "application/json"
        response = self._request(method, api_path, headers, body, content_length)
        return _read_json_response(response, DEFAULT_RESPONSE_LIMIT)

    def download(
        self,
        path: str,
        destination: Path,
        *,
        expected_sha256: str,
        max_bytes: Optional[int] = None,
    ) -> Path:
        api_path = _api_path(path)
        digest = str(expected_sha256 or "").lower()
        if not _SHA256.fullmatch(digest):
            raise ValueError("expected_sha256 is required for remote downloads")
        target = self._resolve_destination(destination)
        limit = min(int(max_bytes or self.endpoint.download_limit_bytes), self.endpoint.download_limit_bytes)
        if limit <= 0:
            raise ValueError("download byte limit must be positive")
        response = self._request("GET", api_path, self._headers(), None, None)
        temporary = target.with_name(f".{target.name}.{secrets.token_hex(8)}.part")
        hasher = hashlib.sha256()
        received = 0
        try:
            declared = _content_length(response.headers)
            if declared is not None and declared > limit:
                raise EmpRemoteError("EMP_FILE_TOO_LARGE", "remote artifact exceeds the configured byte limit")
            target.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("xb") as handle:
                while True:
                    chunk = response.read(self._chunk_size)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > limit:
                        raise EmpRemoteError("EMP_FILE_TOO_LARGE", "remote artifact exceeds the configured byte limit")
                    handle.write(chunk)
                    hasher.update(chunk)
            if hasher.hexdigest() != digest:
                raise EmpRemoteError("EMP_CHECKSUM_MISMATCH", "remote artifact checksum does not match")
            os.replace(temporary, target)
            return target
        finally:
            response.close()
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _headers(self) -> dict[str, str]:
        token = os.environ.get(self.endpoint.token_env)
        if not str(token or "").strip() and self._token_resolver:
            token = self._token_resolver(self.endpoint.token_env)
            if isinstance(token, Mapping):
                token = token.get("key") or token.get("token") or ""
        token = str(token or "").strip()
        if not token:
            raise EmpRemoteError("EMP_AUTH_REQUIRED", "remote EMP token is unavailable")
        if "\r" in token or "\n" in token:
            raise EmpRemoteError("EMP_AUTH_REQUIRED", "remote EMP token contains invalid characters")
        return {
            "Authorization": f"Bearer {token}",
            "User-Agent": "Agent-Hub-EMP-Remote/1.0",
        }

    def _request(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: Optional[Iterable[bytes]],
        content_length: Optional[int],
    ) -> StreamingResponse:
        try:
            response = self._transport(
                self.endpoint, method, path, headers, body, content_length, self.endpoint.timeout_seconds
            )
        except (OSError, TimeoutError, ssl.SSLError, http.client.HTTPException) as exc:
            raise EmpRemoteError("EMP_UNAVAILABLE", "remote EMP request failed") from exc
        if 300 <= response.status < 400:
            response.close()
            raise EmpRemoteError("EMP_REDIRECT_REJECTED", "remote EMP redirects are not permitted", status=response.status)
        if response.status in (401, 403):
            response.close()
            raise EmpRemoteError("EMP_AUTH_REQUIRED", "remote EMP authentication failed", status=response.status)
        if response.status == 413:
            response.close()
            raise EmpRemoteError("EMP_FILE_TOO_LARGE", "remote EMP rejected the transfer size", status=413)
        if response.status >= 400:
            status = response.status
            response.close()
            raise EmpRemoteError("EMP_REMOTE_REQUEST_FAILED", f"remote EMP returned HTTP {status}", status=status)
        return response

    def _prepare_upload_file(self, item: RemoteUploadFile) -> "_PreparedUploadFile":
        path = Path(item.path).resolve(strict=True)
        if not path.is_file() or not _within_roots(path, self._allowed_roots):
            raise EmpRemoteError("EMP_PATH_NOT_ALLOWED", "upload file is outside the configured roots")
        if not _IDENTIFIER.fullmatch(item.field_name):
            raise ValueError("invalid multipart field name")
        digest = str(item.sha256 or "").lower()
        if not _SHA256.fullmatch(digest):
            raise ValueError("each remote upload file requires a SHA-256 checksum")
        filename = item.filename or path.name
        if Path(filename).name != filename or "\r" in filename or "\n" in filename:
            raise ValueError("invalid multipart filename")
        content_type = item.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        if "\r" in content_type or "\n" in content_type or len(content_type) > 256:
            raise ValueError("invalid multipart content type")
        if _sha256_file(path, self._chunk_size) != digest:
            raise EmpRemoteError("EMP_CHECKSUM_MISMATCH", "upload file checksum does not match its manifest")
        return _PreparedUploadFile(
            field_name=item.field_name,
            path=path,
            filename=filename,
            content_type=content_type,
            sha256=digest,
            size=path.stat().st_size,
        )

    def _resolve_destination(self, destination: Path) -> Path:
        target = Path(destination).expanduser().resolve(strict=False)
        if not self._allowed_roots or not _within_roots(target, self._allowed_roots):
            raise EmpRemoteError("EMP_PATH_NOT_ALLOWED", "download destination is outside the configured roots")
        return target


@dataclass(frozen=True)
class _PreparedUploadFile:
    field_name: str
    path: Path
    filename: str
    content_type: str
    sha256: str
    size: int


class _MultipartBody:
    def __init__(
        self,
        *,
        boundary: str,
        fields: Mapping[str, Any],
        files: Sequence[_PreparedUploadFile],
        chunk_size: int,
    ) -> None:
        self._boundary = boundary
        self._fields = [(self._field_header(name), str(value).encode("utf-8")) for name, value in fields.items()]
        self._files = files
        self._chunk_size = chunk_size
        self._complete = False
        self.content_length = self._calculate_length()

    def __iter__(self) -> Iterator[bytes]:
        if self._complete:
            raise EmpRemoteError("EMP_UPLOAD_REUSED", "multipart upload bodies cannot be reused")
        for header, value in self._fields:
            yield header
            yield value
            yield b"\r\n"
        for item in self._files:
            yield self._file_header(item)
            hasher = hashlib.sha256()
            sent = 0
            with item.path.open("rb") as handle:
                while True:
                    chunk = handle.read(self._chunk_size)
                    if not chunk:
                        break
                    sent += len(chunk)
                    if sent > item.size:
                        raise EmpRemoteError("EMP_UPLOAD_FILE_CHANGED", "upload file changed during transfer")
                    hasher.update(chunk)
                    yield chunk
            if sent != item.size or hasher.hexdigest() != item.sha256:
                raise EmpRemoteError("EMP_CHECKSUM_MISMATCH", "upload file checksum does not match its manifest")
            yield b"\r\n"
        yield f"--{self._boundary}--\r\n".encode("ascii")
        self._complete = True

    def ensure_complete(self) -> None:
        if not self._complete:
            raise EmpRemoteError("EMP_UPLOAD_INCOMPLETE", "remote transport did not consume the complete upload")

    def _field_header(self, name: str) -> bytes:
        if not _IDENTIFIER.fullmatch(str(name)):
            raise ValueError("invalid multipart field name")
        return f'--{self._boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii")

    def _file_header(self, item: _PreparedUploadFile) -> bytes:
        fallback = item.filename.encode("ascii", "replace").decode("ascii").replace('"', "_")
        encoded = urllib.parse.quote(item.filename, safe="")
        return (
            f'--{self._boundary}\r\nContent-Disposition: form-data; name="{item.field_name}"; '
            f'filename="{fallback}"; filename*=UTF-8\'\'{encoded}\r\nContent-Type: {item.content_type}\r\n\r\n'
        ).encode("ascii")

    def _calculate_length(self) -> int:
        length = sum(len(header) + len(value) + 2 for header, value in self._fields)
        length += sum(len(self._file_header(item)) + item.size + 2 for item in self._files)
        return length + len(f"--{self._boundary}--\r\n".encode("ascii"))


def _read_json_response(response: StreamingResponse, max_bytes: int) -> dict[str, Any]:
    try:
        raw = _read_limited(response, max_bytes)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EmpRemoteError("EMP_RESULT_MISSING", "remote EMP returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise EmpRemoteError("EMP_RESULT_MISSING", "remote EMP returned a non-object response")
        return payload
    finally:
        response.close()


def _read_limited(response: StreamingResponse, max_bytes: int) -> bytes:
    declared = _content_length(response.headers)
    if declared is not None and declared > max_bytes:
        raise EmpRemoteError("EMP_FILE_TOO_LARGE", "remote response exceeds the configured byte limit")
    chunks = []
    received = 0
    while True:
        chunk = response.read(min(DEFAULT_CHUNK_SIZE, max_bytes + 1 - received))
        if not chunk:
            break
        received += len(chunk)
        if received > max_bytes:
            raise EmpRemoteError("EMP_FILE_TOO_LARGE", "remote response exceeds the configured byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _content_length(headers: Mapping[str, str]) -> Optional[int]:
    value = headers.get("content-length")
    if value in (None, ""):
        return None
    try:
        length = int(value)
    except (TypeError, ValueError) as exc:
        raise EmpRemoteError("EMP_RESULT_MISSING", "remote EMP returned an invalid Content-Length") from exc
    if length < 0:
        raise EmpRemoteError("EMP_RESULT_MISSING", "remote EMP returned an invalid Content-Length")
    return length


def _api_path(path: str) -> str:
    value = str(path or "")
    parsed = urllib.parse.urlsplit(value)
    decoded = urllib.parse.unquote(parsed.path)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/api/")
        or "\r" in value
        or "\n" in value
        or any(part in {".", ".."} for part in decoded.split("/"))
    ):
        raise ValueError("remote EMP path must be a relative registered /api path")
    return parsed.path


def _https_origin(origin: str) -> str:
    value = str(origin or "").strip()
    if any(character in value for character in "\r\n\t"):
        raise ValueError("remote EMP endpoint contains invalid control characters")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("remote EMP endpoints must use HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("remote EMP endpoint credentials are not allowed in URLs")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("remote EMP endpoint must be an HTTPS origin without path, query, or fragment")
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise ValueError("invalid remote EMP endpoint port") from exc
    host = parsed.hostname.lower()
    authority = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    return f"https://{authority}"


def _sha256_file(path: Path, chunk_size: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _within_roots(path: Path, roots: Sequence[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    if not value or len(value) > 16384:
        raise ValueError("invalid base64 value")
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding, altchars=b"-_", validate=True)
