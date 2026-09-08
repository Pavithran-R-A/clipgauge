import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate-model-e2e.py"
SPEC = importlib.util.spec_from_file_location("validate_model_e2e", SCRIPT)
assert SPEC and SPEC.loader
validate_model_e2e = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_model_e2e)


def test_no_recommendations_accepts_analysis_only_run(tmp_path, monkeypatch, capsys):
    log = tmp_path / "model-e2e.jsonl"
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    output = tmp_path / "summary.json"
    stages = ["ingest", "asr", "diarize", "events", "candidates", "score"]
    events = [
        {"event": "progress", "stage": stage, "operation": "done"}
        for stage in stages
    ]
    events.append(
        {
            "event": "terminal",
            "ok": True,
            "code": "NO_RECOMMENDED_CLIPS",
            "stage": "score",
        }
    )
    log.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), str(log), str(job_dir), str(output)])

    assert validate_model_e2e.main() == 0
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["outcome"] == "SUCCESS_NO_RECOMMENDATIONS"
    assert summary["render_skipped"] is True
    assert "camera" not in summary["stages"]
    assert "render" not in summary["stages"]
    assert "SUCCESS_NO_RECOMMENDATIONS" in capsys.readouterr().out
