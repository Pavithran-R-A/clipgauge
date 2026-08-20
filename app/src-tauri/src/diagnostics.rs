use std::collections::VecDeque;
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::Path;

use uuid::Uuid;

const MAX_TAIL_BYTES: usize = 64 * 1024;

#[derive(Debug)]
pub struct BoundedTail {
    max_bytes: usize,
    bytes: VecDeque<u8>,
}

impl Default for BoundedTail {
    fn default() -> Self {
        Self::new(MAX_TAIL_BYTES)
    }
}

impl BoundedTail {
    pub fn new(max_bytes: usize) -> Self {
        Self {
            max_bytes,
            bytes: VecDeque::with_capacity(max_bytes),
        }
    }

    pub fn push(&mut self, chunk: &[u8]) {
        for byte in chunk {
            if self.bytes.len() == self.max_bytes {
                self.bytes.pop_front();
            }
            self.bytes.push_back(*byte);
        }
    }

    pub fn text(&self) -> String {
        let bytes: Vec<u8> = self.bytes.iter().copied().collect();
        String::from_utf8_lossy(&bytes).to_string()
    }
}

fn secret_key(name: &str) -> bool {
    matches!(
        name.to_ascii_lowercase().as_str(),
        "key"
            | "api_key"
            | "apikey"
            | "gemini_key"
            | "gemini_api_key"
            | "openrouter_api_key"
            | "groq_api_key"
            | "cloudflare_api_token"
            | "hf_token"
            | "cerebras_api_key"
            | "provider_secret"
            | "x-api-key"
            | "pexels_key"
            | "pexels_api_key"
            | "access_token"
            | "meta_access_token"
            | "instagram_access_token"
            | "token"
            | "authorization"
            | "app_secret"
            | "client_secret"
            | "secret"
    )
}

fn redact_query_token(mut token: String) -> String {
    for name in [
        "key",
        "api_key",
        "apikey",
        "access_token",
        "token",
        "authorization",
        "app_secret",
    ] {
        for marker in [format!("?{name}="), format!("&{name}=")] {
            let mut search_from = 0;
            while let Some(found) = token[search_from..].find(&marker) {
                let start = search_from + found + marker.len();
                let end = token[start..]
                    .find('&')
                    .map(|offset| start + offset)
                    .unwrap_or(token.len());
                token.replace_range(start..end, "[REDACTED]");
                search_from = start + "[REDACTED]".len();
            }
        }
    }
    token
}

pub fn redact_with_secrets(input: &str, secrets: &[&str]) -> String {
    let mut result = input.to_string();
    for secret in secrets.iter().filter(|value| !value.is_empty()) {
        result = result.replace(secret, "[REDACTED]");
    }
    redact(&result)
}

pub fn redact(input: &str) -> String {
    let mut result = Vec::new();
    let mut redact_next = false;
    for raw in input.split_whitespace() {
        let mut token = redact_query_token(raw.to_string());
        let lower = token.to_ascii_lowercase();
        if redact_next && lower == "bearer" {
            result.push(token);
            continue;
        } else if redact_next {
            token = "[REDACTED]".to_string();
            redact_next = false;
        } else if lower == "bearer" || lower == "authorization:" {
            result.push(token);
            redact_next = true;
            continue;
        } else if ["AIza", "sk-or-v1-", "gsk_", "hf_", "cf_", "csk_"]
            .iter()
            .any(|prefix| token.starts_with(prefix))
        {
            token = "[REDACTED]".to_string();
        } else if let Some((name, _value)) = token.split_once('=') {
            if secret_key(name.trim_matches(|c: char| !c.is_ascii_alphanumeric() && c != '_')) {
                token = format!(
                    "{}=[REDACTED]",
                    &token[..token.find('=').unwrap_or(token.len())]
                );
            }
        } else if let Some((name, _value)) = token.split_once(':') {
            if secret_key(name.trim_matches(|c: char| !c.is_ascii_alphanumeric() && c != '_')) {
                token = format!(
                    "{}: [REDACTED]",
                    &token[..token.find(':').unwrap_or(token.len())]
                );
            }
        }
        result.push(token);
    }
    result.join(" ")
}

pub fn diagnostic_id() -> String {
    format!("diag-{}", Uuid::new_v4().simple())
}

pub fn write_log(directory: &Path, id: &str, text: &str) -> io::Result<bool> {
    fs::create_dir_all(directory)?;
    let path = directory.join(format!("{id}.log"));
    let mut file = match OpenOptions::new().write(true).create_new(true).open(&path) {
        Ok(file) => file,
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => return Ok(false),
        Err(error) => return Err(error),
    };
    file.write_all(redact(text).as_bytes())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600))?;
    }
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::{diagnostic_id, redact, redact_with_secrets, write_log, BoundedTail};
    use std::fs;

    #[test]
    fn tail_is_bounded_and_keeps_latest_bytes() {
        let mut tail = BoundedTail::new(4);
        tail.push(b"1234");
        tail.push(b"56");
        assert_eq!(tail.text(), "3456");
    }

    #[test]
    fn redaction_preserves_context_but_removes_secrets() {
        let text = "tool=yt-dlp status=401 key=AIzaTestSecret pexels_api_key=pexels-secret Authorization: Bearer meta-token https://x.test/?access_token=ig-secret";
        let clean = redact(text);
        assert!(clean.contains("tool=yt-dlp"));
        assert!(clean.contains("status=401"));
        assert!(!clean.contains("AIzaTestSecret"));
        assert!(!clean.contains("pexels-secret"));
        assert!(!clean.contains("meta-token"));
        assert!(!clean.contains("ig-secret"));
    }

    #[test]
    fn custom_provider_secret_values_are_redacted_even_with_custom_header_names() {
        let clean = redact_with_secrets("x-custom-secret=never-show-this", &["never-show-this"]);
        assert!(!clean.contains("never-show-this"));
        assert!(clean.contains("[REDACTED]"));
    }

    #[test]
    fn diagnostic_ids_are_unique_and_have_a_safe_format() {
        let ids: Vec<String> = (0..64).map(|_| diagnostic_id()).collect();
        for id in &ids {
            let parts: Vec<&str> = id.split('-').collect();
            assert_eq!(parts.len(), 2);
            assert_eq!(parts[0], "diag");
            assert_eq!(parts[1].len(), 32);
            assert!(parts[1].chars().all(|c| c.is_ascii_hexdigit()));
        }
        let unique: std::collections::HashSet<&str> = ids.iter().map(String::as_str).collect();
        assert_eq!(unique.len(), ids.len());
    }

    #[test]
    fn diagnostic_log_creation_does_not_overwrite_existing_file() {
        let directory =
            std::env::temp_dir().join(format!("clipgauge-stage1a1-{}", diagnostic_id()));
        fs::create_dir_all(&directory).unwrap();
        let id = "diag-1-2-3";
        assert!(write_log(&directory, id, "first=ok").unwrap());
        assert!(!write_log(&directory, id, "second=must-not-overwrite").unwrap());
        assert_eq!(
            fs::read_to_string(directory.join(format!("{id}.log"))).unwrap(),
            "first=ok"
        );
        let _ = fs::remove_dir_all(directory);
    }
}
