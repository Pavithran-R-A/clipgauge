#!/usr/bin/env python3
"""Validate a generated ClipGauge CycloneDX SBOM against a release tag."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPOSITORY = "Pavithran-R-A/clipgauge"
FORBIDDEN_SOURCE_COMMIT = "c4f4a1f5cae4cdfc7b98c719387946896062e7fb"


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sbom", type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--expected-commit")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    errors: list[str] = []
    try:
        data = json.loads(args.sbom.read_text())
    except Exception as exc:
        print(f"SBOM validation FAILED: invalid JSON: {exc}")
        return 1

    expected_version_match = re.fullmatch(r"v(\d+\.\d+\.\d+)", args.tag)
    if expected_version_match is None:
        errors.append(f"invalid release tag {args.tag!r}")
        expected_version = ""
    else:
        expected_version = expected_version_match.group(1)

    try:
        expected_commit = args.expected_commit or git(root, "rev-parse", f"{args.tag}^{{}}")
    except subprocess.CalledProcessError:
        errors.append(f"cannot resolve release tag {args.tag}")
        expected_commit = ""

    if data.get("bomFormat") != "CycloneDX":
        errors.append(f"bomFormat must be CycloneDX, found {data.get('bomFormat')!r}")
    if data.get("specVersion") not in {"1.4", "1.5", "1.6"}:
        errors.append(f"unsupported or missing CycloneDX specVersion: {data.get('specVersion')!r}")

    text = json.dumps(data, sort_keys=True)
    if FORBIDDEN_SOURCE_COMMIT in text:
        errors.append("forbidden stale v0.1.0 tag object is present")

    metadata = data.get("metadata", {})
    metadata_component = metadata.get("component", {})
    if metadata_component.get("name") != "ClipGauge":
        errors.append(f"metadata component must be ClipGauge, found {metadata_component.get('name')!r}")
    if metadata_component.get("version") != expected_version:
        errors.append("metadata component version does not match release tag")

    properties = {p.get("name"): p.get("value") for p in metadata.get("properties", [])}
    if properties.get("source.repository") != REPOSITORY:
        errors.append(f"source.repository must be {REPOSITORY!r}")
    if properties.get("source.tag") != args.tag:
        errors.append("source.tag does not match requested release tag")
    if properties.get("source.commit") != expected_commit:
        errors.append(f"source.commit must equal peeled tag commit {expected_commit!r}")

    components = data.get("components")
    if not isinstance(components, list) or not components:
        errors.append("components must be a non-empty array")
        components = []
    refs = [component.get("bom-ref") for component in components]
    if any(not ref for ref in refs):
        errors.append("every component must have a BOM reference")
    if len(refs) != len(set(refs)):
        errors.append("duplicate component BOM references found")

    first_party = [component for component in components if component.get("scope") == "first-party"]
    expected_first_party = {"ClipGauge desktop application", "ClipGauge Python pipeline"}
    found_first_party = {component.get("name") for component in first_party}
    if found_first_party != expected_first_party:
        errors.append(f"first-party components mismatch: expected {sorted(expected_first_party)}, found {sorted(found_first_party)}")
    for component in first_party:
        if not component.get("version"):
            errors.append(f"first-party component has empty version: {component.get('name')!r}")
        if not component.get("purl"):
            errors.append(f"first-party component has empty purl: {component.get('name')!r}")

    if errors:
        print("SBOM validation FAILED:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(f"SBOM validation passed for {args.tag} at {expected_commit}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
