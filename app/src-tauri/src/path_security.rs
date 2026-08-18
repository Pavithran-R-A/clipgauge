use std::fs;
use std::path::{Path, PathBuf};

const JOB_ID_PREFIX_LEN: usize = 15; // YYYYMMDD-HHMMSS

pub fn valid_job_id(id: &str) -> bool {
    if id.len() != JOB_ID_PREFIX_LEN + 1 + 6
        || id.contains('/')
        || id.contains('\\')
        || id.contains("..")
    {
        return false;
    }
    let bytes = id.as_bytes();
    bytes.len() >= 15
        && bytes[8] == b'-'
        && bytes[15] == b'-'
        && bytes[..8].iter().all(u8::is_ascii_digit)
        && bytes[9..15].iter().all(u8::is_ascii_digit)
        && bytes[16..].iter().all(|b| b.is_ascii_hexdigit())
}

pub fn jobs_root(home: &Path) -> PathBuf {
    home.join("jobs")
}

pub fn resolve_job_dir(home: &Path, job_id: &str) -> Result<PathBuf, String> {
    if !valid_job_id(job_id) {
        return Err("invalid job identifier".into());
    }
    let root = jobs_root(home);
    let candidate = root.join(job_id);
    let canonical_root =
        fs::canonicalize(&root).map_err(|e| format!("jobs root unavailable: {e}"))?;
    let canonical = fs::canonicalize(&candidate).map_err(|e| format!("job unavailable: {e}"))?;
    if !canonical.starts_with(&canonical_root) || canonical == canonical_root {
        return Err("job is outside the managed jobs root".into());
    }
    if !canonical.is_dir() {
        return Err("job path is not a directory".into());
    }
    Ok(canonical)
}

pub fn resolve_existing_file(root: &Path, candidate: &Path) -> Result<PathBuf, String> {
    let canonical_root =
        fs::canonicalize(root).map_err(|e| format!("managed root unavailable: {e}"))?;
    let canonical =
        fs::canonicalize(candidate).map_err(|e| format!("artifact unavailable: {e}"))?;
    if !canonical.starts_with(&canonical_root) {
        return Err("artifact is outside the managed root".into());
    }
    let metadata = fs::metadata(&canonical).map_err(|e| e.to_string())?;
    if !metadata.is_file() {
        return Err("artifact is not a regular file".into());
    }
    Ok(canonical)
}

#[cfg(test)]
mod tests {
    use super::{resolve_existing_file, resolve_job_dir, valid_job_id};
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_root() -> std::path::PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("clipgauge-stage1a-{suffix}"));
        fs::create_dir_all(&root).unwrap();
        root
    }

    #[test]
    fn validates_the_upstream_job_id_grammar() {
        assert!(valid_job_id("20260818-155237-c6b118"));
        assert!(!valid_job_id("../secret"));
        assert!(!valid_job_id("20260818-155237-zzzzzz"));
        assert!(!valid_job_id("/absolute"));
        assert!(!valid_job_id("20260818-155237-c6b118/nested"));
    }

    #[test]
    fn rejects_symlink_escape() {
        let temp = temp_root();
        let home = temp.join("home");
        let jobs = home.join("jobs");
        fs::create_dir_all(&jobs).unwrap();
        let outside = temp.join("outside");
        fs::create_dir_all(&outside).unwrap();
        #[cfg(unix)]
        std::os::unix::fs::symlink(&outside, jobs.join("20260818-155237-c6b118")).unwrap();
        #[cfg(unix)]
        assert!(resolve_job_dir(&home, "20260818-155237-c6b118").is_err());
    }

    #[test]
    fn missing_job_fails_closed() {
        let temp = temp_root();
        fs::create_dir_all(temp.join("home/jobs")).unwrap();
        assert!(resolve_job_dir(&temp.join("home"), "20260818-155237-c6b118").is_err());
    }

    #[test]
    fn resolves_unicode_regular_files_inside_root() {
        let temp = temp_root();
        let root = temp.join("clips");
        fs::create_dir_all(&root).unwrap();
        let file = root.join("clip café.mp4");
        fs::write(&file, b"x").unwrap();
        assert_eq!(
            resolve_existing_file(&root, &file).unwrap(),
            fs::canonicalize(file).unwrap()
        );
    }
}
