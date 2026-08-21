#!/usr/bin/env python3
"""Validate ClipGauge's authoritative current-release version sources."""
from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

EXPECTED = "0.2.1"
ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover - diagnostic path
        errors.append(f"{path}: invalid JSON: {exc}")
        return {}


def read_toml(path: Path):
    try:
        return tomllib.loads(path.read_text())
    except Exception as exc:  # pragma: no cover - diagnostic path
        errors.append(f"{path}: invalid TOML: {exc}")
        return {}


def require(label: str, actual: object, expected: str = EXPECTED) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected!r}, found {actual!r}")


package_json_path = ROOT / "app/package.json"
package_json = read_json(package_json_path)
require("app/package.json version", package_json.get("version"))

package_lock_path = ROOT / "app/package-lock.json"
package_lock = read_json(package_lock_path)
require("app/package-lock.json version", package_lock.get("version"))
require("app/package-lock.json root package version", package_lock.get("packages", {}).get("", {}).get("version"))

cargo_toml_path = ROOT / "app/src-tauri/Cargo.toml"
cargo_toml = read_toml(cargo_toml_path)
require("Cargo.toml package version", cargo_toml.get("package", {}).get("version"))

cargo_lock_path = ROOT / "app/src-tauri/Cargo.lock"
cargo_lock = read_toml(cargo_lock_path)
clipgauge_lock_entries = [p for p in cargo_lock.get("package", []) if p.get("name") == "clipgauge-app"]
if len(clipgauge_lock_entries) != 1:
    errors.append(f"Cargo.lock: expected exactly one clipgauge-app package entry, found {len(clipgauge_lock_entries)}")
else:
    require("Cargo.lock clipgauge-app version", clipgauge_lock_entries[0].get("version"))

tauri_path = ROOT / "app/src-tauri/tauri.conf.json"
tauri = read_json(tauri_path)
require("tauri.conf.json version", tauri.get("version"))

pyproject_path = ROOT / "pipeline/pyproject.toml"
pyproject = read_toml(pyproject_path)
require("pipeline/pyproject.toml version", pyproject.get("project", {}).get("version"))

init_path = ROOT / "pipeline/clipgauge_pipeline/__init__.py"
init_text = init_path.read_text()
init_match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']\s*$', init_text, re.MULTILINE)
require("clipgauge_pipeline.__version__", init_match.group(1) if init_match else None)

changelog = (ROOT / "CHANGELOG.md").read_text()
if not re.search(r"^## \[0\.2\.1\](?:\s|$)", changelog, re.MULTILINE):
    errors.append("CHANGELOG.md: missing current v0.2.1 section")

readme = (ROOT / "README.md").read_text()
if "ClipGauge v0.2.1" not in readme:
    errors.append("README.md: missing current ClipGauge v0.2.1 marker")
if "unsigned release candidate" in readme.lower():
    errors.append("README.md: stale 'unsigned release candidate' wording remains")

about = (ROOT / "app/src/components/About.tsx").read_text()
if "ClipGauge v0.2.1" not in about:
    errors.append("About.tsx: missing current ClipGauge v0.2.1 marker")

if errors:
    print("Version consistency check FAILED:")
    print("\n".join(f"- {error}" for error in errors))
    sys.exit(1)

print(f"Version consistency check passed: all authoritative current-release sources report {EXPECTED}.")
