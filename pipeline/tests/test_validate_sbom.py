from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "validate-sbom.py"


def test_validate_sbom_reports_malformed_object_shapes(tmp_path: Path):
    sbom = tmp_path / "malformed.json"
    sbom.write_text(json.dumps({"metadata": [], "components": [None]}), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(sbom), "--tag", "v0.5.15"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "metadata must be an object" in result.stdout
    assert "components entries must be objects" in result.stdout
