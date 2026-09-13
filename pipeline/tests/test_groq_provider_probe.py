from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "qa_groq_provider_probe.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("CLIPGAUGE_GROQ_API_KEY", None)
    environment["PYTHONPATH"] = str(SCRIPT.parents[1] / "pipeline")
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def test_groq_probe_requires_a_model_argument():
    result = _run()

    assert result.returncode == 2
    assert "usage:" in result.stderr.lower()


def test_groq_probe_reports_missing_credential_without_traceback():
    result = _run("openai/gpt-oss-20b")

    assert result.returncode == 2
    assert json.loads(result.stdout) == {
        "model": "openai/gpt-oss-20b",
        "exception_type": "MissingCredential",
    }
    assert "Traceback" not in result.stderr
