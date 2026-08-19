use std::path::Path;

use serde::Deserialize;
use serde_json::Value;

use crate::path_security;

#[derive(Debug, serde::Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SaveClipEditsInput {
    pub clip: u32,
    pub edit: ClipEditInput,
}

#[derive(Debug, serde::Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ClipEditInput {
    pub start: f64,
    pub end: f64,
    #[serde(default)]
    pub caption_preset: Option<String>,
    #[serde(default)]
    pub camera_mode: Option<String>,
    #[serde(default)]
    pub remove_dead_space: bool,
    #[serde(default)]
    pub disabled_cuts: Vec<u32>,
    #[serde(default)]
    pub overlays: Vec<OverlayInput>,
}

#[derive(Debug, serde::Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OverlayInput {
    pub id: String,
    pub query: String,
    #[serde(default = "default_source")]
    pub source: String,
    #[serde(default)]
    pub image_path: String,
    pub start: f64,
    pub end: f64,
    pub x: f64,
    pub y: f64,
    pub scale: f64,
    #[serde(default = "default_animation")]
    pub animation: String,
    #[serde(default)]
    pub phrase: String,
}

fn default_source() -> String {
    "pexels".to_string()
}

fn default_animation() -> String {
    "none".to_string()
}

fn finite(value: f64, label: &str) -> Result<(), String> {
    if value.is_finite() {
        Ok(())
    } else {
        Err(format!("{label} must be finite"))
    }
}

fn validate_local_asset(job_dir: &Path, overlay: &OverlayInput) -> Result<(), String> {
    if overlay.image_path.is_empty() {
        if overlay.source == "upload" {
            return Err(format!("overlay {} requires a local image", overlay.id));
        }
        return Ok(());
    }
    let raw = Path::new(&overlay.image_path);
    let candidate = if raw.is_absolute() {
        raw.to_path_buf()
    } else {
        job_dir.join(raw)
    };
    let resolved = path_security::resolve_existing_file(&job_dir.join("overlays"), &candidate)?;
    let extension = resolved
        .extension()
        .and_then(|value| value.to_str())
        .map(str::to_ascii_lowercase)
        .ok_or_else(|| format!("overlay {} has no supported image extension", overlay.id))?;
    if !matches!(extension.as_str(), "png" | "jpg" | "jpeg" | "webp") {
        return Err(format!(
            "overlay {} has an unsupported image type",
            overlay.id
        ));
    }
    Ok(())
}

pub fn validate(
    job_dir: &Path,
    input: &SaveClipEditsInput,
    score: &Value,
) -> Result<Value, String> {
    let clips = score["data"]["clips"]
        .as_array()
        .ok_or_else(|| "score checkpoint has no clip list".to_string())?;
    let clip = clips
        .get(input.clip as usize)
        .ok_or_else(|| "clip identity is not present in the score checkpoint".to_string())?;
    let source_start = clip["start"]
        .as_f64()
        .ok_or_else(|| "clip start is malformed".to_string())?;
    let source_end = clip["end"]
        .as_f64()
        .ok_or_else(|| "clip end is malformed".to_string())?;
    let edit = &input.edit;
    finite(edit.start, "edit start")?;
    finite(edit.end, "edit end")?;
    if edit.start < source_start || edit.end > source_end || edit.end <= edit.start {
        return Err("edit timeline must remain within the selected clip bounds".to_string());
    }
    if edit.disabled_cuts.len() > 256 {
        return Err("too many disabled cuts".to_string());
    }
    if let Some(preset) = &edit.caption_preset {
        if !matches!(preset.as_str(), "classic" | "bold" | "karaoke") {
            return Err("unsupported caption preset".to_string());
        }
    }
    if let Some(mode) = &edit.camera_mode {
        if !matches!(mode.as_str(), "cut" | "pan" | "locked") {
            return Err("unsupported camera mode".to_string());
        }
    }
    if edit.overlays.len() > 32 {
        return Err("overlay count exceeds the limit of 32".to_string());
    }
    let duration = edit.end - edit.start;
    for overlay in &edit.overlays {
        if overlay.id.is_empty()
            || overlay.id.len() > 128
            || !overlay.id.bytes().all(|b| b.is_ascii_graphic())
        {
            return Err("overlay id is invalid".to_string());
        }
        if overlay.query.len() > 500 || overlay.phrase.len() > 500 {
            return Err(format!("overlay {} text is too long", overlay.id));
        }
        if !matches!(overlay.source.as_str(), "pexels" | "gemini" | "upload") {
            return Err(format!("overlay {} source is invalid", overlay.id));
        }
        if !matches!(overlay.animation.as_str(), "none" | "pop" | "ping") {
            return Err(format!("overlay {} animation is invalid", overlay.id));
        }
        for (value, label) in [
            (overlay.start, "overlay start"),
            (overlay.end, "overlay end"),
            (overlay.x, "overlay x"),
            (overlay.y, "overlay y"),
            (overlay.scale, "overlay scale"),
        ] {
            finite(value, label)?;
        }
        if overlay.start < 0.0 || overlay.end <= overlay.start || overlay.end > duration {
            return Err(format!(
                "overlay {} timeline is outside the edited clip",
                overlay.id
            ));
        }
        if !(0.0..=1.0).contains(&overlay.x)
            || !(0.0..=1.0).contains(&overlay.y)
            || !(0.05..=0.9).contains(&overlay.scale)
        {
            return Err(format!(
                "overlay {} position or size is outside safe bounds",
                overlay.id
            ));
        }
        validate_local_asset(job_dir, overlay)?;
    }
    serde_json::to_value(serde_json::json!({input.clip.to_string(): {
        "start": edit.start,
        "end": edit.end,
        "caption_preset": edit.caption_preset,
        "camera_mode": edit.camera_mode,
        "remove_dead_space": edit.remove_dead_space,
        "disabled_cuts": edit.disabled_cuts,
        "overlays": edit.overlays,
    }}))
    .map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid() -> SaveClipEditsInput {
        serde_json::from_value(serde_json::json!({
            "clip": 0,
            "edit": {
                "start": 10.0, "end": 20.0,
                "caption_preset": "classic",
                "camera_mode": "cut",
                "remove_dead_space": false,
                "disabled_cuts": [], "overlays": []
            }
        }))
        .unwrap()
    }

    fn score() -> Value {
        serde_json::json!({"data": {"clips": [{"start": 10.0, "end": 20.0}]}})
    }

    #[test]
    fn accepts_bounded_edit() {
        assert!(validate(Path::new("/tmp/job"), &valid(), &score()).is_ok());
    }

    #[test]
    fn rejects_unknown_fields_during_deserialization() {
        assert!(
            serde_json::from_value::<SaveClipEditsInput>(serde_json::json!({
                "clip": 0, "edit": {"start": 10.0, "end": 20.0, "danger": true}
            }))
            .is_err()
        );
    }

    #[test]
    fn rejects_path_escape_and_invalid_timeline() {
        let mut payload = valid();
        payload.edit.end = 20.1;
        assert!(validate(Path::new("/tmp/job"), &payload, &score()).is_err());
    }
}
