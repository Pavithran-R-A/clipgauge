use std::collections::VecDeque;

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
        } else if token.starts_with("AIza") {
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
    use std::time::{SystemTime, UNIX_EPOCH};
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or_default();
    format!("diag-{}", millis)
}

#[cfg(test)]
mod tests {
    use super::{redact, BoundedTail};

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
}
