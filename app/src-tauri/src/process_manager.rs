use std::collections::HashMap;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum LifecycleState {
    Queued,
    Starting,
    Running,
    Cancelling,
    Cancelled,
    Completed,
    Failed,
    Interrupted,
    Resumable,
}

impl LifecycleState {
    pub fn terminal(self) -> bool {
        matches!(
            self,
            Self::Cancelled | Self::Completed | Self::Failed | Self::Interrupted | Self::Resumable
        )
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LeaseRecord {
    pub protocol_version: u32,
    pub app_version: String,
    pub session_id: String,
    pub job_id: String,
    pub process_id: u32,
    pub started_at_ms: u128,
    pub heartbeat_at_ms: u128,
    pub stage: Option<String>,
    pub state: LifecycleState,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Reservation {
    pub key: String,
}

#[derive(Debug, Clone)]
pub struct JobRecord {
    pub key: String,
    pub job_id: Option<String>,
    pub process_id: Option<u32>,
    pub started_at_ms: u128,
    pub heartbeat_at_ms: u128,
    pub stage: Option<String>,
    pub state: LifecycleState,
    pub cancel_requested: bool,
}

#[derive(Debug, Default)]
pub struct ProcessManager {
    session_id: String,
    active: HashMap<String, JobRecord>,
    max_heavy_jobs: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ReserveError {
    Busy,
    AlreadyActive,
}

impl ProcessManager {
    pub fn new() -> Self {
        Self {
            session_id: Uuid::new_v4().to_string(),
            active: HashMap::new(),
            max_heavy_jobs: 1,
        }
    }

    pub fn session_id(&self) -> &str {
        &self.session_id
    }

    pub fn reserve(&mut self, key: impl Into<String>) -> Result<Reservation, ReserveError> {
        let key = key.into();
        if self.active.contains_key(&key) {
            return Err(ReserveError::AlreadyActive);
        }
        if self
            .active
            .values()
            .filter(|record| !record.state.terminal())
            .count()
            >= self.max_heavy_jobs
        {
            return Err(ReserveError::Busy);
        }
        let now = now_ms();
        self.active.insert(
            key.clone(),
            JobRecord {
                key: key.clone(),
                job_id: None,
                process_id: None,
                started_at_ms: now,
                heartbeat_at_ms: now,
                stage: None,
                state: LifecycleState::Starting,
                cancel_requested: false,
            },
        );
        Ok(Reservation { key })
    }

    pub fn adopt_job_id(&mut self, key: &str, job_id: impl Into<String>) -> Result<(), String> {
        let record = self
            .active
            .get_mut(key)
            .ok_or_else(|| "job reservation is no longer active".to_string())?;
        record.job_id = Some(job_id.into());
        Ok(())
    }

    pub fn register_process(&mut self, key: &str, process_id: u32) -> Result<(), String> {
        let record = self
            .active
            .get_mut(key)
            .ok_or_else(|| "job reservation is no longer active".to_string())?;
        record.process_id = Some(process_id);
        record.state = LifecycleState::Running;
        record.heartbeat_at_ms = now_ms();
        Ok(())
    }

    pub fn update_stage(&mut self, key: &str, stage: Option<String>) {
        if let Some(record) = self.active.get_mut(key) {
            record.stage = stage;
            record.heartbeat_at_ms = now_ms();
        }
    }

    pub fn request_cancel(&mut self, job_id: &str) -> Result<u32, String> {
        let record = self
            .active
            .values_mut()
            .find(|record| record.job_id.as_deref() == Some(job_id))
            .ok_or_else(|| "no active ClipGauge process owns this job".to_string())?;
        if record.state.terminal() {
            return Err("job is no longer active".to_string());
        }
        record.cancel_requested = true;
        record.state = LifecycleState::Cancelling;
        record
            .process_id
            .ok_or_else(|| "job is starting and has no cancellable process yet".to_string())
    }

    pub fn is_cancel_requested(&self, key: &str) -> bool {
        self.active
            .get(key)
            .map(|record| record.cancel_requested)
            .unwrap_or(false)
    }

    pub fn finish(&mut self, key: &str, success: bool) -> Option<LifecycleState> {
        let record = self.active.get_mut(key)?;
        let state = if record.cancel_requested {
            LifecycleState::Cancelled
        } else if success {
            LifecycleState::Completed
        } else {
            LifecycleState::Failed
        };
        record.state = state;
        record.heartbeat_at_ms = now_ms();
        Some(state)
    }

    pub fn mark_interrupted(lease: &LeaseRecord) -> LeaseRecord {
        let mut stale = lease.clone();
        stale.state = LifecycleState::Interrupted;
        stale
    }

    pub fn lease(
        &self,
        key: &str,
        app_version: &str,
        protocol_version: u32,
    ) -> Option<LeaseRecord> {
        let record = self.active.get(key)?;
        Some(LeaseRecord {
            protocol_version,
            app_version: app_version.to_string(),
            session_id: self.session_id.clone(),
            job_id: record.job_id.clone().unwrap_or_else(|| record.key.clone()),
            process_id: record.process_id.unwrap_or_default(),
            started_at_ms: record.started_at_ms,
            heartbeat_at_ms: record.heartbeat_at_ms,
            stage: record.stage.clone(),
            state: record.state,
        })
    }
}

fn now_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::{LifecycleState, ProcessManager, ReserveError};

    #[test]
    fn duplicate_and_concurrent_jobs_are_rejected() {
        let mut manager = ProcessManager::new();
        manager.reserve("job-a").unwrap();
        assert_eq!(manager.reserve("job-a"), Err(ReserveError::AlreadyActive));
        assert_eq!(manager.reserve("job-b"), Err(ReserveError::Busy));
    }

    #[test]
    fn cancellation_is_distinct_and_finishes_as_cancelled() {
        let mut manager = ProcessManager::new();
        manager.reserve("pending").unwrap();
        manager
            .adopt_job_id("pending", "20260819-120000-abcdef")
            .unwrap();
        manager.register_process("pending", 123).unwrap();
        assert_eq!(manager.request_cancel("20260819-120000-abcdef"), Ok(123));
        assert!(manager.is_cancel_requested("pending"));
        assert_eq!(
            manager.finish("pending", false),
            Some(LifecycleState::Cancelled)
        );
    }

    #[test]
    fn stale_lease_reconciliation_does_not_reuse_live_process_identity() {
        let mut manager = ProcessManager::new();
        manager.reserve("job-a").unwrap();
        manager
            .adopt_job_id("job-a", "20260819-120000-abcdef")
            .unwrap();
        manager.register_process("job-a", 123).unwrap();
        let lease = manager.lease("job-a", "0.1.0", 1).unwrap();
        let stale = ProcessManager::mark_interrupted(&lease);
        assert_eq!(stale.state, LifecycleState::Interrupted);
        assert_ne!(stale.session_id, "other-session");
        assert_eq!(stale.process_id, 123);
    }
}

pub fn terminate_owned(process_id: u32) -> Result<(), String> {
    #[cfg(unix)]
    {
        let group = -(process_id as i32);
        let result = unsafe { libc::kill(group, libc::SIGTERM) };
        if result != 0 {
            let error = std::io::Error::last_os_error();
            if error.raw_os_error() != Some(libc::ESRCH) {
                return Err(format!(
                    "could not request process-group cancellation: {error}"
                ));
            }
        }
        std::thread::spawn(move || {
            std::thread::sleep(std::time::Duration::from_secs(2));
            let _ = unsafe { libc::kill(group, libc::SIGKILL) };
        });
        Ok(())
    }

    #[cfg(windows)]
    {
        let status = std::process::Command::new("taskkill")
            .args(["/PID", &process_id.to_string(), "/T", "/F"])
            .status()
            .map_err(|error| format!("could not terminate owned process tree: {error}"))?;
        if status.success() {
            Ok(())
        } else {
            Err(format!("taskkill returned {status}"))
        }
    }
}

#[cfg(unix)]
pub fn configure_process_group(command: &mut std::process::Command) {
    use std::os::unix::process::CommandExt;
    unsafe {
        command.pre_exec(|| {
            if libc::setpgid(0, 0) != 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
}

#[cfg(not(unix))]
pub fn configure_process_group(_command: &mut std::process::Command) {}
