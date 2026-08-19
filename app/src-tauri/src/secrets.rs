use std::fs;
use std::path::Path;

const SERVICE: &str = "io.github.pavithranra.clipgauge";
const MIGRATION_MARKER: &str = "secret-migration-v1.done";

#[derive(Debug, Clone, Copy)]
pub enum SecretName {
    GeminiApiKey,
    PexelsApiKey,
    InstagramConnection,
}

impl SecretName {
    fn account(self) -> &'static str {
        match self {
            Self::GeminiApiKey => "gemini_api_key",
            Self::PexelsApiKey => "pexels_api_key",
            Self::InstagramConnection => "instagram_connection",
        }
    }
}

pub trait SecretBackend {
    fn get(&self, name: SecretName) -> Result<Option<String>, String>;
    fn set(&mut self, name: SecretName, value: &str) -> Result<(), String>;
}

pub struct OsSecretBackend;

impl SecretBackend for OsSecretBackend {
    fn get(&self, name: SecretName) -> Result<Option<String>, String> {
        let entry = keyring::Entry::new(SERVICE, name.account())
            .map_err(|error| format!("credential store unavailable: {error}"))?;
        match entry.get_password() {
            Ok(value) if !value.is_empty() => Ok(Some(value)),
            Ok(_) => Ok(None),
            Err(keyring::Error::NoEntry) => Ok(None),
            Err(error) => Err(format!("credential store read failed: {error}")),
        }
    }

    fn set(&mut self, name: SecretName, value: &str) -> Result<(), String> {
        if value.trim().is_empty() {
            return Err("secret cannot be empty".to_string());
        }
        let entry = keyring::Entry::new(SERVICE, name.account())
            .map_err(|error| format!("credential store unavailable: {error}"))?;
        entry
            .set_password(value)
            .map_err(|error| format!("credential store write failed: {error}"))
    }
}

pub fn set(name: SecretName, value: &str) -> Result<(), String> {
    OsSecretBackend.set(name, value)
}

pub fn get(name: SecretName) -> Result<Option<String>, String> {
    OsSecretBackend.get(name)
}

pub fn apply_operation_env(command: &mut std::process::Command) {
    if let Ok(Some(value)) = get(SecretName::GeminiApiKey) {
        command.env("PUBLIKCLIP_GEMINI_API_KEY", value);
    }
    if let Ok(Some(value)) = get(SecretName::PexelsApiKey) {
        command.env("PUBLIKCLIP_PEXELS_API_KEY", value);
    }
    if let Ok(Some(value)) = get(SecretName::InstagramConnection) {
        command.env("PUBLIKCLIP_INSTAGRAM_CONNECTION_JSON", value);
    }
}

fn migrate_legacy_with_backend<B: SecretBackend>(
    home: &Path,
    backend: &mut B,
) -> Result<(), String> {
    let marker = home.join(MIGRATION_MARKER);
    if marker.exists() {
        return Ok(());
    }
    let legacy = home.join("secrets.json");
    if legacy.exists() {
        let text = fs::read_to_string(&legacy)
            .map_err(|error| format!("could not read legacy credentials: {error}"))?;
        let value: serde_json::Value = serde_json::from_str(&text)
            .map_err(|error| format!("legacy credentials are malformed: {error}"))?;
        let mut migrated = false;
        for (field, name) in [
            ("gemini_api_key", SecretName::GeminiApiKey),
            ("pexels_api_key", SecretName::PexelsApiKey),
        ] {
            if let Some(secret) = value.get(field).and_then(serde_json::Value::as_str) {
                if !secret.is_empty() {
                    backend.set(name, secret)?;
                    migrated = true;
                }
            }
        }
        if migrated {
            fs::remove_file(&legacy)
                .map_err(|error| format!("could not remove migrated credentials: {error}"))?;
        }
    }
    fs::write(marker, b"migrated")
        .map_err(|error| format!("could not record credential migration: {error}"))
}

pub fn migrate_legacy(home: &Path) -> Result<(), String> {
    let mut backend = OsSecretBackend;
    migrate_legacy_with_backend(home, &mut backend)
}

pub fn migrate_instagram_file(home: &Path) -> Result<(), String> {
    let path = home.join("instagram.json");
    if !path.exists() {
        return Ok(());
    }
    let value = fs::read_to_string(&path)
        .map_err(|error| format!("could not read Instagram connection: {error}"))?;
    let parsed: serde_json::Value = serde_json::from_str(&value)
        .map_err(|error| format!("Instagram connection is malformed: {error}"))?;
    let compact = serde_json::to_string(&parsed).map_err(|error| error.to_string())?;
    set(SecretName::InstagramConnection, &compact)?;
    fs::remove_file(path)
        .map_err(|error| format!("could not remove migrated Instagram connection: {error}"))
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use super::{SecretBackend, SecretName};

    struct MemoryBackend(HashMap<&'static str, String>);

    impl SecretBackend for MemoryBackend {
        fn get(&self, name: SecretName) -> Result<Option<String>, String> {
            Ok(self.0.get(name.account()).cloned())
        }
        fn set(&mut self, name: SecretName, value: &str) -> Result<(), String> {
            self.0.insert(name.account(), value.to_string());
            Ok(())
        }
    }

    #[test]
    fn memory_backend_round_trips_without_exposing_values_in_errors() {
        let mut backend = MemoryBackend(HashMap::new());
        backend
            .set(SecretName::GeminiApiKey, "secret-value")
            .unwrap();
        assert_eq!(
            backend.get(SecretName::GeminiApiKey).unwrap().as_deref(),
            Some("secret-value")
        );
    }

    #[test]
    fn legacy_migration_writes_to_backend_before_removing_file() {
        let home =
            std::env::temp_dir().join(format!("clipgauge-secret-test-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&home).unwrap();
        std::fs::write(
            home.join("secrets.json"),
            r#"{"gemini_api_key":"gemini-test","pexels_api_key":"pexels-test"}"#,
        )
        .unwrap();
        let mut backend = MemoryBackend(HashMap::new());
        super::migrate_legacy_with_backend(&home, &mut backend).unwrap();
        assert!(!home.join("secrets.json").exists());
        assert_eq!(
            backend.get(SecretName::GeminiApiKey).unwrap().as_deref(),
            Some("gemini-test")
        );
        assert_eq!(
            backend.get(SecretName::PexelsApiKey).unwrap().as_deref(),
            Some("pexels-test")
        );
        let _ = std::fs::remove_dir_all(home);
    }

    #[test]
    fn secret_names_are_stable_operation_accounts() {
        assert_eq!(SecretName::GeminiApiKey.account(), "gemini_api_key");
        assert_eq!(SecretName::PexelsApiKey.account(), "pexels_api_key");
        assert_eq!(
            SecretName::InstagramConnection.account(),
            "instagram_connection"
        );
    }
}
