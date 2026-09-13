"""Probe configured Groq model capability without exposing credentials."""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

from clipgauge_pipeline.scoring import providers, rubric


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", help="Groq model identifier to probe")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    model = args.model
    api_key = os.environ.get("CLIPGAUGE_GROQ_API_KEY")
    if not api_key:
        print(json.dumps({"model": model, "exception_type": "MissingCredential"}, separators=(",", ":")))
        return 2
    headers = {"authorization": f"Bearer {api_key}"}
    result: dict[str, object] = {"model": model}
    try:
        response = httpx.get(
            "https://api.groq.com/openai/v1/models",
            headers=headers,
            timeout=20,
            follow_redirects=False,
        )
        result["models_status"] = response.status_code
        if response.status_code == 200:
            payload = response.json()
            rows = payload.get("data", []) if isinstance(payload, dict) else []
            result["model_count"] = len(rows)
            for row in rows:
                if isinstance(row, dict) and row.get("id") == model:
                    result["model_record"] = {
                        key: row.get(key)
                        for key in (
                            "id",
                            "owned_by",
                            "context_window",
                            "active",
                            "supported_parameters",
                        )
                        if key in row
                    }
                    break
        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        }
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "Return exactly one JSON object with ok true."}],
            "temperature": 0,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "probe", "strict": True, "schema": schema},
            },
        }
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={**headers, "content-type": "application/json"},
            json=body,
            timeout=60,
            follow_redirects=False,
        )
        result["probe_status"] = response.status_code
        try:
            payload = response.json()
            result["response_keys"] = sorted(payload.keys()) if isinstance(payload, dict) else []
            if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
                result["error_type"] = payload["error"].get("type")
                result["error_code"] = payload["error"].get("code")
            choices = payload.get("choices", []) if isinstance(payload, dict) else []
            if choices and isinstance(choices[0], dict):
                choice = choices[0]
                result["finish_reason"] = choice.get("finish_reason")
                message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
                content = message.get("content")
                result["content_type"] = type(content).__name__
                result["content_length"] = len(content) if isinstance(content, str) else None
                result["has_reasoning"] = bool(message.get("reasoning"))
        except Exception as exc:  # noqa: BLE001 - bounded diagnostic only
            result["response_parse_error"] = type(exc).__name__

        scoring_schema = rubric.schema_for_model(model)
        scoring_body = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": rubric.t1_prompt(
                        "S0001 (speaker 0): The plane is coming in low.\n"
                        "S0002 (speaker 0): Hold on tight.",
                        {"duration": 5, "events_desc": "none detected"},
                    ),
                }
            ],
            "temperature": 0,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "clipgauge",
                    "strict": True,
                    "schema": providers._strict_json_schema(scoring_schema),
                },
            },
        }
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={**headers, "content-type": "application/json"},
            json=scoring_body,
            timeout=60,
            follow_redirects=False,
        )
        result["scoring_probe_status"] = response.status_code
        try:
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
                result["scoring_error_type"] = payload["error"].get("type")
                result["scoring_error_code"] = payload["error"].get("code")
                result["scoring_error_message"] = str(payload["error"].get("message", ""))[:240]
            choices = payload.get("choices", []) if isinstance(payload, dict) else []
            message = choices[0].get("message", {}) if choices and isinstance(choices[0], dict) else {}
            content = message.get("content") if isinstance(message, dict) else None
            result["scoring_content_type"] = type(content).__name__
            result["scoring_content_length"] = len(content) if isinstance(content, str) else None
            result["scoring_finish_reason"] = choices[0].get("finish_reason") if choices and isinstance(choices[0], dict) else None
            result["scoring_has_reasoning"] = bool(message.get("reasoning")) if isinstance(message, dict) else False
            if isinstance(content, str):
                try:
                    parsed = providers.parse_json_text(content)
                    providers.validate_json_schema(parsed, scoring_schema)
                    result["scoring_json_valid"] = True
                    result["scoring_keys"] = sorted(parsed)
                except Exception as exc:  # noqa: BLE001 - bounded diagnostic only
                    result["scoring_json_valid"] = False
                    result["scoring_json_error"] = type(exc).__name__
                    stripped = content.strip()
                    result["scoring_first_char"] = stripped[:1]
                    result["scoring_last_char"] = stripped[-1:] if stripped else ""
        except Exception as exc:  # noqa: BLE001 - bounded diagnostic only
            result["scoring_response_parse_error"] = type(exc).__name__
    except Exception as exc:  # noqa: BLE001 - bounded diagnostic only
        result["exception_type"] = type(exc).__name__
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
