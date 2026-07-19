from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Mapping, Optional

import pytest

from ali.emp_remote import (
    EmpRemoteClient,
    EmpRemoteEndpoint,
    EmpRemoteEndpointRegistry,
    EmpRemoteError,
    RemoteUploadFile,
    UploadApprovalSigner,
)


class FakeResponse:
    def __init__(self, status: int, body: bytes = b"{}", headers: Optional[Mapping[str, str]] = None) -> None:
        self.status = status
        self.headers = {key.lower(): value for key, value in (headers or {}).items()}
        self._body = io.BytesIO(body)
        self.read_sizes = []
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return self._body.read(size)

    def close(self) -> None:
        self.closed = True


class FakeTransport:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls = []
        self.upload_chunks = []

    def __call__(self, endpoint, method, path, headers, body, content_length, timeout):
        if body is not None:
            self.upload_chunks = list(body)
        self.calls.append(
            {
                "endpoint": endpoint,
                "method": method,
                "path": path,
                "headers": dict(headers),
                "content_length": content_length,
                "timeout": timeout,
            }
        )
        return self.response


def _endpoint(**overrides) -> EmpRemoteEndpoint:
    values = {
        "endpoint_id": "lab-prod",
        "origin": "https://emp.example.edu",
        "token_env": "EMP_LAB_TOKEN",
        "upload_limit_bytes": 1024 * 1024,
        "download_limit_bytes": 1024 * 1024,
    }
    values.update(overrides)
    return EmpRemoteEndpoint(**values)


def _signer(clock=lambda: 1_000) -> UploadApprovalSigner:
    return UploadApprovalSigner(b"s" * 32, clock=clock)


@pytest.mark.parametrize(
    "origin",
    [
        "http://emp.example.edu",
        "https://user:pass@emp.example.edu",
        "https://emp.example.edu/api",
        "https://emp.example.edu?target=other",
        "https://emp.example.edu\r\nX-Test: value",
    ],
)
def test_endpoint_requires_clean_https_origin(origin: str) -> None:
    with pytest.raises(ValueError):
        _endpoint(origin=origin)


def test_registry_rejects_literal_tokens_and_unknown_runtime_urls() -> None:
    with pytest.raises(ValueError, match="token environment"):
        EmpRemoteEndpointRegistry(
            {"lab": {"origin": "https://emp.example.edu", "token_env": "EMP_TOKEN", "token": "secret"}}
        )
    registry = EmpRemoteEndpointRegistry(
        {"lab": {"origin": "https://emp.example.edu", "token_env": "EMP_TOKEN"}}
    )
    assert registry.get("lab").origin == "https://emp.example.edu:443"
    compatible = EmpRemoteEndpointRegistry(
        {"lab": {"origin": "https://emp.example.edu", "api_token_env": "EMP_TOKEN"}}
    )
    assert compatible.get("lab").token_env == "EMP_TOKEN"
    with pytest.raises(EmpRemoteError, match="not configured"):
        registry.get("https://attacker.example")


def test_approval_is_signed_expiring_and_bound_to_exact_transfer() -> None:
    signer = _signer()
    fingerprint = "a" * 64
    token = signer.issue(
        endpoint_id="lab-prod",
        endpoint_origin="https://emp.example.edu:443",
        manifest_fingerprint=fingerprint,
        hub_session_id="hub-1",
        file_count=2,
        total_bytes=123,
        data_policy="confidential",
        approver="admin",
        ttl_seconds=60,
    )
    approval = signer.verify(
        token,
        endpoint_id="lab-prod",
        endpoint_origin="https://emp.example.edu:443",
        manifest_fingerprint=fingerprint,
        hub_session_id="hub-1",
        file_count=2,
        total_bytes=123,
        data_policy="confidential",
    )
    assert approval.approver == "admin"
    with pytest.raises(EmpRemoteError, match="does not match"):
        signer.verify(
            token,
            endpoint_id="lab-prod",
            endpoint_origin="https://emp.example.edu:443",
            manifest_fingerprint=fingerprint,
            hub_session_id="hub-other",
            file_count=2,
            total_bytes=123,
            data_policy="confidential",
        )
    payload, signature = token.split(".")
    with pytest.raises(EmpRemoteError, match="signature"):
        signer.verify(
            payload + "." + ("A" if signature[0] != "A" else "B") + signature[1:],
            endpoint_id="lab-prod",
            endpoint_origin="https://emp.example.edu:443",
            manifest_fingerprint=fingerprint,
            hub_session_id="hub-1",
            file_count=2,
            total_bytes=123,
            data_policy="confidential",
        )
    expired = UploadApprovalSigner(b"s" * 32, clock=lambda: 2_000)
    with pytest.raises(EmpRemoteError, match="expired"):
        expired.verify(
            token,
            endpoint_id="lab-prod",
            endpoint_origin="https://emp.example.edu:443",
            manifest_fingerprint=fingerprint,
            hub_session_id="hub-1",
            file_count=2,
            total_bytes=123,
            data_policy="confidential",
        )


def test_restricted_data_is_denied_by_default() -> None:
    with pytest.raises(EmpRemoteError) as caught:
        _signer().issue(
            endpoint_id="lab-prod",
            endpoint_origin="https://emp.example.edu:443",
            manifest_fingerprint="a" * 64,
            hub_session_id="hub-1",
            file_count=1,
            total_bytes=10,
            data_policy="restricted",
            approver="admin",
        )
    assert caught.value.code == "EMP_REMOTE_RESTRICTED_DENIED"


def test_approval_is_bound_to_configured_origin() -> None:
    signer = _signer()
    token = signer.issue(
        endpoint_id="lab-prod",
        endpoint_origin="https://emp.example.edu",
        manifest_fingerprint="a" * 64,
        hub_session_id="hub-1",
        file_count=1,
        total_bytes=10,
        data_policy="internal",
        approver="admin",
    )
    with pytest.raises(EmpRemoteError, match="does not match"):
        signer.verify(
            token,
            endpoint_id="lab-prod",
            endpoint_origin="https://replacement.example.edu",
            manifest_fingerprint="a" * 64,
            hub_session_id="hub-1",
            file_count=1,
            total_bytes=10,
            data_policy="internal",
        )


def test_upload_streams_files_and_resolves_token_only_at_request_time(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EMP_LAB_TOKEN", raising=False)
    content = b"0123456789" * 20_000
    source = tmp_path / "counts.csv"
    source.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    fingerprint = "b" * 64
    signer = _signer()
    approval = signer.issue(
        endpoint_id="lab-prod",
        endpoint_origin="https://emp.example.edu:443",
        manifest_fingerprint=fingerprint,
        hub_session_id="hub-1",
        file_count=1,
        total_bytes=len(content),
        data_policy="internal",
        approver="user-1",
    )
    resolved = []
    transport = FakeTransport(FakeResponse(200, json.dumps({"success": True}).encode()))
    client = EmpRemoteClient(
        _endpoint(),
        approval_signer=signer,
        allowed_roots=[tmp_path],
        token_resolver=lambda reference: resolved.append(reference) or "runtime-secret",
        transport=transport,
        chunk_size=16 * 1024,
    )
    result = client.upload_multipart(
        "/api/import",
        files=[RemoteUploadFile("data", source, checksum)],
        fields={"session_id": "emp-session"},
        approval_token=approval,
        manifest_fingerprint=fingerprint,
        hub_session_id="hub-1",
        data_policy="internal",
    )
    assert result == {"success": True}
    assert resolved == ["EMP_LAB_TOKEN"]
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer runtime-secret"
    assert transport.calls[0]["content_length"] == sum(map(len, transport.upload_chunks))
    file_chunks = [chunk for chunk in transport.upload_chunks if chunk and not chunk.startswith(b"--")]
    assert max(map(len, file_chunks)) <= 16 * 1024
    assert b"".join(transport.upload_chunks).count(content) == 1


def test_environment_token_precedes_secrets_callback(tmp_path: Path, monkeypatch) -> None:
    content = b"result"
    monkeypatch.setenv("EMP_LAB_TOKEN", "environment-secret")
    response = FakeResponse(200, content)
    transport = FakeTransport(response)
    client = EmpRemoteClient(
        _endpoint(),
        approval_signer=_signer(),
        allowed_roots=[tmp_path],
        token_resolver=lambda _ref: pytest.fail("secrets callback should not run when env is set"),
        transport=transport,
    )
    client.download(
        "/api/results/one",
        tmp_path / "result.bin",
        expected_sha256=hashlib.sha256(content).hexdigest(),
    )
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer environment-secret"


def test_secrets_callback_may_return_a_key_record(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EMP_LAB_TOKEN", raising=False)
    content = b"result"
    transport = FakeTransport(FakeResponse(200, content))
    client = EmpRemoteClient(
        _endpoint(),
        approval_signer=_signer(),
        allowed_roots=[tmp_path],
        token_resolver=lambda _ref: {"present": True, "key": "stored-secret"},
        transport=transport,
    )
    client.download(
        "/api/results/one",
        tmp_path / "record-result.bin",
        expected_sha256=hashlib.sha256(content).hexdigest(),
    )
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer stored-secret"


def test_upload_rejects_limit_before_contacting_remote(tmp_path: Path) -> None:
    source = tmp_path / "data.bin"
    source.write_bytes(b"payload")
    fingerprint = "c" * 64
    signer = _signer()
    approval = signer.issue(
        endpoint_id="lab-prod",
        endpoint_origin="https://emp.example.edu:443",
        manifest_fingerprint=fingerprint,
        hub_session_id="hub-1",
        file_count=1,
        total_bytes=7,
        data_policy="internal",
        approver="user-1",
    )
    transport = FakeTransport(FakeResponse(200, b"{}"))
    client = EmpRemoteClient(
        _endpoint(upload_limit_bytes=6),
        approval_signer=signer,
        allowed_roots=[tmp_path],
        token_resolver=lambda _ref: "token",
        transport=transport,
    )
    with pytest.raises(EmpRemoteError) as caught:
        client.upload_multipart(
            "/api/import",
            files=[RemoteUploadFile("data", source, hashlib.sha256(b"payload").hexdigest())],
            fields={},
            approval_token=approval,
            manifest_fingerprint=fingerprint,
            hub_session_id="hub-1",
            data_policy="internal",
        )
    assert caught.value.code == "EMP_FILE_TOO_LARGE"
    assert transport.calls == []


def test_upload_rejects_manifest_checksum_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "data.bin"
    source.write_bytes(b"payload")
    fingerprint = "f" * 64
    signer = _signer()
    approval = signer.issue(
        endpoint_id="lab-prod",
        endpoint_origin="https://emp.example.edu:443",
        manifest_fingerprint=fingerprint,
        hub_session_id="hub-1",
        file_count=1,
        total_bytes=7,
        data_policy="internal",
        approver="user-1",
    )
    client = EmpRemoteClient(
        _endpoint(),
        approval_signer=signer,
        allowed_roots=[tmp_path],
        token_resolver=lambda _ref: "token",
        transport=FakeTransport(FakeResponse(200, b"{}")),
    )
    with pytest.raises(EmpRemoteError) as caught:
        client.upload_multipart(
            "/api/import",
            files=[RemoteUploadFile("data", source, "0" * 64)],
            fields={},
            approval_token=approval,
            manifest_fingerprint=fingerprint,
            hub_session_id="hub-1",
            data_policy="internal",
        )
    assert caught.value.code == "EMP_CHECKSUM_MISMATCH"


def test_upload_rejects_mime_header_injection_before_network(tmp_path: Path) -> None:
    source = tmp_path / "data.bin"
    source.write_bytes(b"payload")
    fingerprint = "9" * 64
    signer = _signer()
    approval = signer.issue(
        endpoint_id="lab-prod",
        endpoint_origin="https://emp.example.edu:443",
        manifest_fingerprint=fingerprint,
        hub_session_id="hub-1",
        file_count=1,
        total_bytes=7,
        data_policy="internal",
        approver="user-1",
    )
    transport = FakeTransport(FakeResponse(200, b"{}"))
    client = EmpRemoteClient(
        _endpoint(),
        approval_signer=signer,
        allowed_roots=[tmp_path],
        token_resolver=lambda _ref: "token",
        transport=transport,
    )
    with pytest.raises(ValueError, match="content type"):
        client.upload_multipart(
            "/api/import",
            files=[
                RemoteUploadFile(
                    "data",
                    source,
                    hashlib.sha256(b"payload").hexdigest(),
                    content_type="text/plain\r\nX-Evil: 1",
                )
            ],
            fields={},
            approval_token=approval,
            manifest_fingerprint=fingerprint,
            hub_session_id="hub-1",
            data_policy="internal",
        )
    assert transport.calls == []


def test_remote_request_requires_secret_at_call_time(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EMP_LAB_TOKEN", raising=False)
    transport = FakeTransport(FakeResponse(200, b"result"))
    client = EmpRemoteClient(
        _endpoint(),
        approval_signer=_signer(),
        allowed_roots=[tmp_path],
        transport=transport,
    )
    with pytest.raises(EmpRemoteError) as caught:
        client.download("/api/results/one", tmp_path / "result.bin", expected_sha256="d" * 64)
    assert caught.value.code == "EMP_AUTH_REQUIRED"
    assert transport.calls == []


def test_upload_rejects_files_outside_allowed_roots(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = tmp_path / "outside.bin"
    source.write_bytes(b"payload")
    client = EmpRemoteClient(
        _endpoint(),
        approval_signer=_signer(),
        allowed_roots=[allowed],
        token_resolver=lambda _ref: "token",
        transport=FakeTransport(FakeResponse(200)),
    )
    with pytest.raises(EmpRemoteError) as caught:
        client.upload_multipart(
            "/api/import",
            files=[RemoteUploadFile("data", source, hashlib.sha256(b"payload").hexdigest())],
            fields={},
            approval_token="not-reached",
            manifest_fingerprint="a" * 64,
            hub_session_id="hub-1",
            data_policy="internal",
        )
    assert caught.value.code == "EMP_PATH_NOT_ALLOWED"


def test_redirect_is_rejected_without_following_or_reusing_token(tmp_path: Path) -> None:
    target = tmp_path / "artifact.bin"
    response = FakeResponse(302, headers={"Location": "https://attacker.example/steal"})
    transport = FakeTransport(response)
    client = EmpRemoteClient(
        _endpoint(),
        approval_signer=_signer(),
        allowed_roots=[tmp_path],
        token_resolver=lambda _ref: "secret-token",
        transport=transport,
    )
    with pytest.raises(EmpRemoteError) as caught:
        client.download("/api/results/one", target, expected_sha256="d" * 64)
    assert caught.value.code == "EMP_REDIRECT_REJECTED"
    assert len(transport.calls) == 1
    assert response.closed is True


def test_download_streams_atomically_with_limit_and_checksum(tmp_path: Path) -> None:
    content = b"result-data" * 10_000
    checksum = hashlib.sha256(content).hexdigest()
    response = FakeResponse(200, content, {"Content-Length": str(len(content))})
    transport = FakeTransport(response)
    destination = tmp_path / "artifacts" / "result.bin"
    client = EmpRemoteClient(
        _endpoint(),
        approval_signer=_signer(),
        allowed_roots=[tmp_path],
        token_resolver=lambda _ref: "secret-token",
        transport=transport,
        chunk_size=8192,
    )
    assert client.download("/api/results/one", destination, expected_sha256=checksum) == destination
    assert destination.read_bytes() == content
    assert max(size for size in response.read_sizes if size > 0) <= 8192
    assert response.closed is True

    bad_response = FakeResponse(200, b"wrong")
    bad_client = EmpRemoteClient(
        _endpoint(),
        approval_signer=_signer(),
        allowed_roots=[tmp_path],
        token_resolver=lambda _ref: "secret-token",
        transport=FakeTransport(bad_response),
    )
    bad_target = tmp_path / "bad.bin"
    with pytest.raises(EmpRemoteError) as caught:
        bad_client.download("/api/results/two", bad_target, expected_sha256=checksum)
    assert caught.value.code == "EMP_CHECKSUM_MISMATCH"
    assert not bad_target.exists()
    assert not list(tmp_path.glob(".*.part"))


def test_download_enforces_declared_and_streamed_byte_limits(tmp_path: Path) -> None:
    declared = FakeResponse(200, b"small", {"Content-Length": "100"})
    client = EmpRemoteClient(
        _endpoint(download_limit_bytes=10),
        approval_signer=_signer(),
        allowed_roots=[tmp_path],
        token_resolver=lambda _ref: "token",
        transport=FakeTransport(declared),
    )
    with pytest.raises(EmpRemoteError) as caught:
        client.download("/api/results/declared", tmp_path / "declared.bin", expected_sha256="a" * 64)
    assert caught.value.code == "EMP_FILE_TOO_LARGE"
    assert not (tmp_path / "declared.bin").exists()

    streamed = FakeResponse(200, b"01234567890")
    streamed_client = EmpRemoteClient(
        _endpoint(download_limit_bytes=10),
        approval_signer=_signer(),
        allowed_roots=[tmp_path],
        token_resolver=lambda _ref: "token",
        transport=FakeTransport(streamed),
    )
    with pytest.raises(EmpRemoteError) as caught:
        streamed_client.download("/api/results/streamed", tmp_path / "streamed.bin", expected_sha256="a" * 64)
    assert caught.value.code == "EMP_FILE_TOO_LARGE"
    assert not (tmp_path / "streamed.bin").exists()

    malformed = FakeResponse(200, b"small", {"Content-Length": "invalid"})
    malformed_client = EmpRemoteClient(
        _endpoint(download_limit_bytes=10),
        approval_signer=_signer(),
        allowed_roots=[tmp_path],
        token_resolver=lambda _ref: "token",
        transport=FakeTransport(malformed),
    )
    with pytest.raises(EmpRemoteError) as caught:
        malformed_client.download("/api/results/malformed", tmp_path / "malformed.bin", expected_sha256="a" * 64)
    assert caught.value.code == "EMP_RESULT_MISSING"
    assert malformed.closed is True


@pytest.mark.parametrize(
    "path",
    ["https://attacker.example/api/result", "http://emp.example/api/result", "/api/../secret", "/other/result"],
)
def test_runtime_paths_cannot_select_an_arbitrary_origin(path: str, tmp_path: Path) -> None:
    client = EmpRemoteClient(
        _endpoint(),
        approval_signer=_signer(),
        allowed_roots=[tmp_path],
        token_resolver=lambda _ref: "secret-token",
        transport=FakeTransport(FakeResponse(200)),
    )
    with pytest.raises(ValueError):
        client.download(path, tmp_path / "result.bin", expected_sha256="e" * 64)
