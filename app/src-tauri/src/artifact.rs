use std::fs;
use std::path::{Path, PathBuf};

use serde_json::{json, Map, Value};

use crate::path_security::{resolve_existing_file, resolve_job_dir};

fn read_stage(dir: &Path, name: &str) -> Result<Value, String> {
    let path = dir.join(format!("{name}.json"));
    if !path.exists() {
        return Ok(Value::Null);
    }
    let text =
        fs::read_to_string(&path).map_err(|_| format!("could not read {name} checkpoint"))?;
    let envelope: Value =
        serde_json::from_str(&text).map_err(|_| format!("malformed {name} checkpoint"))?;
    envelope
        .get("data")
        .cloned()
        .ok_or_else(|| format!("malformed {name} checkpoint"))
}

fn artifact_status(render_root: &Path, value: &mut Map<String, Value>) {
    let raw_path = value.get("path").and_then(Value::as_str).map(PathBuf::from);
    let Some(path) = raw_path else {
        value.insert("artifact_status".into(), json!("invalid"));
        value.insert("path".into(), Value::Null);
        return;
    };
    match resolve_existing_file(render_root, &path) {
        Ok(canonical) if canonical.extension().and_then(|e| e.to_str()) == Some("mp4") => {
            value.insert(
                "path".into(),
                json!(canonical.to_string_lossy().to_string()),
            );
            value.insert("artifact_status".into(), json!("available"));
        }
        Ok(_) => {
            value.insert("path".into(), Value::Null);
            value.insert("artifact_status".into(), json!("invalid"));
        }
        Err(message) if message.contains("outside") => {
            value.insert("path".into(), Value::Null);
            value.insert("artifact_status".into(), json!("outside_managed_root"));
        }
        Err(_) => {
            value.insert("path".into(), Value::Null);
            value.insert("artifact_status".into(), json!("missing"));
        }
    }
}

pub fn job_results(home: &Path, job_id: &str) -> Result<Value, String> {
    let dir = resolve_job_dir(home, job_id)?;
    let ingest = read_stage(&dir, "ingest")?;
    let score = read_stage(&dir, "score")?;
    let camera = read_stage(&dir, "camera")?;
    let mut render = read_stage(&dir, "render")?;
    let events = read_stage(&dir, "events")?;
    let candidates = read_stage(&dir, "candidates")?;

    if let Some(outputs) = render.get_mut("outputs").and_then(Value::as_array_mut) {
        let render_root = dir.join("clips");
        for output in outputs {
            if let Some(object) = output.as_object_mut() {
                artifact_status(&render_root, object);
            }
        }
    } else if !render.is_null() {
        return Err("malformed render outputs".into());
    }

    Ok(json!({
        "job_id": job_id,
        "ingest": ingest,
        "score": score,
        "camera": camera,
        "render": render,
        "events": events,
        "candidates": candidates,
    }))
}

fn safe_stem(title: Option<&String>) -> String {
    let raw = title.cloned().unwrap_or_else(|| "clipgauge".into());
    let safe = raw
        .chars()
        .map(|c| {
            if c.is_alphanumeric() || c == ' ' || c == '-' {
                c
            } else {
                '_'
            }
        })
        .collect::<String>()
        .trim()
        .replace(' ', "-")
        .chars()
        .take(60)
        .collect::<String>();
    if safe.is_empty() {
        "clipgauge".into()
    } else {
        safe
    }
}

pub fn export_clip(
    home: &Path,
    downloads: &Path,
    job_id: &str,
    clip: u32,
    title: Option<String>,
) -> Result<String, String> {
    let dir = resolve_job_dir(home, job_id)?;
    let render = read_stage(&dir, "render")?;
    let outputs = render
        .get("outputs")
        .and_then(Value::as_array)
        .ok_or_else(|| "malformed render outputs".to_string())?;
    let output = outputs
        .iter()
        .find(|entry| entry.get("clip").and_then(Value::as_u64) == Some(clip as u64))
        .ok_or_else(|| "clip is not part of this job".to_string())?;
    let source = output
        .get("path")
        .and_then(Value::as_str)
        .ok_or_else(|| "clip has no render artifact".to_string())?;
    let source = resolve_existing_file(&dir.join("clips"), Path::new(source))?;
    if source.extension().and_then(|e| e.to_str()) != Some("mp4") {
        return Err("clip artifact is not an MP4".into());
    }
    fs::create_dir_all(downloads).map_err(|e| e.to_string())?;
    let stem = safe_stem(title.as_ref());
    let mut dest = downloads.join(format!("{stem}.mp4"));
    let mut n = 1;
    while dest.exists() {
        dest = downloads.join(format!("{stem}-{n}.mp4"));
        n += 1;
    }
    fs::copy(source, &dest).map_err(|e| e.to_string())?;
    Ok(dest.to_string_lossy().to_string())
}

#[cfg(test)]
mod tests {
    use super::{export_clip, job_results};
    use serde_json::json;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn fixture() -> std::path::PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let home = std::env::temp_dir().join(format!("clipgauge-artifact-{suffix}"));
        let job = home.join("jobs/20260818-155237-c6b118");
        fs::create_dir_all(job.join("clips")).unwrap();
        fs::write(job.join("clips/clip_00.mp4"), b"video").unwrap();
        let checkpoint = json!({
            "data": {
                "outputs": [{
                    "clip": 0,
                    "path": job.join("clips/clip_00.mp4").to_string_lossy(),
                }]
            }
        });
        fs::write(
            job.join("render.json"),
            serde_json::to_vec(&checkpoint).unwrap(),
        )
        .unwrap();
        home
    }

    #[test]
    fn reports_available_render_artifact() {
        let home = fixture();
        let result = job_results(&home, "20260818-155237-c6b118").unwrap();
        assert_eq!(
            result["render"]["outputs"][0]["artifact_status"],
            "available"
        );
    }

    #[test]
    fn export_rejects_a_clip_not_in_render_checkpoint() {
        let home = fixture();
        let downloads = home.join("Downloads");
        assert!(export_clip(&home, &downloads, "20260818-155237-c6b118", 9, None).is_err());
    }

    #[test]
    fn export_rejects_an_arbitrary_readable_file_outside_job_clips() {
        let home = fixture();
        let job = home.join("jobs/20260818-155237-c6b118");
        let outside = home.join("outside-readable.mp4");
        fs::write(&outside, b"not the rendered clip").unwrap();
        fs::write(
            job.join("render.json"),
            format!(
                r#"{{"data":{{"outputs":[{{"clip":0,"path":"{}"}}]}}}}"#,
                outside.to_string_lossy()
            ),
        )
        .unwrap();
        assert!(export_clip(
            &home,
            &home.join("Downloads"),
            "20260818-155237-c6b118",
            0,
            None,
        )
        .is_err());
    }

    #[test]
    fn outside_render_artifact_is_explicit() {
        let home = fixture();
        let job = home.join("jobs/20260818-155237-c6b118");
        let outside = home.join("outside-readable.mp4");
        fs::write(&outside, b"outside").unwrap();
        fs::write(
            job.join("render.json"),
            format!(
                r#"{{"data":{{"outputs":[{{"clip":0,"path":"{}"}}]}}}}"#,
                outside.to_string_lossy()
            ),
        )
        .unwrap();
        let result = job_results(&home, "20260818-155237-c6b118").unwrap();
        assert_eq!(
            result["render"]["outputs"][0]["artifact_status"],
            "outside_managed_root"
        );
        assert!(result["render"]["outputs"][0]["path"].is_null());
    }

    #[test]
    fn missing_render_artifact_is_explicit() {
        let home = fixture();
        fs::remove_file(home.join("jobs/20260818-155237-c6b118/clips/clip_00.mp4")).unwrap();
        let result = job_results(&home, "20260818-155237-c6b118").unwrap();
        assert_eq!(result["render"]["outputs"][0]["artifact_status"], "missing");
    }
}
