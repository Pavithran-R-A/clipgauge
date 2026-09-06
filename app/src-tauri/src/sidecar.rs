use std::io::{Read, Write};
use std::path::Path;
use std::process::{Command, ExitStatus, Stdio};
use std::sync::{
    atomic::{AtomicU64, Ordering},
    Arc, Condvar, Mutex,
};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

use crate::diagnostics::BoundedTail;
use crate::process_manager;

pub const MAX_DIAGNOSTIC_BYTES: usize = 64 * 1024;
pub const MAX_STDIN_BYTES: usize = 64 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PipelineMode {
    ReadOnly,
    Initialize,
    ManagedOperation,
}

pub fn pipeline_args(pipeline_dir: &Path, mode: PipelineMode) -> Vec<String> {
    let directory = pipeline_dir.to_string_lossy().into_owned();
    match mode {
        PipelineMode::Initialize => vec![
            "--directory".to_string(),
            directory,
            "sync".to_string(),
            "--locked".to_string(),
        ],
        PipelineMode::ReadOnly | PipelineMode::ManagedOperation => vec![
            "--directory".to_string(),
            directory,
            "run".to_string(),
            "--no-sync".to_string(),
            "clipgauge".to_string(),
        ],
    }
}

#[derive(Debug, Default)]
struct InitializationState {
    running: bool,
    ready: bool,
}

#[derive(Debug, Default)]
pub struct InitializationCoordinator {
    state: Mutex<InitializationState>,
    changed: Condvar,
}

impl InitializationCoordinator {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn ensure_initialized<F>(&self, initialize: F) -> Result<(), String>
    where
        F: FnOnce() -> Result<(), String>,
    {
        let mut state = self
            .state
            .lock()
            .map_err(|_| "pipeline initialization state is unavailable".to_string())?;
        loop {
            if state.ready {
                return Ok(());
            }
            if !state.running {
                state.running = true;
                break;
            }
            state = self
                .changed
                .wait(state)
                .map_err(|_| "pipeline initialization state is unavailable".to_string())?;
        }
        drop(state);

        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(initialize))
            .map_err(|_| "pipeline initialization panicked".to_string())
            .and_then(|result| result);
        let mut state = self
            .state
            .lock()
            .map_err(|_| "pipeline initialization state is unavailable".to_string())?;
        state.running = false;
        state.ready = result.is_ok();
        self.changed.notify_all();
        result
    }
}

#[derive(Debug, Clone, Copy)]
pub struct RunPolicy {
    pub hard_timeout: Duration,
    pub idle_timeout: Duration,
    pub poll_interval: Duration,
}

impl RunPolicy {
    pub fn status() -> Self {
        Self {
            hard_timeout: Duration::from_secs(30),
            idle_timeout: Duration::from_secs(10),
            poll_interval: Duration::from_millis(100),
        }
    }

    pub fn initialization() -> Self {
        Self {
            hard_timeout: Duration::from_secs(2 * 60 * 60),
            idle_timeout: Duration::from_secs(5 * 60),
            poll_interval: Duration::from_millis(250),
        }
    }

    pub fn interactive() -> Self {
        Self {
            hard_timeout: Duration::from_secs(30 * 60),
            idle_timeout: Duration::from_secs(15 * 60),
            poll_interval: Duration::from_millis(250),
        }
    }
}

#[derive(Debug)]
pub struct RunOutput {
    pub status: ExitStatus,
    pub stdout: String,
    pub stderr_tail: String,
}

#[derive(Debug, PartialEq, Eq)]
pub enum RunError {
    Spawn(String),
    Wait(String),
    HardTimeout,
    IdleTimeout,
}

fn collect_stream<R: Read + Send + 'static>(
    mut stream: R,
    activity: Arc<AtomicU64>,
    started: Instant,
) -> JoinHandle<String> {
    thread::spawn(move || {
        let mut tail = BoundedTail::new(MAX_DIAGNOSTIC_BYTES);
        let mut buffer = [0u8; 8192];
        loop {
            match stream.read(&mut buffer) {
                Ok(0) | Err(_) => break,
                Ok(count) => {
                    tail.push(&buffer[..count]);
                    activity.store(started.elapsed().as_millis() as u64, Ordering::Relaxed);
                }
            }
        }
        tail.text()
    })
}

pub fn run_bounded(command: Command, policy: RunPolicy) -> Result<RunOutput, RunError> {
    run_bounded_with_callback_and_stdin(command, policy, |_| {}, None)
}

pub fn run_bounded_with_callback<F>(
    command: Command,
    policy: RunPolicy,
    on_spawn: F,
) -> Result<RunOutput, RunError>
where
    F: FnOnce(u32),
{
    run_bounded_with_callback_and_stdin(command, policy, on_spawn, None)
}

pub fn run_bounded_with_stdin(
    command: Command,
    input: &[u8],
    policy: RunPolicy,
) -> Result<RunOutput, RunError> {
    run_bounded_with_callback_and_stdin(command, policy, |_| {}, Some(input))
}

fn run_bounded_with_callback_and_stdin<F>(
    mut command: Command,
    policy: RunPolicy,
    on_spawn: F,
    input: Option<&[u8]>,
) -> Result<RunOutput, RunError>
where
    F: FnOnce(u32),
{
    if input.is_some_and(|bytes| bytes.len() > MAX_STDIN_BYTES) {
        return Err(RunError::Wait(format!(
            "sidecar stdin exceeds {MAX_STDIN_BYTES}-byte safety limit"
        )));
    }
    process_manager::configure_process_group(&mut command);
    command.stdin(if input.is_some() {
        Stdio::piped()
    } else {
        Stdio::null()
    });
    let mut child = command
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| RunError::Spawn(error.to_string()))?;
    on_spawn(child.id());
    let started = Instant::now();
    let activity = Arc::new(AtomicU64::new(0));
    let stdout_reader = child
        .stdout
        .take()
        .map(|stream| collect_stream(stream, Arc::clone(&activity), started));
    let stderr_reader = child
        .stderr
        .take()
        .map(|stream| collect_stream(stream, Arc::clone(&activity), started));
    let stdin_writer = input.map(|input| {
        let data = input.to_vec();
        let stdin = child.stdin.take();
        thread::spawn(move || stdin.map_or(Ok(()), |mut stream| stream.write_all(&data)))
    });

    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) => {}
            Err(error) => {
                let _ = process_manager::terminate_owned(child.id());
                let _ = child.wait();
                return Err(RunError::Wait(error.to_string()));
            }
        }
        let elapsed = started.elapsed();
        if elapsed >= policy.hard_timeout {
            let _ = process_manager::terminate_owned(child.id());
            let _ = child.wait();
            let stdout = stdout_reader
                .and_then(|reader| reader.join().ok())
                .unwrap_or_default();
            let stderr_tail = stderr_reader
                .and_then(|reader| reader.join().ok())
                .unwrap_or_default();
            let _ = stdin_writer.and_then(|writer| writer.join().ok());
            let _ = (stdout, stderr_tail);
            return Err(RunError::HardTimeout);
        }
        let last_activity = Duration::from_millis(activity.load(Ordering::Relaxed));
        if elapsed.saturating_sub(last_activity) >= policy.idle_timeout {
            let _ = process_manager::terminate_owned(child.id());
            let _ = child.wait();
            let stdout = stdout_reader
                .and_then(|reader| reader.join().ok())
                .unwrap_or_default();
            let stderr_tail = stderr_reader
                .and_then(|reader| reader.join().ok())
                .unwrap_or_default();
            let _ = stdin_writer.and_then(|writer| writer.join().ok());
            let _ = (stdout, stderr_tail);
            return Err(RunError::IdleTimeout);
        }
        thread::sleep(policy.poll_interval);
    };

    let stdout = stdout_reader
        .and_then(|reader| reader.join().ok())
        .unwrap_or_default();
    let stderr_tail = stderr_reader
        .and_then(|reader| reader.join().ok())
        .unwrap_or_default();
    if let Some(writer) = stdin_writer {
        let write_result = writer
            .join()
            .map_err(|_| RunError::Wait("sidecar stdin writer panicked".to_string()))?
            .map_err(|error| RunError::Wait(error.to_string()));
        write_result?;
    }
    Ok(RunOutput {
        status,
        stdout,
        stderr_tail,
    })
}

#[cfg(test)]
impl RunPolicy {
    fn test() -> Self {
        Self {
            hard_timeout: Duration::from_secs(10),
            idle_timeout: Duration::from_secs(10),
            poll_interval: Duration::from_millis(10),
        }
    }

    fn test_idle_timeout() -> Self {
        Self {
            hard_timeout: Duration::from_secs(10),
            idle_timeout: Duration::from_millis(100),
            poll_interval: Duration::from_millis(10),
        }
    }
}

#[cfg(test)]
mod tests {
    use std::path::Path;
    use std::process::Command;
    use std::sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        Arc, Barrier,
    };
    use std::thread;
    use std::time::Duration;

    use super::{
        pipeline_args, run_bounded, InitializationCoordinator, PipelineMode, RunError, RunPolicy,
        MAX_DIAGNOSTIC_BYTES, MAX_STDIN_BYTES,
    };

    fn test_sleep_command() -> Command {
        #[cfg(target_os = "windows")]
        {
            let mut command = Command::new("powershell");
            command.args(["-NoProfile", "-Command", "Start-Sleep -Seconds 2"]);
            command
        }
        #[cfg(not(target_os = "windows"))]
        {
            let mut command = Command::new("sh");
            command.args(["-c", "sleep 2"]);
            command
        }
    }

    fn test_noisy_command() -> Command {
        #[cfg(target_os = "windows")]
        {
            let mut command = Command::new("powershell");
            command.args([
                "-NoProfile",
                "-Command",
                "$x = 'x' * 4096; 1..512 | ForEach-Object { [Console]::Error.Write($x) }",
            ]);
            command
        }
        #[cfg(not(target_os = "windows"))]
        {
            let mut command = Command::new("sh");
            command.args(["-c", "yes x | head -c 1048576 1>&2"]);
            command
        }
    }

    #[test]
    fn hanging_sidecar_returns_idle_timeout() {
        let result = run_bounded(test_sleep_command(), RunPolicy::test_idle_timeout());
        assert!(matches!(result, Err(RunError::IdleTimeout)));
    }

    #[test]
    fn noisy_sidecar_completes_without_pipe_deadlock() {
        let output = run_bounded(test_noisy_command(), RunPolicy::test()).unwrap();
        assert!(output.stderr_tail.len() <= MAX_DIAGNOSTIC_BYTES);
    }

    #[test]
    fn oversized_stdin_is_rejected_before_spawn() {
        let input = vec![b'x'; MAX_STDIN_BYTES + 1];
        let result = super::run_bounded_with_stdin(test_sleep_command(), &input, RunPolicy::test());
        assert!(matches!(result, Err(RunError::Wait(message)) if message.contains("safety limit")));
    }

    #[test]
    fn completed_sidecar_respects_hard_timeout_policy() {
        let result = run_bounded(
            test_sleep_command(),
            RunPolicy {
                hard_timeout: Duration::from_secs(10),
                idle_timeout: Duration::from_secs(10),
                poll_interval: Duration::from_millis(10),
            },
        );
        assert!(result.is_ok());
    }

    #[test]
    fn read_only_pipeline_never_requests_uv_sync() {
        let args = pipeline_args(Path::new("pipeline"), PipelineMode::ReadOnly);
        assert!(args.contains(&"--no-sync".to_string()));
        assert!(!args.contains(&"sync".to_string()));
    }

    #[test]
    fn initialize_pipeline_requests_locked_sync() {
        let args = pipeline_args(Path::new("pipeline"), PipelineMode::Initialize);
        assert_eq!(args, vec!["--directory", "pipeline", "sync", "--locked"]);
    }

    #[test]
    fn concurrent_initializers_share_one_result() {
        let coordinator = Arc::new(InitializationCoordinator::new());
        let calls = Arc::new(AtomicUsize::new(0));
        let barrier = Arc::new(Barrier::new(2));
        let handles = (0..2)
            .map(|_| {
                let coordinator = Arc::clone(&coordinator);
                let calls = Arc::clone(&calls);
                let barrier = Arc::clone(&barrier);
                thread::spawn(move || {
                    barrier.wait();
                    coordinator.ensure_initialized(|| {
                        calls.fetch_add(1, Ordering::SeqCst);
                        thread::sleep(Duration::from_millis(50));
                        Ok(())
                    })
                })
            })
            .collect::<Vec<_>>();
        assert!(handles
            .into_iter()
            .all(|handle| handle.join().unwrap().is_ok()));
        assert_eq!(calls.load(Ordering::SeqCst), 1);
    }

    #[test]
    fn failed_initialization_can_retry() {
        let coordinator = InitializationCoordinator::new();
        let fail = AtomicBool::new(true);
        assert!(coordinator
            .ensure_initialized(|| {
                if fail.swap(false, Ordering::SeqCst) {
                    Err("initialization failed".to_string())
                } else {
                    Ok(())
                }
            })
            .is_err());
        assert!(coordinator.ensure_initialized(|| Ok(())).is_ok());
    }
}
