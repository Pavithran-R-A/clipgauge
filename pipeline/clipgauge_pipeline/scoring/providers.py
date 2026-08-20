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
import time
from dataclasses import asdict, dataclass, field
from json import JSONDecodeError
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx

from .. import config, protocol

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
        validate_base_url(self.base_url, allow_remote_http=self.locality == "local")
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


def validate_base_url(value: str, *, allow_remote_http: bool = False) -> str:
    normalized = normalize_base_url(value)
    parts = urlsplit(normalized)
    if parts.scheme not in {"https", "http"}:
        raise ValueError("provider base URL scheme must be HTTPS or approved HTTP")
    host = (parts.hostname or "").lower()
    loopback = host in {"127.0.0.1", "localhost", "::1"}
    if parts.scheme == "http" and not (loopback or allow_remote_http):
        raise ValueError("remote HTTP provider endpoints require explicit approval")
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
    ) -> None:
        if code not in ERROR_CODES:
            code = "INTERNAL_PROVIDER_ERROR"
        self.code = code
        self.message = protocol.safe_message(message, limit=300)
        self.retry_after = retry_after
        super().__init__(self.message)


class ProviderAdapter:
    backend = "provider"

    def __init__(self, profile: ProviderProfile, secret: str | None = None) -> None:
        self.profile = profile
        self.model = profile.model
        self._secret = secret.strip() if secret and secret.strip() else None
        self.last_result: InferenceResult | None = None

    @property
    def backend_name(self) -> str:
        return self.profile.kind

    @property
    def supports_vision(self) -> bool:
        return self.profile.capabilities.vision is True

    def cache_file(self, request: InferenceRequest) -> Any:
        return _cache_dir() / f"{cache_key(self.profile, request)}.json"

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

    def infer(self, request: InferenceRequest) -> InferenceResult:
        if request.require_vision and self.profile.capabilities.vision is False:
            raise ProviderError("VISION_UNSUPPORTED", "The selected model does not support vision.")
        if request.max_images is not None and len(request.images) > request.max_images:
            raise ProviderError("VISION_UNSUPPORTED", "Too many images were supplied for this provider.")
        cache_file = self.cache_file(request)
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text())
                validate_json_schema(data, request.schema)
                result = InferenceResult(
                    data=data,
                    provider_profile_id=self.profile.id,
                    provider_kind=self.profile.kind,
                    model=self.model,
                    capabilities_used={"cache": True},
                    degraded_signals=[],
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
        cache_file.write_text(json.dumps(data, sort_keys=True))
        result = InferenceResult(
            data=data,
            provider_profile_id=self.profile.id,
            provider_kind=self.profile.kind,
            model=self.model,
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
                )
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


def cache_key(profile: ProviderProfile, request: InferenceRequest) -> str:
    h = hashlib.sha256()
    fields = {
        "schema_version": 1,
        "profile_id": profile.id,
        "kind": profile.kind,
        "model": profile.model,
        "endpoint": profile.endpoint_identity,
        "prompt": request.prompt,
        "schema": request.schema,
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
    value = response.headers.get("retry-after")
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
        return ProviderError("AUTH_INVALID", "Provider rejected the configured credential.")
    if status == 404:
        return ProviderError("MODEL_NOT_FOUND", "The selected provider model or endpoint was not found.")
    if status == 429:
        lower = message.lower()
        code = "QUOTA_EXHAUSTED" if "quota" in lower or "credit" in lower or "billing" in lower else "RATE_LIMITED"
        return ProviderError(code, "Provider rate or quota limit was reached.", retry_after=_retry_after(response))
    if status in {413, 422}:
        return ProviderError("CONTEXT_TOO_LARGE", "The provider rejected the request size or schema.")
    if 500 <= status < 600:
        return ProviderError("PROVIDER_UNAVAILABLE", "The provider service returned a temporary server error.")
    if 300 <= status < 400:
        return ProviderError("PROVIDER_UNAVAILABLE", "Authenticated redirects are disabled for provider safety.")
    return ProviderError("PROVIDER_RESPONSE_INVALID", f"Provider returned HTTP {status}.")


class OpenAICompatibleAdapter(ProviderAdapter):
    backend = "openai-compatible"

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

    def model_listing(self) -> list[str]:
        try:
            response = httpx.get(self._url("models"), headers=self._headers(), timeout=min(10.0, self.profile.timeout_seconds), follow_redirects=False)
            if response.status_code >= 400:
                return []
            payload = response.json()
            return [str(item["id"]) for item in payload.get("data", []) if isinstance(item, dict) and item.get("id")]
        except (httpx.HTTPError, JSONDecodeError, KeyError, TypeError):
            return []

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
        if content != request.prompt:
            body["messages"][0]["content"][0]["text"] = prompt  # type: ignore[index]
        else:
            body["messages"][0]["content"] = prompt
        if self.structured_level() == "native_schema":
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "clipgauge", "strict": True, "schema": request.schema}}
        elif self.structured_level() == "json_mode":
            body["response_format"] = {"type": "json_object"}
        payload = self._post_json("chat/completions", body)
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

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        last: ProviderError | None = None
        for attempt in range(3):
            try:
                response = httpx.post(self._url(path), headers=self._headers(), json=body, timeout=self.profile.timeout_seconds, follow_redirects=False)
                if response.status_code >= 400 or 300 <= response.status_code < 400:
                    error = _status_error(response)
                    last = error
                    if error.code in {"RATE_LIMITED", "PROVIDER_UNAVAILABLE", "NETWORK_FAILED", "TIMEOUT"} and attempt < 2:
                        time.sleep(error.retry_after if error.retry_after is not None else 2**attempt)
                        continue
                    raise error
                return response.json()
            except ProviderError:
                raise
            except httpx.TimeoutException as err:
                last = ProviderError("TIMEOUT", "Provider request timed out.")
            except httpx.HTTPError as err:
                last = ProviderError("NETWORK_FAILED", "Provider network request failed.")
            except JSONDecodeError as err:
                raise ProviderError("PROVIDER_RESPONSE_INVALID", "Provider returned malformed JSON.") from err
            if attempt < 2:
                time.sleep(2**attempt)
        raise last or ProviderError("INTERNAL_PROVIDER_ERROR", "Provider request failed.")


class GeminiAdapter(ProviderAdapter):
    backend = "gemini"

    def _headers(self) -> dict[str, str]:
        if not self._secret:
            raise ProviderError("AUTH_INVALID", "No Gemini API key is configured.")
        return {"x-goog-api-key": self._secret, "content-type": "application/json"}

    def _infer_uncached(self, request: InferenceRequest) -> tuple[dict[str, Any], list[str], str | None]:
        parts: list[dict[str, Any]] = [{"text": request.prompt}]
        for image in request.images:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image).decode()}})
        body = {"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json", "responseSchema": request.schema, "temperature": request.temperature}}
        response = self._post(body)
        try:
            raw = response["candidates"][0]["content"]["parts"][0]["text"]
            return parse_json_text(raw), [], response_request_id(response)
        except (KeyError, IndexError, TypeError, ValueError, JSONDecodeError) as err:
            raise ProviderError("PROVIDER_RESPONSE_INVALID", "Gemini returned no usable JSON content.") from err

    def model_listing(self) -> list[str]:
        try:
            response = httpx.get(self.profile.endpoint_identity.rstrip("/") + "/models", headers=self._headers(), timeout=10.0, follow_redirects=False)
            if response.status_code >= 400:
                return []
            return [str(item["name"]).split("models/", 1)[-1] for item in response.json().get("models", []) if isinstance(item, dict) and item.get("name")]
        except (httpx.HTTPError, JSONDecodeError, KeyError, TypeError):
            return []

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        url = self.profile.endpoint_identity.rstrip("/") + f"/models/{self.model}:generateContent"
        last: ProviderError | None = None
        for attempt in range(3):
            try:
                response = httpx.post(url, headers=self._headers(), json=body, timeout=self.profile.timeout_seconds, follow_redirects=False)
                if response.status_code >= 400:
                    error = _status_error(response)
                    last = error
                    if error.code in {"RATE_LIMITED", "PROVIDER_UNAVAILABLE"} and attempt < 2:
                        time.sleep(error.retry_after if error.retry_after is not None else 2**attempt)
                        continue
                    raise error
                return response.json()
            except ProviderError:
                raise
            except httpx.TimeoutException as err:
                last = ProviderError("TIMEOUT", "Gemini request timed out.")
            except httpx.HTTPError as err:
                last = ProviderError("NETWORK_FAILED", "Gemini network request failed.")
            except JSONDecodeError as err:
                raise ProviderError("PROVIDER_RESPONSE_INVALID", "Gemini returned malformed JSON.") from err
        raise last or ProviderError("INTERNAL_PROVIDER_ERROR", "Gemini request failed.")


class OllamaAdapter(ProviderAdapter):
    backend = "ollama"

    def infer(self, request: InferenceRequest) -> InferenceResult:
        if self.model == "auto":
            models = self.model_listing()
            if not models:
                raise ProviderError("PROVIDER_UNAVAILABLE", "Ollama is stopped or has no installed models.")
            self.model = _pick_model(models)
        return super().infer(request)

    def _url(self, path: str) -> str:
        return self.profile.endpoint_identity.rstrip("/") + "/" + path.lstrip("/")

    def model_listing(self) -> list[str]:
        try:
            response = httpx.get(self._url("api/tags"), timeout=5.0, follow_redirects=False)
            response.raise_for_status()
            return [str(item["name"]) for item in response.json().get("models", []) if isinstance(item, dict) and item.get("name")]
        except (httpx.HTTPError, JSONDecodeError, KeyError, TypeError):
            return []

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
            response = httpx.post(self._url("api/chat"), json=body, timeout=self.profile.timeout_seconds, follow_redirects=False)
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
    defaults = legacy_profile(kind if kind in {"gemini", "ollama"} else "gemini")
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


def make_adapter(profile_or_mode: ProviderProfile | str, secret: str | None = None) -> ProviderAdapter:
    profile = legacy_profile(profile_or_mode) if isinstance(profile_or_mode, str) else profile_or_mode
    secret = secret if secret is not None else secret_from_environment(profile)
    if profile.kind == "gemini":
        return GeminiAdapter(profile, secret)
    if profile.kind == "ollama":
        return OllamaAdapter(profile, secret)
    return OpenAICompatibleAdapter(profile, secret)
