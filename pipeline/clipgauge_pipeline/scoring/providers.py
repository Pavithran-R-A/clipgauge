"""Capability-aware, normalized inference providers for ClipGauge v0.2.

The module deliberately keeps secrets outside ProviderProfile. Adapters translate
one normalized request contract to provider-specific HTTP/local requests and
return schema-validated JSON plus explicit capability/degradation metadata.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx

from .. import config, local_runtime, protocol

LOCAL_QA_TRACE_ENV = "CLIPGAUGE_QA_RUNTIME_TRACE"
LOCAL_QA_TRACE_MAX_BYTES = 24_000
INFERENCE_CACHE_CONTRACT_VERSION = 2
RUBRIC_CACHE_VERSION = "balanced-v1"
SCORING_REQUEST_TIMEOUT_CAP_SECONDS = 30.0
GROQ_QWEN_SCORING_MAX_OUTPUT_TOKENS = 900


def _proc_rss_kb(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _memory_snapshot(server_pid: int | None) -> dict[str, int | None]:
    available_kb = None
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    available_kb = int(line.split()[1])
                    break
    except (OSError, ValueError, IndexError):
        pass
    return {
        "client_rss_kb": _proc_rss_kb(os.getpid()),
        "server_rss_kb": _proc_rss_kb(server_pid) if server_pid else None,
        "mem_available_kb": available_kb,
    }


def _local_qa_trace(event: str, **fields: Any) -> None:
    """Record bounded local-provider facts only under explicit QA opt-in."""
    if os.environ.get(LOCAL_QA_TRACE_ENV) != "1":
        return
    try:
        directory = config.home_dir() / "diagnostics"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "local-runtime.jsonl"
        record = {"event": event, "time": round(time.time(), 3), **fields}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        if path.stat().st_size > LOCAL_QA_TRACE_MAX_BYTES:
            data = path.read_bytes()[-LOCAL_QA_TRACE_MAX_BYTES:]
            path.write_bytes(data[data.find(b"\n") + 1:] if b"\n" in data else data)
        path.chmod(0o600)
    except OSError:
        # Diagnostics must never change provider behavior.
        return


Capability = bool | None
StructuredLevel = Literal["native_schema", "json_mode", "text_compatibility"]

ERROR_CODES = {
    "AUTH_INVALID",
    "PROVIDER_UNAVAILABLE",
    "MODEL_NOT_FOUND",
    "MODEL_UNSUPPORTED",
    "RATE_LIMITED",
    "QUOTA_EXHAUSTED",
    "BILLING_REQUIRED",
    "TIMEOUT",
    "NETWORK_FAILED",
    "STRUCTURED_OUTPUT_INVALID",
    "CONTEXT_TOO_LARGE",
    "VISION_UNSUPPORTED",
    "PROVIDER_RESPONSE_INVALID",
    "INTERNAL_PROVIDER_ERROR",
}


@dataclass(frozen=True)
class CapabilitySet:
    text: Capability = True
    structured_json: Capability = None
    json_schema: Capability = None
    vision: Capability = None
    model_listing: Capability = None
    local: Capability = False
    cloud: Capability = True
    streaming: Capability = None
    context_window: int | None = None
    max_images: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CapabilitySet":
        data = data or {}
        values = {name: data.get(name) for name in cls.__dataclass_fields__}
        values["text"] = data.get("text", True)
        values["local"] = data.get("local", False)
        values["cloud"] = data.get("cloud", not bool(values["local"]))
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderProfile:
    schema_version: int
    id: str
    kind: str
    display_name: str
    base_url: str
    model: str
    auth_strategy: str = "none"
    secret_ref: str | None = None
    capabilities: CapabilitySet = field(default_factory=CapabilitySet)
    locality: str = "cloud"
    enabled: bool = True
    timeout_seconds: float = 120.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_base_url(self.base_url)
        if not self.id or not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", self.id):
            raise ValueError("provider profile id is invalid")
        if not self.model or len(self.model) > 240:
            raise ValueError("provider model is invalid")
        if self.auth_strategy not in {"none", "bearer", "api_key_header", "custom_secret_header"}:
            raise ValueError("provider auth strategy is invalid")
        if not 1.0 <= self.timeout_seconds <= 1800.0:
            raise ValueError("provider timeout is outside the safe range")
        if self.auth_strategy == "custom_secret_header":
            name = str(self.metadata.get("secret_header_name", ""))
            if not re.fullmatch(r"[A-Za-z0-9!#$%&'*+.^_`|~-]{1,128}", name):
                raise ValueError("custom secret header name is invalid")

    @property
    def endpoint_identity(self) -> str:
        return normalize_base_url(self.base_url)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "kind": self.kind,
            "display_name": self.display_name,
            "base_url": self.base_url,
            "model": self.model,
            "auth_strategy": self.auth_strategy,
            "secret_ref": self.secret_ref,
            "capabilities": self.capabilities.to_dict(),
            "locality": self.locality,
            "enabled": self.enabled,
            "timeout_seconds": self.timeout_seconds,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProviderProfile":
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            id=str(data["id"]),
            kind=str(data["kind"]),
            display_name=str(data.get("display_name", data["kind"])),
            base_url=str(data["base_url"]),
            model=str(data["model"]),
            auth_strategy=str(data.get("auth_strategy", "none")),
            secret_ref=data.get("secret_ref"),
            capabilities=CapabilitySet.from_dict(data.get("capabilities")),
            locality=str(data.get("locality", "cloud")),
            enabled=bool(data.get("enabled", True)),
            timeout_seconds=float(data.get("timeout_seconds", 120.0)),
            metadata=dict(data.get("metadata") or {}),
        )


def normalize_base_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if not parts.scheme or not parts.netloc or parts.username or parts.password:
        raise ValueError("provider base URL must have an authority and no embedded credentials")
    if parts.query or parts.fragment:
        raise ValueError("provider base URL must not contain query or fragment data")
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    netloc = host.lower() + port
    path = parts.path.rstrip("/") or ""
    return urlunsplit((parts.scheme.lower(), netloc, path, "", ""))


def validate_base_url(value: str) -> str:
    normalized = normalize_base_url(value)
    parts = urlsplit(normalized)
    if parts.scheme not in {"https", "http"}:
        raise ValueError("provider base URL scheme must be HTTPS or approved HTTP")
    host = (parts.hostname or "").lower()
    loopback = host in {"127.0.0.1", "localhost", "::1"}
    if parts.scheme == "http" and not loopback:
        raise ValueError("remote HTTP provider endpoints are not supported")
    return normalized


def legacy_profile(llm_mode: str, model: str | None = None) -> ProviderProfile:
    if llm_mode == "ollama":
        return ProviderProfile(
            schema_version=1,
            id="legacy-ollama",
            kind="ollama",
            display_name="Ollama",
            base_url="http://127.0.0.1:11434",
            model=model or "auto",
            capabilities=CapabilitySet(
                structured_json=True,
                json_schema=None,
                vision=None,
                model_listing=True,
                local=True,
                cloud=False,
            ),
            locality="local",
        )
    return ProviderProfile(
        schema_version=1,
        id="legacy-gemini",
        kind="gemini",
        display_name="Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model=model or "gemini-flash-latest",
        auth_strategy="api_key_header",
        secret_ref="legacy:gemini",
        capabilities=CapabilitySet(
            structured_json=True,
            json_schema=True,
            vision=True,
            model_listing=True,
            local=False,
            cloud=True,
        ),
        locality="cloud",
    )


@dataclass
class InferenceRequest:
    prompt: str
    schema: dict[str, Any]
    images: list[bytes] = field(default_factory=list)
    temperature: float = 0.2
    purpose: str = "scoring"
    job_id: str | None = None
    require_vision: bool = False
    max_images: int | None = None


@dataclass
class InferenceResult:
    data: dict[str, Any]
    provider_profile_id: str
    provider_kind: str
    model: str
    capabilities_used: dict[str, Any]
    degraded_signals: list[str]
    structured_level: StructuredLevel
    latency_ms: int
    cache_hit: bool = False
    provider_request_id: str | None = None


class ProviderError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retry_after: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if code not in ERROR_CODES:
            code = "INTERNAL_PROVIDER_ERROR"
        self.code = code
        self.message = protocol.safe_message(message, limit=300)
        self.retry_after = retry_after
        self.details = dict(details or {})
        super().__init__(self.message)


class ProviderAdapter:
    backend = "provider"

    def __init__(self, profile: ProviderProfile, secret: str | None = None) -> None:
        self.profile = profile
        self.model = profile.model
        self.requested_model = profile.model
        self.actual_model = profile.model
        self._secret = secret.strip() if secret and secret.strip() else None
        self.last_result: InferenceResult | None = None
        self._request_number = 0
        self._scoring_deadline: float | None = None
        self._scoring_request_aborted = False
        self._scoring_worker: threading.Thread | None = None

    @property
    def backend_name(self) -> str:
        return self.profile.kind

    @property
    def supports_vision(self) -> bool:
        return self.profile.capabilities.vision is True

    def set_scoring_deadline(self, deadline: float | None) -> None:
        self._scoring_deadline = deadline
        self._scoring_request_aborted = False

    def request_timeout(self, request: InferenceRequest | None = None) -> float:
        timeout = float(self.profile.timeout_seconds)
        if request is None or request.purpose != "scoring" or self._scoring_deadline is None:
            return timeout
        if self._scoring_request_aborted:
            raise ProviderError("TIMEOUT", "Provider scoring request was aborted after exceeding its wall-time limit.")
        if self._scoring_worker is not None:
            if self._scoring_worker.is_alive():
                self._scoring_request_aborted = True
                raise ProviderError("TIMEOUT", "A previous provider scoring request is still stopping.")
            self._scoring_worker = None
        remaining = self._scoring_deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderError("TIMEOUT", "Provider scoring time budget was exhausted.")
        return max(0.001, min(timeout, remaining, SCORING_REQUEST_TIMEOUT_CAP_SECONDS))

    def retry_delay(
        self,
        error: ProviderError,
        attempt: int,
        request: InferenceRequest | None = None,
    ) -> float:
        delay = error.retry_after if error.retry_after is not None else 2**attempt
        if request is None or request.purpose != "scoring" or self._scoring_deadline is None:
            return delay
        if self._scoring_request_aborted:
            raise ProviderError("TIMEOUT", "Provider scoring request was aborted after exceeding its wall-time limit.")
        remaining = self._scoring_deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderError("TIMEOUT", "Provider scoring time budget was exhausted.")
        # Leave a small clock-resolution margin before sleeping. This keeps
        # retry backoff inside the hard deadline on coarse Windows clocks.
        return min(delay, max(0.0, remaining - 1e-6))

    def _post_request(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        request: InferenceRequest | None = None,
    ) -> httpx.Response:
        timeout = self.request_timeout(request)
        if request is None or request.purpose != "scoring" or self._scoring_deadline is None:
            return httpx.post(url, headers=headers, json=json_body, timeout=timeout, follow_redirects=False)

        remaining = self._scoring_deadline - time.monotonic()
        if remaining <= 0:
            raise httpx.TimeoutException("Provider scoring time budget was exhausted.")
        response: list[httpx.Response] = []
        errors: list[BaseException] = []

        def send() -> None:
            try:
                response.append(
                    httpx.post(
                        url,
                        headers=headers,
                        json=json_body,
                        timeout=timeout,
                        follow_redirects=False,
                    )
                )
            except BaseException as error:  # pragma: no cover - thread handoff
                errors.append(error)

        worker = threading.Thread(target=send, name="clipgauge-provider-request", daemon=True)
        self._scoring_worker = worker
        worker.start()
        worker.join(min(timeout, remaining))
        if not worker.is_alive():
            self._scoring_worker = None
        if worker.is_alive():
            self._scoring_request_aborted = True
            raise httpx.TimeoutException("Provider scoring request exceeded its wall-time deadline.")
        if errors:
            raise errors[0]
        if not response:
            raise httpx.TimeoutException("Provider scoring request returned no response.")
        return response[0]

    def cache_file(self, request: InferenceRequest, *, actual_model: str | None = None) -> Any:
        return _cache_dir() / f"{cache_key(self.profile, request, actual_model=actual_model or self.model)}.json"

    def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        images: list[bytes] | None = None,
        *,
        purpose: str = "scoring",
        job_id: str | None = None,
    ) -> dict[str, Any]:
        result = self.infer(
            InferenceRequest(
                prompt=prompt,
                schema=schema,
                images=images or [],
                purpose=purpose,
                job_id=job_id,
            )
        )
        return result.data

    def infer(self, request: InferenceRequest, *, use_cache: bool = True) -> InferenceResult:
        if request.require_vision and self.profile.capabilities.vision is False:
            raise ProviderError("VISION_UNSUPPORTED", "The selected model does not support vision.")
        if request.max_images is not None and len(request.images) > request.max_images:
            raise ProviderError("VISION_UNSUPPORTED", "Too many images were supplied for this provider.")
        cache_enabled = use_cache and not (
            self.profile.kind == "openrouter" and self.requested_model == "openrouter/free"
        )
        cache_file = self.cache_file(request)
        if cache_enabled and cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text())
                cached_model = None
                if (
                    isinstance(cached, dict)
                    and cached.get("cache_schema_version") == INFERENCE_CACHE_CONTRACT_VERSION
                    and isinstance(cached.get("data"), dict)
                ):
                    data = cached["data"]
                    cached_model = cached.get("actual_model")
                else:
                    data = cached
                validate_json_schema(data, request.schema)
                if isinstance(cached_model, str) and cached_model.strip():
                    self.actual_model = cached_model.strip()
                degraded = ["vision_unavailable"] if request.images and self.profile.capabilities.vision is False else []
                result = InferenceResult(
                    data=data,
                    provider_profile_id=self.profile.id,
                    provider_kind=self.profile.kind,
                    model=self.actual_model,
                    capabilities_used={"cache": True, "vision": bool(request.images) and self.profile.capabilities.vision is True},
                    degraded_signals=degraded,
                    structured_level=self.structured_level(),
                    latency_ms=0,
                    cache_hit=True,
                )
                self.last_result = result
                return result
            except (OSError, JSONDecodeError, ValueError):
                cache_file.unlink(missing_ok=True)
        started = time.monotonic()
        data, degraded, request_id = self._infer_uncached(request)
        try:
            validate_json_schema(data, request.schema)
        except ValueError as err:
            raise ProviderError("STRUCTURED_OUTPUT_INVALID", str(err)) from err
        if cache_enabled:
            cache_payload = {
                "cache_schema_version": INFERENCE_CACHE_CONTRACT_VERSION,
                "actual_model": self.actual_model,
                "data": data,
            }
            _write_json_atomic(cache_file, cache_payload)
            resolved_cache_file = self.cache_file(request, actual_model=self.actual_model)
            if resolved_cache_file != cache_file:
                _write_json_atomic(resolved_cache_file, cache_payload)
        result = InferenceResult(
            data=data,
            provider_profile_id=self.profile.id,
            provider_kind=self.profile.kind,
            model=self.actual_model,
            capabilities_used={
                "text": True,
                "structured_json": self.profile.capabilities.structured_json,
                "json_schema": self.profile.capabilities.json_schema,
                "vision": bool(request.images) and self.profile.capabilities.vision is True,
            },
            degraded_signals=degraded,
            structured_level=self.structured_level(),
            latency_ms=int((time.monotonic() - started) * 1000),
            provider_request_id=request_id,
        )
        self.last_result = result
        return result

    def structured_level(self) -> StructuredLevel:
        if self.profile.capabilities.json_schema is True:
            return "native_schema"
        if self.profile.capabilities.structured_json is True:
            return "json_mode"
        return "text_compatibility"

    def model_listing(self) -> list[str]:
        return []

    def model_descriptors(self) -> list[dict[str, Any]]:
        return [describe_model(self.profile, model) for model in self.model_listing()]

    def failure_context(self) -> dict[str, Any]:
        """Return safe runtime facts for a provider failure diagnostic."""
        return {}

    def recover_for_scoring(self) -> dict[str, Any]:
        """Give a provider one bounded scoring recovery opportunity."""
        return {"recovered": False}

    def test_connection(self) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        }
        try:
            models = self.model_listing()
            result = self.infer(
                InferenceRequest(
                    prompt='Return exactly {"ok":true}.',
                    schema=schema,
                    purpose="test_connection",
                    temperature=0.0,
                ),
                use_cache=False,
            )
            state = "PASS" if not result.degraded_signals else "WARNING"
            return {
                "state": state,
                "provider": self.profile.kind,
                "model": self.model,
                "models": models,
                "capabilities": result.capabilities_used,
                "degraded_signals": result.degraded_signals,
            }
        except ProviderError as err:
            return {
                "state": "FAIL",
                "provider": self.profile.kind,
                "model": self.model,
                "code": err.code,
                "message": err.message,
            }

    def _infer_uncached(self, request: InferenceRequest) -> tuple[dict[str, Any], list[str], str | None]:
        raise NotImplementedError


def _cache_dir():
    path = config.home_dir() / "llm-cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def describe_model(
    profile: ProviderProfile,
    model: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe whether a discovered model can safely score clips."""
    model_id = str(model).strip()
    metadata = metadata or {}
    lowered = model_id.casefold()
    unsupported = any(token in lowered for token in ("embedding", "whisper", "tts", "text-to-image"))
    capabilities = profile.capabilities.to_dict()
    supported_parameters = metadata.get("supported_parameters")
    if isinstance(supported_parameters, list) and supported_parameters:
        parameter_names = {str(value).casefold() for value in supported_parameters}
        structured = bool(parameter_names & {"response_format", "structured_outputs", "json_schema"})
        schema = "json_schema" in parameter_names or "structured_outputs" in parameter_names
        capabilities["structured_json"] = structured
        capabilities["json_schema"] = schema if structured else False
    else:
        structured = capabilities["structured_json"]
        schema = capabilities["json_schema"]
    architecture = metadata.get("architecture")
    if isinstance(architecture, dict) and isinstance(architecture.get("input_modalities"), list):
        capabilities["vision"] = any("image" in str(value).casefold() for value in architecture["input_modalities"])
    if unsupported:
        compatibility = "UNSUPPORTED"
    elif structured is False:
        compatibility = "NO STRUCTURED OUTPUT"
    elif structured is True and schema is True:
        compatibility = "FULL"
    else:
        compatibility = "TEXT-ONLY"
    result = {
        "id": model_id,
        "compatibility": compatibility,
        "capabilities": capabilities,
        "available": True,
        "deprecated": bool(metadata.get("deprecated", False)),
        "local": profile.locality == "local",
    }
    context_length = metadata.get("context_length")
    if isinstance(context_length, int) and context_length > 0:
        result["capabilities"]["context_window"] = context_length
    pricing = metadata.get("pricing")
    if isinstance(pricing, dict):
        result["price"] = dict(pricing)
    return result


def cache_key(
    profile: ProviderProfile,
    request: InferenceRequest,
    *,
    actual_model: str | None = None,
    rubric_version: str = RUBRIC_CACHE_VERSION,
) -> str:
    h = hashlib.sha256()
    fields = {
        "schema_version": INFERENCE_CACHE_CONTRACT_VERSION,
        "profile_id": profile.id,
        "kind": profile.kind,
        "requested_model": profile.model,
        "actual_model": actual_model or profile.model,
        "endpoint": profile.endpoint_identity,
        "prompt": request.prompt,
        "schema": request.schema,
        "rubric_version": rubric_version,
        "temperature": request.temperature,
        "purpose": request.purpose,
        "require_vision": request.require_vision,
    }
    h.update(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode())
    for image in request.images:
        h.update(hashlib.sha256(image).digest())
    return h.hexdigest()[:32]


def _strip_fences(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1] if "\n" in value else value[3:]
        if value.rstrip().endswith("```"):
            value = value.rstrip()[:-3]
    return value.strip()


def _strict_json_schema(value: Any) -> Any:
    """Add strict object bounds without mutating the scoring schema."""
    if isinstance(value, list):
        return [_strict_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    normalized = {key: _strict_json_schema(item) for key, item in value.items()}
    if normalized.get("type") == "object" or "properties" in normalized:
        normalized.setdefault("additionalProperties", False)
    return normalized


def parse_json_text(text: str) -> dict[str, Any]:
    value = _strip_fences(text)
    try:
        parsed = json.loads(value)
    except JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(value):
            if char not in "[{":
                continue
            try:
                parsed, _ = decoder.raw_decode(value[index:])
                break
            except JSONDecodeError:
                continue
        else:
            raise
    if not isinstance(parsed, dict):
        raise ValueError("provider response must be a JSON object")
    return parsed


def validate_json_schema(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    expected = schema.get("type")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} is not one of the allowed values")
    if expected == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be an object")
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            if extra:
                raise ValueError(f"{path} contains unsupported fields")
        for key, child in properties.items():
            if key in value:
                validate_json_schema(value[key], child, f"{path}.{key}")
    elif expected == "array":
        if not isinstance(value, list):
            raise ValueError(f"{path} must be an array")
        for index, item in enumerate(value):
            validate_json_schema(item, schema.get("items", {}), f"{path}[{index}]")
    elif expected == "string" and not isinstance(value, str):
        raise ValueError(f"{path} must be a string")
    elif expected == "boolean" and not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    elif expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        raise ValueError(f"{path} must be an integer")
    elif expected == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
        raise ValueError(f"{path} must be a number")


def _retry_after(response: httpx.Response) -> float | None:
    headers = getattr(response, "headers", {})
    value = headers.get("retry-after")
    try:
        return max(0.0, min(300.0, float(value))) if value else None
    except ValueError:
        return None


def _status_error(response: httpx.Response) -> ProviderError:
    status = response.status_code
    try:
        body = response.json()
        message = str(body.get("error", {}).get("message", body.get("message", "provider request failed")))
    except Exception:  # noqa: BLE001
        message = "provider request failed"
    if status in {401, 403}:
        return ProviderError("AUTH_INVALID", "Provider rejected the configured credential.", details={"http_status": status})
    if status == 404:
        return ProviderError("MODEL_NOT_FOUND", "The selected provider model or endpoint was not found.", details={"http_status": status})
    if status == 429:
        lower = message.lower()
        code = "QUOTA_EXHAUSTED" if "quota" in lower or "credit" in lower or "billing" in lower else "RATE_LIMITED"
        return ProviderError(code, "Provider rate or quota limit was reached.", retry_after=_retry_after(response), details={"http_status": status})
    if status in {413, 422}:
        return ProviderError("CONTEXT_TOO_LARGE", "The provider rejected the request size or schema.", details={"http_status": status})
    if 500 <= status < 600:
        return ProviderError("PROVIDER_UNAVAILABLE", "The provider service returned a temporary server error.", details={"http_status": status})
    if 300 <= status < 400:
        return ProviderError("PROVIDER_UNAVAILABLE", "Authenticated redirects are disabled for provider safety.", details={"http_status": status})
    return ProviderError("PROVIDER_RESPONSE_INVALID", f"Provider returned HTTP {status}.", details={"http_status": status})


LOCAL_PROVIDER_TIMEOUT_SECONDS = 300.0
LOCAL_PROVIDER_MAX_ATTEMPTS = 1


class OpenAICompatibleAdapter(ProviderAdapter):
    backend = "openai-compatible"

    def infer(self, request: InferenceRequest, *, use_cache: bool = True) -> InferenceResult:
        if self.model == "auto":
            models = self.model_listing()
            if not models:
                raise ProviderError("PROVIDER_UNAVAILABLE", "The local compatible server is stopped or has no models.")
            self.model = _pick_model(models)
            self.actual_model = self.model
        return super().infer(request, use_cache=use_cache)

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        strategy = self.profile.auth_strategy
        if strategy == "none":
            return headers
        if not self._secret:
            raise ProviderError("AUTH_INVALID", "This provider profile has no configured credential.")
        if strategy == "bearer":
            headers["authorization"] = f"Bearer {self._secret}"
        elif strategy == "api_key_header":
            headers["x-api-key"] = self._secret
        else:
            name = str(self.profile.metadata.get("secret_header_name", ""))
            if not re.fullmatch(r"[A-Za-z0-9!#$%&'*+.^_`|~-]{1,128}", name):
                raise ProviderError("AUTH_INVALID", "Custom secret header name is invalid.")
            headers[name] = self._secret
        return headers

    def _url(self, path: str) -> str:
        return self.profile.endpoint_identity.rstrip("/") + "/" + path.lstrip("/")

    def _model_records(self, *, strict: bool = False) -> list[dict[str, Any]]:
        try:
            response = httpx.get(self._url("models"), headers=self._headers(), timeout=min(10.0, self.profile.timeout_seconds), follow_redirects=False)
            if response.status_code >= 400:
                if strict:
                    raise _status_error(response)
                return []
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                if strict:
                    raise ProviderError("PROVIDER_RESPONSE_INVALID", "Provider returned an invalid model list.")
                return []
            return [
                item
                for item in payload["data"]
                if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip()
            ]
        except ProviderError:
            raise
        except httpx.TimeoutException as err:
            if strict:
                raise ProviderError("TIMEOUT", "Provider model listing timed out.") from err
            return []
        except httpx.HTTPError as err:
            if strict:
                raise ProviderError("NETWORK_FAILED", "Provider model listing failed.") from err
            return []
        except (JSONDecodeError, KeyError, TypeError) as err:
            if strict:
                raise ProviderError("PROVIDER_RESPONSE_INVALID", "Provider returned an invalid model list.") from err
            return []

    def model_listing(self) -> list[str]:
        return [str(item["id"]) for item in self._model_records()]

    def model_descriptors(self) -> list[dict[str, Any]]:
        return [describe_model(self.profile, str(item["id"]), item) for item in self._model_records(strict=True)]

    def _infer_uncached(self, request: InferenceRequest) -> tuple[dict[str, Any], list[str], str | None]:
        degraded: list[str] = []
        images = request.images
        if images and self.profile.capabilities.vision is False:
            if request.require_vision:
                raise ProviderError("VISION_UNSUPPORTED", "The selected model does not support vision.")
            images = []
            degraded.append("vision_unavailable")
        content: str | list[dict[str, Any]] = request.prompt
        if images:
            content = [{"type": "text", "text": request.prompt}]
            for image in images[: self.profile.capabilities.max_images or len(images)]:
                content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(image).decode()}})
        prompt = request.prompt
        if self.structured_level() == "text_compatibility":
            prompt += "\nReturn only one JSON object matching the supplied schema. Do not use Markdown fences."
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": request.temperature,
            "stream": False,
        }
        if request.purpose == "scoring" and self.profile.kind == "groq" and self.model.casefold().startswith("qwen/"):
            body["max_tokens"] = GROQ_QWEN_SCORING_MAX_OUTPUT_TOKENS
        if content != request.prompt:
            body["messages"][0]["content"][0]["text"] = prompt  # type: ignore[index]
        else:
            body["messages"][0]["content"] = prompt
        if self.structured_level() == "native_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "clipgauge",
                    "strict": True,
                    "schema": _strict_json_schema(request.schema),
                },
            }
        elif self.structured_level() == "json_mode":
            body["response_format"] = {"type": "json_object"}
        payload = self._post_json("chat/completions", body, request=request)
        routed_model = payload.get("model") if isinstance(payload, dict) else None
        if isinstance(routed_model, str) and routed_model.strip():
            self.actual_model = routed_model.strip()
        try:
            choice = payload["choices"][0]
            message = choice["message"]
            raw = message.get("content", "")
            if isinstance(raw, list):
                raw = "".join(str(part.get("text", "")) for part in raw if isinstance(part, dict))
            data = parse_json_text(str(raw))
            return data, degraded, response_request_id(payload)
        except (KeyError, IndexError, TypeError, ValueError, JSONDecodeError) as err:
            raise ProviderError("PROVIDER_RESPONSE_INVALID", "Provider returned no usable JSON content.") from err

    def _post_json(self, path: str, body: dict[str, Any], *, request: InferenceRequest | None = None) -> dict[str, Any]:
        last: ProviderError | None = None
        trace_local = self.profile.kind == "clipgauge-local"
        max_attempts = LOCAL_PROVIDER_MAX_ATTEMPTS if trace_local else 3
        self._request_number += 1
        request_number = self._request_number
        for attempt in range(max_attempts):
            started = time.monotonic()
            duration_ms = 0
            if trace_local:
                handle = getattr(getattr(self, "_runtime", None), "handle", None)
                memory = _memory_snapshot(handle.process.pid if handle else None)
                _local_qa_trace(
                    "request_start",
                    attempt=attempt + 1,
                    path=path,
                    timeout_seconds=self.profile.timeout_seconds,
                    requested_output_token_limit=body.get("max_tokens"),
                    prompt_chars=len(request.prompt) if request else None,
                    schema_keys=sorted(request.schema) if request else [],
                    has_images=bool(request.images) if request else False,
                    **memory,
                )
            try:
                response = self._post_request(
                    self._url(path),
                    headers=self._headers(),
                    json_body=body,
                    request=request,
                )
                duration_ms = int((time.monotonic() - started) * 1000)
                if response.status_code >= 400 or 300 <= response.status_code < 400:
                    error = _status_error(response)
                    last = error
                    if trace_local:
                        _local_qa_trace("request_http_error", attempt=attempt + 1, duration_ms=duration_ms, status_code=response.status_code, error_code=error.code)
                    if error.code in {"RATE_LIMITED", "PROVIDER_UNAVAILABLE", "NETWORK_FAILED", "TIMEOUT"} and attempt + 1 < max_attempts:
                        time.sleep(self.retry_delay(error, attempt, request))
                        continue
                    raise error
                payload = response.json()
                if trace_local:
                    usage = payload.get("usage") if isinstance(payload, dict) else None
                    timings = payload.get("timings") if isinstance(payload, dict) else None
                    choice = payload.get("choices", [{}])[0] if isinstance(payload, dict) and payload.get("choices") else {}
                    _local_qa_trace(
                        "request_success",
                        attempt=attempt + 1,
                        duration_ms=duration_ms,
                        status_code=response.status_code,
                        prompt_tokens=usage.get("prompt_tokens") if isinstance(usage, dict) else None,
                        completion_tokens=usage.get("completion_tokens") if isinstance(usage, dict) else None,
                        total_tokens=usage.get("total_tokens") if isinstance(usage, dict) else None,
                        timings={key: timings[key] for key in ("prompt_per_second", "predicted_per_second", "prompt_n", "predicted_n") if isinstance(timings, dict) and key in timings},
                        finish_reason=choice.get("finish_reason") if isinstance(choice, dict) else None,
                        **_memory_snapshot(handle.process.pid if handle else None),
                    )
                return payload
            except ProviderError as error:
                error.details = {
                    **self._failure_details(request_number, duration_ms, error),
                    **error.details,
                }
                raise
            except httpx.TimeoutException:
                duration_ms = int((time.monotonic() - started) * 1000)
                last = ProviderError("TIMEOUT", "Provider request timed out.")
                last.details = self._failure_details(request_number, duration_ms, last)
                if trace_local:
                    _local_qa_trace("request_timeout", attempt=attempt + 1, duration_ms=duration_ms, timeout_seconds=self.profile.timeout_seconds, **_memory_snapshot(handle.process.pid if handle else None))
                if self._scoring_request_aborted:
                    raise last
            except httpx.HTTPError:
                duration_ms = int((time.monotonic() - started) * 1000)
                last = ProviderError("NETWORK_FAILED", "Provider network request failed.")
                last.details = self._failure_details(request_number, duration_ms, last)
                if trace_local:
                    _local_qa_trace("request_network_error", attempt=attempt + 1, duration_ms=duration_ms)
            except JSONDecodeError as err:
                if trace_local:
                    _local_qa_trace("request_invalid_json", attempt=attempt + 1, duration_ms=int((time.monotonic() - started) * 1000))
                error = ProviderError("PROVIDER_RESPONSE_INVALID", "Provider returned malformed JSON.")
                error.details = self._failure_details(
                    request_number,
                    int((time.monotonic() - started) * 1000),
                    error,
                )
                raise error from err
            if attempt + 1 < max_attempts:
                time.sleep(self.retry_delay(last, attempt, request))
        if last:
            raise last
        error = ProviderError("INTERNAL_PROVIDER_ERROR", "Provider request failed.")
        error.details = self._failure_details(request_number, 0, error)
        raise error

    def _failure_details(
        self,
        request_number: int,
        duration_ms: int,
        error: ProviderError | None,
    ) -> dict[str, Any]:
        try:
            free_disk_bytes = shutil.disk_usage(config.home_dir().parent).free
        except OSError:
            free_disk_bytes = None
        details: dict[str, Any] = {
            "provider_code": error.code if error else None,
            "provider_kind": self.profile.kind,
            "request_number": request_number,
            "elapsed_ms": duration_ms,
            "timeout_seconds": self.profile.timeout_seconds,
            "structured_level": self.structured_level(),
            "structured_output_status": (
                "invalid"
                if error and error.code in {"STRUCTURED_OUTPUT_INVALID", "PROVIDER_RESPONSE_INVALID"}
                else "not_returned"
            ),
            "free_disk_bytes": free_disk_bytes,
        }
        context = self.failure_context()
        details.update(context)
        details.update(_memory_snapshot(context.get("runtime_pid")))
        return details


class ClipGaugeLocalAdapter(OpenAICompatibleAdapter):
    backend = "clipgauge-local"

    def __init__(self, profile: ProviderProfile, secret: str | None = None) -> None:
        super().__init__(profile, secret)
        self._runtime = local_runtime.LocalRuntime()
        self._endpoint = profile.endpoint_identity

    def _url(self, path: str) -> str:
        return self._endpoint.rstrip("/") + "/" + path.lstrip("/")

    def _ensure_runtime(self) -> None:
        if self.profile.metadata.get("managed", True) is False:
            return
        health_url = self._endpoint.rsplit("/v1", 1)[0] + "/health"
        try:
            response = httpx.get(health_url, timeout=0.5, follow_redirects=False)
            if response.status_code in {200, 204}:
                return
        except httpx.HTTPError:
            pass
        try:
            self._endpoint = self._runtime.start(self.model)
        except local_runtime.LocalRuntimeError as exc:
            raise ProviderError("PROVIDER_UNAVAILABLE", str(exc)) from exc

    def model_listing(self) -> list[str]:
        self._ensure_runtime()
        return [self.model]

    def infer(self, request: InferenceRequest, *, use_cache: bool = True) -> InferenceResult:
        self._ensure_runtime()
        return super().infer(request, use_cache=use_cache)

    def failure_context(self) -> dict[str, Any]:
        handle = self._runtime.handle
        process = handle.process if handle else None
        exit_code = process.poll() if process else None
        return {
            "runtime_alive": bool(process and exit_code is None),
            "runtime_pid": process.pid if process else None,
            "runtime_exit_code": exit_code,
        }

    def recover_for_scoring(self) -> dict[str, Any]:
        if self.profile.metadata.get("managed", True) is False:
            return {"recovered": False, "runtime_restarted": False, "runtime_alive": True}
        health_url = self._endpoint.rsplit("/v1", 1)[0] + "/health"
        try:
            response = httpx.get(health_url, timeout=0.5, follow_redirects=False)
            if response.status_code in {200, 204}:
                return {"recovered": True, "runtime_restarted": False, "runtime_alive": True}
        except httpx.HTTPError:
            pass
        self._runtime.stop()
        try:
            self._endpoint = self._runtime.start(self.model)
        except local_runtime.LocalRuntimeError as exc:
            raise ProviderError(
                "PROVIDER_UNAVAILABLE",
                "ClipGauge Local could not recover its managed runtime.",
                details={"runtime_alive": False},
            ) from exc
        return {"recovered": True, "runtime_restarted": True, "runtime_alive": True}

    def stop(self) -> None:
        self._runtime.stop()


class GeminiAdapter(ProviderAdapter):
    backend = "gemini"

    def _headers(self) -> dict[str, str]:
        if not self._secret:
            raise ProviderError("AUTH_INVALID", "No Gemini API key is configured.")
        return {"x-goog-api-key": self._secret}

    def _infer_uncached(self, request: InferenceRequest) -> tuple[dict[str, Any], list[str], str | None]:
        parts: list[dict[str, Any]] = [{"text": request.prompt}]
        for image in request.images:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image).decode()}})
        body = {"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json", "responseSchema": request.schema, "temperature": request.temperature}}
        response = self._post(body, request=request)
        try:
            raw = response["candidates"][0]["content"]["parts"][0]["text"]
            return parse_json_text(raw), [], response_request_id(response)
        except (KeyError, IndexError, TypeError, ValueError, JSONDecodeError) as err:
            raise ProviderError("PROVIDER_RESPONSE_INVALID", "Gemini returned no usable JSON content.") from err

    def _model_records(self, *, strict: bool = False) -> list[dict[str, Any]]:
        try:
            response = httpx.get(self.profile.endpoint_identity.rstrip("/") + "/models", headers=self._headers(), timeout=10.0, follow_redirects=False)
            if response.status_code >= 400:
                if strict:
                    raise _status_error(response)
                return []
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
                if strict:
                    raise ProviderError("PROVIDER_RESPONSE_INVALID", "Provider returned an invalid model list.")
                return []
            return [
                item
                for item in payload["models"]
                if isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and item["name"].strip()
                and isinstance(item.get("supportedGenerationMethods", ["generateContent"]), list)
                and "generateContent" in item.get("supportedGenerationMethods", ["generateContent"])
            ]
        except ProviderError:
            raise
        except httpx.TimeoutException as err:
            if strict:
                raise ProviderError("TIMEOUT", "Gemini model listing timed out.") from err
            return []
        except httpx.HTTPError as err:
            if strict:
                raise ProviderError("NETWORK_FAILED", "Gemini model listing failed.") from err
            return []
        except (JSONDecodeError, KeyError, TypeError) as err:
            if strict:
                raise ProviderError("PROVIDER_RESPONSE_INVALID", "Provider returned an invalid model list.") from err
            return []

    def model_listing(self) -> list[str]:
        return [str(item["name"]).split("models/", 1)[-1] for item in self._model_records()]

    def model_descriptors(self) -> list[dict[str, Any]]:
        descriptors = []
        for item in self._model_records(strict=True):
            metadata: dict[str, Any] = {}
            input_limit = item.get("inputTokenLimit")
            if isinstance(input_limit, int) and input_limit > 0:
                metadata["context_length"] = input_limit
            descriptors.append(describe_model(self.profile, str(item["name"]).split("models/", 1)[-1], metadata))
        return descriptors

    def _post(self, body: dict[str, Any], *, request: InferenceRequest | None = None) -> dict[str, Any]:
        url = self.profile.endpoint_identity.rstrip("/") + f"/models/{self.model}:generateContent"
        last: ProviderError | None = None
        for attempt in range(3):
            try:
                response = self._post_request(
                    url,
                    headers=self._headers(),
                    json_body=body,
                    request=request,
                )
                if response.status_code >= 400:
                    error = _status_error(response)
                    last = error
                    if error.code in {"RATE_LIMITED", "PROVIDER_UNAVAILABLE"} and attempt < 2:
                        time.sleep(self.retry_delay(error, attempt, request))
                        continue
                    raise error
                return response.json()
            except ProviderError:
                raise
            except httpx.TimeoutException as err:
                last = ProviderError("TIMEOUT", "Gemini request timed out.")
                if self._scoring_request_aborted:
                    raise last
            except httpx.HTTPError as err:
                last = ProviderError("NETWORK_FAILED", "Gemini network request failed.")
            except JSONDecodeError as err:
                raise ProviderError("PROVIDER_RESPONSE_INVALID", "Gemini returned malformed JSON.") from err
            if attempt < 2:
                time.sleep(self.retry_delay(last, attempt, request))
        raise last or ProviderError("INTERNAL_PROVIDER_ERROR", "Gemini request failed.")


class OllamaAdapter(ProviderAdapter):
    backend = "ollama"

    def infer(self, request: InferenceRequest, *, use_cache: bool = True) -> InferenceResult:
        if self.model == "auto":
            models = self.model_listing()
            if not models:
                raise ProviderError("PROVIDER_UNAVAILABLE", "Ollama is stopped or has no installed models.")
            self.model = _pick_model(models)
            self.actual_model = self.model
        return super().infer(request, use_cache=use_cache)

    def _url(self, path: str) -> str:
        return self.profile.endpoint_identity.rstrip("/") + "/" + path.lstrip("/")

    def _model_records(self, *, strict: bool = False) -> list[dict[str, Any]]:
        try:
            response = httpx.get(self._url("api/tags"), timeout=5.0, follow_redirects=False)
            if response.status_code >= 400:
                if strict:
                    raise _status_error(response)
                return []
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
                if strict:
                    raise ProviderError("PROVIDER_RESPONSE_INVALID", "Ollama returned an invalid model list.")
                return []
            return [
                item
                for item in payload["models"]
                if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip()
            ]
        except ProviderError:
            raise
        except httpx.TimeoutException as err:
            if strict:
                raise ProviderError("TIMEOUT", "Ollama model listing timed out.") from err
            return []
        except httpx.HTTPError as err:
            if strict:
                raise ProviderError("NETWORK_FAILED", "Ollama model listing failed.") from err
            return []
        except (JSONDecodeError, KeyError, TypeError) as err:
            if strict:
                raise ProviderError("PROVIDER_RESPONSE_INVALID", "Ollama returned an invalid model list.") from err
            return []

    def model_listing(self) -> list[str]:
        return [str(item["name"]) for item in self._model_records()]

    def model_descriptors(self) -> list[dict[str, Any]]:
        return [describe_model(self.profile, str(item["name"]), item) for item in self._model_records(strict=True)]

    def _infer_uncached(self, request: InferenceRequest) -> tuple[dict[str, Any], list[str], str | None]:
        models = self.model_listing()
        if not models:
            raise ProviderError("PROVIDER_UNAVAILABLE", "Ollama is stopped or has no installed models.")
        if self.model == "auto":
            self.model = _pick_model(models)
        if self.model not in models:
            raise ProviderError("MODEL_NOT_FOUND", f"Ollama model {self.model!r} is not installed.")
        degraded: list[str] = []
        message: dict[str, Any] = {"role": "user", "content": request.prompt}
        if request.images and self.profile.capabilities.vision is not False:
            message["images"] = [base64.b64encode(image).decode() for image in request.images[: self.profile.capabilities.max_images or len(request.images)]]
        elif request.images:
            if request.require_vision:
                raise ProviderError("VISION_UNSUPPORTED", "The selected Ollama model does not support vision.")
            degraded.append("vision_unavailable")
        body = {"model": self.model, "messages": [message], "format": request.schema, "stream": False, "options": {"temperature": request.temperature}}
        try:
            response = self._post_request(
                self._url("api/chat"),
                json_body=body,
                request=request,
            )
            if response.status_code >= 400:
                raise _status_error(response)
            payload = response.json()
            data = parse_json_text(payload["message"]["content"])
            return data, degraded, response_request_id(payload)
        except ProviderError:
            raise
        except httpx.TimeoutException as err:
            raise ProviderError("TIMEOUT", "Ollama request timed out.") from err
        except httpx.HTTPError as err:
            raise ProviderError("NETWORK_FAILED", "Ollama request failed.") from err
        except (JSONDecodeError, KeyError, TypeError, ValueError) as err:
            raise ProviderError("PROVIDER_RESPONSE_INVALID", "Ollama returned malformed structured output.") from err


def response_request_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("id") or payload.get("request_id")
    return str(value)[:160] if value else None


def _pick_model(models: list[str]) -> str:
    def size(name: str) -> float:
        match = re.search(r"(\d+(?:\.\d+)?)b", name.lower())
        return float(match.group(1)) if match else 0.0

    preferred = [m for prefix in ("llama3", "qwen", "mistral", "gemma") for m in models if m.startswith(prefix)]
    return max(preferred or models, key=size)


def secret_from_environment(profile: ProviderProfile) -> str | None:
    if profile.auth_strategy == "none":
        return None
    names = {
        "gemini": "CLIPGAUGE_GEMINI_API_KEY",
        "openrouter": "CLIPGAUGE_OPENROUTER_API_KEY",
        "groq": "CLIPGAUGE_GROQ_API_KEY",
        "cloudflare": "CLIPGAUGE_CLOUDFLARE_API_TOKEN",
        "huggingface": "CLIPGAUGE_HF_TOKEN",
        "cerebras": "CLIPGAUGE_CEREBRAS_API_KEY",
    }
    name = names.get(profile.kind, "CLIPGAUGE_PROVIDER_SECRET")
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


def profile_from_snapshot(snapshot: dict[str, Any]) -> ProviderProfile:
    kind = str(snapshot.get("kind", "gemini"))
    defaults = preset_profile(kind) if kind == "clipgauge-local" else legacy_profile(kind if kind in {"gemini", "ollama"} else "gemini")
    base_url = str(snapshot.get("endpoint_identity") or defaults.base_url)
    auth_strategy = str(snapshot.get("auth_strategy") or defaults.auth_strategy)
    locality = str(snapshot.get("locality") or defaults.locality)
    return ProviderProfile(
        schema_version=int(snapshot.get("schema_version", 1)),
        id=str(snapshot.get("id") or defaults.id),
        kind=kind,
        display_name=str(snapshot.get("display_name") or kind.title()),
        base_url=base_url,
        model=str(snapshot.get("model") or defaults.model),
        auth_strategy=auth_strategy,
        secret_ref=snapshot.get("secret_ref"),
        capabilities=CapabilitySet.from_dict(snapshot.get("capabilities")),
        locality=locality,
        enabled=bool(snapshot.get("enabled", True)),
        timeout_seconds=float(snapshot.get("timeout_seconds", defaults.timeout_seconds)),
        metadata=dict(snapshot.get("metadata") or {}),
    )


def preset_profile(
    kind: str,
    *,
    model: str | None = None,
    endpoint: str | None = None,
    auth_strategy: str | None = None,
    secret_header_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ProviderProfile:
    kind = kind.strip().lower()
    if kind in {"gemini", "ollama"}:
        base = legacy_profile(kind, model)
        if endpoint or metadata:
            return ProviderProfile(
                schema_version=base.schema_version,
                id=base.id,
                kind=base.kind,
                display_name=base.display_name,
                base_url=endpoint or base.base_url,
                model=model or base.model,
                auth_strategy=base.auth_strategy,
                secret_ref=base.secret_ref,
                capabilities=base.capabilities,
                locality=base.locality,
                metadata=metadata or {},
            )
        return base
    defaults: dict[str, tuple[str, str, str]] = {
        "clipgauge-local": ("ClipGauge Local", "http://127.0.0.1:8080/v1", "clipgauge-local/qwen3-4b-q4_k_m"),
        "lmstudio": ("LM Studio", "http://127.0.0.1:1234/v1", "auto"),
        "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1", "openrouter/free"),
        "groq": ("Groq", "https://api.groq.com/openai/v1", "openai/gpt-oss-20b"),
        "cloudflare": ("Cloudflare Workers AI", "", "@cf/meta/llama-3.1-8b-instruct"),
        "huggingface": ("Hugging Face", "https://router.huggingface.co/v1", "Qwen/Qwen3-32B"),
        "cerebras": ("Cerebras", "https://api.cerebras.ai/v1", "gpt-oss-120b"),
        "custom": ("Custom OpenAI-compatible", "", ""),
    }
    if kind not in defaults:
        raise ValueError(f"unknown provider kind: {kind}")
    display, default_endpoint, default_model = defaults[kind]
    # Windows packaged UI qualification may provide a loopback OpenAI-compatible
    # fixture. It is opt-in, never overrides an explicit endpoint, and does not
    # change normal provider behavior or credential handling.
    qa_endpoint = os.environ.get("CLIPGAUGE_QA_OPENROUTER_ENDPOINT") if kind == "openrouter" else None
    selected_endpoint = endpoint or qa_endpoint or default_endpoint
    if not selected_endpoint:
        raise ValueError(f"provider {kind} requires an explicit endpoint")
    selected_model = model or default_model
    if not selected_model:
        raise ValueError(f"provider {kind} requires a model")
    selected_auth = auth_strategy or ("none" if kind in {"custom", "lmstudio", "clipgauge-local"} else "bearer")
    selected_metadata = dict(metadata or {})
    if secret_header_name:
        selected_metadata["secret_header_name"] = secret_header_name
    capability_defaults = {
        "clipgauge-local": {"structured_json": True, "json_schema": True, "vision": False},
        "groq": {"structured_json": True, "json_schema": True, "vision": None},
        "cloudflare": {"structured_json": True, "json_schema": None, "vision": None},
        "huggingface": {"structured_json": True, "json_schema": True, "vision": None},
        "cerebras": {"structured_json": True, "json_schema": True, "vision": False},
    }
    selected_caps = capability_defaults.get(kind, {"structured_json": None, "json_schema": None, "vision": None})
    local = kind in {"lmstudio", "clipgauge-local"}
    caps = CapabilitySet(
        structured_json=selected_caps["structured_json"],
        json_schema=selected_caps["json_schema"],
        vision=selected_caps["vision"],
        model_listing=True,
        local=local,
        cloud=not local,
    )
    return ProviderProfile(
        schema_version=1,
        id=f"preset-{kind}",
        kind=kind,
        display_name=display,
        base_url=selected_endpoint,
        model=selected_model,
        auth_strategy=selected_auth,
        secret_ref=f"provider:{kind}",
        capabilities=caps,
        locality="local" if local else "cloud",
        timeout_seconds=LOCAL_PROVIDER_TIMEOUT_SECONDS if kind == "clipgauge-local" else 120.0,
        metadata={"managed": kind == "clipgauge-local", **selected_metadata},
    )


def make_adapter(profile_or_mode: ProviderProfile | str, secret: str | None = None) -> ProviderAdapter:
    if isinstance(profile_or_mode, str):
        profile = preset_profile(profile_or_mode) if profile_or_mode.strip().lower() == "clipgauge-local" else legacy_profile(profile_or_mode)
    else:
        profile = profile_or_mode
    secret = secret if secret is not None else secret_from_environment(profile)
    if profile.kind == "gemini":
        return GeminiAdapter(profile, secret)
    if profile.kind == "ollama":
        return OllamaAdapter(profile, secret)
    if profile.kind == "clipgauge-local":
        return ClipGaugeLocalAdapter(profile, secret)
    return OpenAICompatibleAdapter(profile, secret)
