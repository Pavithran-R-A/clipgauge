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
    if name == "collections" && envelope.get("collections").is_some() {
        return Ok(envelope);
    }
    envelope
        .get("data")
        .cloned()
        .ok_or_else(|| format!("malformed {name} checkpoint"))
}

fn read_creator_overrides(dir: &Path) -> Result<Value, String> {
    let path = dir.join("creator-overrides.json");
    if !path.exists() {
        return Ok(Value::Null);
    }
    let text = fs::read_to_string(path).map_err(|_| "could not read creator overrides")?;
    let value: Value = serde_json::from_str(&text).map_err(|_| "malformed creator overrides")?;
    if value.get("schema_version").and_then(Value::as_u64) != Some(1)
        || !value.get("clips").is_some_and(Value::is_object)
    {
        return Err("malformed creator overrides".to_string());
    }
    Ok(value)
}

fn apply_creator_title_overrides(stage: &mut Value, overrides: &Value) {
    let Some(entries) = overrides.get("clips").and_then(Value::as_object) else {
        return;
    };
    let Some(clips) = stage.get_mut("clips").and_then(Value::as_array_mut) else {
        return;
    };
    for clip in clips {
        let Some(object) = clip.as_object_mut() else {
            continue;
        };
        let Some(clip_id) = object.get("clip_id").and_then(Value::as_str) else {
            continue;
        };
        let Some(title) = entries
            .get(clip_id)
            .and_then(Value::as_object)
            .and_then(|entry| entry.get("title"))
            .and_then(Value::as_str)
        else {
            continue;
        };
        object.insert("title".to_string(), Value::String(title.to_string()));
        object.insert(
            "title_source".to_string(),
            Value::String("user".to_string()),
        );
    }
}

pub fn render_artifact(home: &Path, job_id: &str, clip: u32) -> Result<PathBuf, String> {
    let dir = resolve_job_dir(home, job_id)?;
    let render = read_stage(&dir, "render")?;
    let output = render
        .get("outputs")
        .and_then(Value::as_array)
        .and_then(|outputs| {
            outputs
                .iter()
                .find(|entry| entry.get("clip").and_then(Value::as_u64) == Some(clip as u64))
        })
        .ok_or_else(|| "clip is not part of this job".to_string())?;
    let raw = output
        .get("path")
        .and_then(Value::as_str)
        .ok_or_else(|| "clip has no render artifact".to_string())?;
    let raw_path = Path::new(raw);
    let candidate = if raw_path.is_absolute() {
        raw_path.to_path_buf()
    } else {
        dir.join(raw_path)
    };
    let resolved = resolve_existing_file(&dir.join("clips"), &candidate)?;
    if resolved.extension().and_then(|ext| ext.to_str()) != Some("mp4") {
        return Err("clip artifact is not an MP4".into());
    }
    Ok(resolved)
}

pub fn source_media_artifact(home: &Path, job_id: &str) -> Result<PathBuf, String> {
    let dir = resolve_job_dir(home, job_id)?;
    let ingest = read_stage(&dir, "ingest")?;
    let raw = ingest
        .get("media_path")
        .or_else(|| ingest.get("source_path"))
        .and_then(Value::as_str)
        .ok_or_else(|| "source media is not declared".to_string())?;
    let raw_path = Path::new(raw);
    let candidate = if raw_path.is_absolute() {
        raw_path.to_path_buf()
    } else {
        dir.join(raw_path)
    };
    let resolved = resolve_existing_file(&dir, &candidate)?;
    match resolved.extension().and_then(|ext| ext.to_str()) {
        Some("mp4") | Some("webm") | Some("mov") => Ok(resolved),
        _ => Err("source media is not a supported video file".into()),
    }
}

fn artifact_status(job_dir: &Path, value: &mut Map<String, Value>) {
    let raw_path = value.get("path").and_then(Value::as_str).map(PathBuf::from);
    let Some(path) = raw_path else {
        value.insert("artifact_status".into(), json!("invalid"));
        value.insert("path".into(), Value::Null);
        return;
    };
    let clips_root = job_dir.join("clips");
    let candidate = if path.is_absolute() {
        path
    } else {
        job_dir.join(path)
    };
    match resolve_existing_file(&clips_root, &candidate) {
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
    let creator_overrides = read_creator_overrides(&dir)?;
    let ingest = read_stage(&dir, "ingest")?;
    let score = read_stage(&dir, "score")?;
    let enrich = read_stage(&dir, "enrich")?;
    let collections = read_stage(&dir, "collections")?;
    let camera = read_stage(&dir, "camera")?;
    let mut render = read_stage(&dir, "render")?;
    let events = read_stage(&dir, "events")?;
    let candidates = read_stage(&dir, "candidates")?;
    let outcome = score.get("outcome").cloned().unwrap_or_else(|| {
        if render
            .get("outputs")
            .and_then(Value::as_array)
            .is_some_and(|outputs| !outputs.is_empty())
        {
            json!("SUCCESS_WITH_CLIPS")
        } else {
            json!("FAILED")
        }
    });

    let mut score = score;
    if let (Some(score_clips), Some(enriched_clips)) = (
        score.get_mut("clips").and_then(Value::as_array_mut),
        enrich.get("clips").and_then(Value::as_array),
    ) {
        for (index, score_clip) in score_clips.iter_mut().enumerate() {
            let Some(enriched) = enriched_clips.get(index).and_then(Value::as_object) else {
                continue;
            };
            let Some(target) = score_clip.as_object_mut() else {
                continue;
            };
            for key in [
                "clip_id",
                "title",
                "short_description",
                "title_source",
                "description_source",
            ] {
                if let Some(value) = enriched.get(key) {
                    target.insert(key.to_string(), value.clone());
                }
            }
        }
    }
    apply_creator_title_overrides(&mut score, &creator_overrides);
    let mut enrich = enrich;
    apply_creator_title_overrides(&mut enrich, &creator_overrides);

    if let Some(outputs) = render.get_mut("outputs").and_then(Value::as_array_mut) {
        for output in outputs {
            if let Some(object) = output.as_object_mut() {
                artifact_status(&dir, object);
            }
        }
    } else if !render.is_null() {
        return Err("malformed render outputs".into());
    }

    Ok(json!({
        "job_id": job_id,
        "outcome": outcome,
        "ingest": ingest,
        "score": score,
        "enrich": enrich,
        "collections": collections,
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

fn validate_explicit_destination(destination: &Path) -> Result<(), String> {
    if !destination.is_absolute() {
        return Err("export destination must be an absolute path".into());
    }
    let is_mp4 = destination
        .extension()
        .and_then(|extension| extension.to_str())
        .is_some_and(|extension| extension.eq_ignore_ascii_case("mp4"));
    if !is_mp4 {
        return Err("export destination must end in .mp4".into());
    }
    let parent = destination
        .parent()
        .ok_or_else(|| "export destination has no parent directory".to_string())?;
    let parent_metadata = fs::metadata(parent)
        .map_err(|_| "export destination parent directory does not exist".to_string())?;
    if !parent_metadata.is_dir() {
        return Err("export destination parent is not a directory".into());
    }
    match fs::symlink_metadata(destination) {
        Ok(metadata) => {
            if metadata.file_type().is_symlink() {
                return Err("export destination may not be a symlink".into());
            }
            if !metadata.is_file() {
                return Err("export destination is not a regular file".into());
            }
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(_) => return Err("could not inspect existing export destination".into()),
    }
    Ok(())
}

pub fn export_clip_to(
    home: &Path,
    job_id: &str,
    clip: u32,
    destination: &Path,
) -> Result<String, String> {
    let source = render_artifact(home, job_id, clip)?;
    validate_explicit_destination(destination)?;
    if fs::symlink_metadata(destination).is_ok() {
        let existing = fs::canonicalize(destination)
            .map_err(|_| "could not resolve existing export destination".to_string())?;
        if existing == source {
            return Err("export destination cannot overwrite the managed source artifact".into());
        }
    }
    fs::copy(&source, destination).map_err(|e| e.to_string())?;
    Ok(destination.to_string_lossy().to_string())
}

pub fn export_clip(
    home: &Path,
    downloads: &Path,
    job_id: &str,
    clip: u32,
    title: Option<String>,
) -> Result<String, String> {
    let source = render_artifact(home, job_id, clip)?;
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
    use super::{export_clip, export_clip_to, job_results, render_artifact, source_media_artifact};
    use serde_json::json;
    use std::fs;
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT_FIXTURE: AtomicU64 = AtomicU64::new(0);

    fn write_render_checkpoint(job: &std::path::Path, path: &std::path::Path) {
        let checkpoint = json!({
            "data": {
                "outputs": [{
                    "clip": 0,
                    "path": path.to_string_lossy().to_string(),
                }]
            }
        });
        fs::write(
            job.join("render.json"),
            serde_json::to_vec(&checkpoint).unwrap(),
        )
        .unwrap();
    }

    fn fixture() -> std::path::PathBuf {
        let suffix = NEXT_FIXTURE.fetch_add(1, Ordering::Relaxed);
        let home = std::env::temp_dir().join(format!(
            "clipgauge-artifact-{}-{suffix}",
            std::process::id()
        ));
        let job = home.join("jobs/20260818-155237-c6b118");
        fs::create_dir_all(job.join("clips")).unwrap();
        fs::write(job.join("clips/clip_00.mp4"), b"video").unwrap();
        write_render_checkpoint(&job, &job.join("clips/clip_00.mp4"));
        home
    }

    fn relative_fixture() -> std::path::PathBuf {
        let home = fixture();
        let job = home.join("jobs/20260818-155237-c6b118");
        write_render_checkpoint_path(&job, "clips/clip_00.mp4");
        home
    }

    fn source_fixture() -> std::path::PathBuf {
        let home = fixture();
        let job = home.join("jobs/20260818-155237-c6b118");
        fs::write(job.join("media.mp4"), b"source").unwrap();
        fs::write(
            job.join("ingest.json"),
            serde_json::to_vec(&json!({"data": {"media_path": "media.mp4"}})).unwrap(),
        )
        .unwrap();
        home
    }

    #[test]
    fn resolves_declared_source_media_inside_job() {
        let home = source_fixture();
        let source = source_media_artifact(&home, "20260818-155237-c6b118").unwrap();
        assert_eq!(fs::read(source).unwrap(), b"source");
    }

    #[test]
    fn rejects_source_media_outside_job() {
        let home = source_fixture();
        let job = home.join("jobs/20260818-155237-c6b118");
        let outside = home.join("outside-source.mp4");
        fs::write(&outside, b"outside").unwrap();
        fs::write(
            job.join("ingest.json"),
            serde_json::to_vec(&json!({"data": {"media_path": "../outside-source.mp4"}})).unwrap(),
        )
        .unwrap();
        assert!(source_media_artifact(&home, "20260818-155237-c6b118").is_err());
    }

    fn write_render_checkpoint_path(job: &std::path::Path, path: &str) {
        let checkpoint = json!({
            "data": {
                "outputs": [{"clip": 0, "path": path}]
            }
        });
        fs::write(
            job.join("render.json"),
            serde_json::to_vec(&checkpoint).unwrap(),
        )
        .unwrap();
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
    fn resolves_render_artifact_by_persisted_clip_number() {
        let home = fixture();
        let job = home.join("jobs/20260818-155237-c6b118");
        fs::write(job.join("clips/clip_03.mp4"), b"three").unwrap();
        fs::write(job.join("clips/clip_07.mp4"), b"seven").unwrap();
        let checkpoint = json!({
            "data": {
                "outputs": [
                    {"clip": 7, "path": "clips/clip_07.mp4"},
                    {"clip": 3, "path": "clips/clip_03.mp4"}
                ]
            }
        });
        fs::write(
            job.join("render.json"),
            serde_json::to_vec(&checkpoint).unwrap(),
        )
        .unwrap();

        let artifact = render_artifact(&home, "20260818-155237-c6b118", 7).unwrap();

        assert_eq!(fs::read(artifact).unwrap(), b"seven");
    }

    #[test]
    fn preserves_python_score_adjustment_reasons_for_review() {
        let home = fixture();
        let job = home.join("jobs/20260818-155237-c6b118");
        let score = json!({
            "data": {
                "outcome": "SUCCESS_WITH_CLIPS",
                "clips": [{
                    "adjustments": [{
                        "rule": "bait_verification",
                        "factor": 1.0,
                        "reason": "Bait phrases were checked against the candidate transcript."
                    }]
                }]
            }
        });
        fs::write(job.join("score.json"), serde_json::to_vec(&score).unwrap()).unwrap();

        let result = job_results(&home, "20260818-155237-c6b118").unwrap();

        assert_eq!(
            result["score"]["clips"][0]["adjustments"][0]["reason"],
            "Bait phrases were checked against the candidate transcript."
        );
        assert_eq!(result["outcome"], "SUCCESS_WITH_CLIPS");
    }

    #[test]
    fn applies_creator_title_override_without_mutating_score_checkpoint() {
        let home = fixture();
        let job = home.join("jobs/20260818-155237-c6b118");
        let score = json!({
            "data": {
                "outcome": "SUCCESS_WITH_CLIPS",
                "clips": [{"clip_id": "clip-a", "title": "Generated", "title_source": "model"}]
            }
        });
        let score_bytes = serde_json::to_vec(&score).unwrap();
        fs::write(job.join("score.json"), &score_bytes).unwrap();
        fs::write(
            job.join("creator-overrides.json"),
            serde_json::to_vec(&json!({
                "schema_version": 1,
                "job_id": "20260818-155237-c6b118",
                "clips": {"clip-a": {"title": "Creator title", "updated_at": "2026-09-20T00:00:00Z"}}
            }))
            .unwrap(),
        )
        .unwrap();

        let result = job_results(&home, "20260818-155237-c6b118").unwrap();

        assert_eq!(result["score"]["clips"][0]["title"], "Creator title");
        assert_eq!(result["score"]["clips"][0]["title_source"], "user");
        assert_eq!(fs::read(job.join("score.json")).unwrap(), score_bytes);
    }

    #[test]
    fn reads_python_creator_collection_state_after_mutation() {
        let home = fixture();
        let job = home.join("jobs/20260818-155237-c6b118");
        fs::write(
            job.join("score.json"),
            serde_json::to_vec(&json!({
                "data": {
                    "outcome": "SUCCESS_WITH_CLIPS",
                    "clips": [
                        {"clip_id": "clip-a", "title": "A"},
                        {"clip_id": "clip-b", "title": "B"}
                    ]
                }
            }))
            .unwrap(),
        )
        .unwrap();
        fs::write(
            job.join("collections.json"),
            serde_json::to_vec(&json!({
                "schema_version": 1,
                "job_id": "20260818-155237-c6b118",
                "collections": [{
                    "id": "collection-a",
                    "title": "Creator series",
                    "clip_ids": ["clip-a", "clip-b"],
                    "source": "manual",
                    "user_edited": true,
                    "render_path": null
                }]
            }))
            .unwrap(),
        )
        .unwrap();

        let result = job_results(&home, "20260818-155237-c6b118").unwrap();

        assert_eq!(
            result["collections"]["collections"][0]["title"],
            "Creator series"
        );
    }

    #[test]
    fn reports_available_relative_render_artifact() {
        let home = relative_fixture();
        let result = job_results(&home, "20260818-155237-c6b118").unwrap();
        assert_eq!(
            result["render"]["outputs"][0]["artifact_status"],
            "available"
        );
    }

    #[test]
    fn exports_a_relative_render_artifact() {
        let home = relative_fixture();
        let downloads = home.join("Downloads");
        let exported = export_clip(
            &home,
            &downloads,
            "20260818-155237-c6b118",
            0,
            Some("Sample interview".into()),
        )
        .unwrap();
        assert_eq!(fs::read(exported).unwrap(), b"video");
    }

    #[test]
    fn exports_to_an_explicit_absolute_destination() {
        let home = relative_fixture();
        let exports = home.join("chosen");
        fs::create_dir_all(&exports).unwrap();
        let destination = exports.join("picked-by-user.mp4");
        let exported = export_clip_to(&home, "20260818-155237-c6b118", 0, &destination).unwrap();
        assert_eq!(exported, destination.to_string_lossy());
        assert_eq!(fs::read(destination).unwrap(), b"video");
    }

    #[test]
    fn explicit_export_rejects_relative_and_non_mp4_destinations() {
        let home = relative_fixture();
        assert!(export_clip_to(
            &home,
            "20260818-155237-c6b118",
            0,
            std::path::Path::new("relative.mp4"),
        )
        .is_err());
        let exports = home.join("chosen");
        fs::create_dir_all(&exports).unwrap();
        assert!(export_clip_to(
            &home,
            "20260818-155237-c6b118",
            0,
            &exports.join("wrong.txt"),
        )
        .is_err());
    }

    #[cfg(unix)]
    #[test]
    fn explicit_export_rejects_dangling_destination_symlinks() {
        use std::os::unix::fs::symlink;

        let home = fixture();
        let exports = home.join("chosen");
        fs::create_dir_all(&exports).unwrap();
        let destination = exports.join("picked.mp4");
        symlink(exports.join("missing.mp4"), &destination).unwrap();

        let error = export_clip_to(&home, "20260818-155237-c6b118", 0, &destination).unwrap_err();
        assert!(error.contains("may not be a symlink"));
    }

    #[test]
    fn rejects_a_job_root_mp4_as_a_render_artifact() {
        let home = fixture();
        let job = home.join("jobs/20260818-155237-c6b118");
        let misplaced = job.join("media.mp4");
        fs::write(&misplaced, b"not a clip").unwrap();
        write_render_checkpoint(&job, &misplaced);
        let result = job_results(&home, "20260818-155237-c6b118").unwrap();
        assert_eq!(
            result["render"]["outputs"][0]["artifact_status"],
            "outside_managed_root"
        );
        assert!(result["render"]["outputs"][0]["path"].is_null());
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
        write_render_checkpoint(&job, &outside);
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
        write_render_checkpoint(&job, &outside);
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
