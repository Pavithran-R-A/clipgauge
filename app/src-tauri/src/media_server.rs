use std::collections::HashMap;
use std::fs::{self, File};
use std::io::{self, BufRead, BufReader, Read, Seek, SeekFrom, Write};
use std::net::{Shutdown, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use uuid::Uuid;

const CAPABILITY_LIFETIME: Duration = Duration::from_secs(30 * 60);
const MAX_REQUEST_BYTES: usize = 16 * 1024;

struct Capability {
    path: PathBuf,
    expires_at: Instant,
}

struct Inner {
    listener_addr: std::net::SocketAddr,
    capabilities: Mutex<HashMap<String, Capability>>,
    stopping: AtomicBool,
    external_handles: AtomicUsize,
}

pub struct MediaServer {
    inner: Arc<Inner>,
}

impl MediaServer {
    pub fn start() -> io::Result<Self> {
        let listener = TcpListener::bind(("127.0.0.1", 0))?;
        listener.set_nonblocking(true)?;
        let listener_addr = listener.local_addr()?;
        let inner = Arc::new(Inner {
            listener_addr,
            capabilities: Mutex::new(HashMap::new()),
            stopping: AtomicBool::new(false),
            external_handles: AtomicUsize::new(1),
        });
        let worker_inner = Arc::clone(&inner);
        thread::Builder::new()
            .name("clipgauge-media-server".to_string())
            .spawn(move || serve(listener, worker_inner))?;
        Ok(Self { inner })
    }

    pub fn authorize(&self, path: PathBuf) -> Result<String, String> {
        if fs::symlink_metadata(&path)
            .map(|metadata| metadata.file_type().is_symlink())
            .unwrap_or(false)
        {
            return Err("media artifact cannot be a symlink".to_string());
        }
        let canonical =
            fs::canonicalize(&path).map_err(|_| "media artifact is unavailable".to_string())?;
        let metadata =
            fs::metadata(&canonical).map_err(|_| "media artifact is unavailable".to_string())?;
        if !metadata.is_file() {
            return Err("media artifact is not a regular file".to_string());
        }
        let token = Uuid::new_v4().simple().to_string();
        let mut capabilities = self
            .inner
            .capabilities
            .lock()
            .map_err(|_| "media server state is unavailable".to_string())?;
        prune_expired(&mut capabilities);
        capabilities.insert(
            token.clone(),
            Capability {
                path: canonical,
                expires_at: Instant::now() + CAPABILITY_LIFETIME,
            },
        );
        Ok(format!(
            "http://127.0.0.1:{}/media/{}",
            self.inner.listener_addr.port(),
            token
        ))
    }

    #[cfg(test)]
    fn capability_count(&self) -> usize {
        self.inner
            .capabilities
            .lock()
            .map(|map| map.len())
            .unwrap_or(0)
    }

    #[cfg(test)]
    fn port(&self) -> u16 {
        self.inner.listener_addr.port()
    }
}

impl Clone for MediaServer {
    fn clone(&self) -> Self {
        self.inner.external_handles.fetch_add(1, Ordering::AcqRel);
        Self {
            inner: Arc::clone(&self.inner),
        }
    }
}

impl Drop for MediaServer {
    fn drop(&mut self) {
        if self.inner.external_handles.fetch_sub(1, Ordering::AcqRel) == 1 {
            self.inner.stopping.store(true, Ordering::Release);
            wake_listener(self.inner.listener_addr);
        }
    }
}

fn prune_expired(capabilities: &mut HashMap<String, Capability>) {
    let now = Instant::now();
    capabilities.retain(|_, capability| capability.expires_at > now);
}

fn wake_listener(addr: std::net::SocketAddr) {
    let _ = TcpStream::connect_timeout(&addr, Duration::from_millis(100));
}

fn serve(listener: TcpListener, inner: Arc<Inner>) {
    while !inner.stopping.load(Ordering::Acquire) {
        match listener.accept() {
            Ok((stream, _)) => {
                let worker_inner = Arc::clone(&inner);
                thread::spawn(move || handle_connection(stream, worker_inner));
            }
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(10));
            }
            Err(_) => break,
        }
    }
}

fn handle_connection(mut stream: TcpStream, inner: Arc<Inner>) {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(3)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(10)));
    let request = match read_request(&mut stream) {
        Ok(request) => request,
        Err(_) => {
            let _ = write_error(&mut stream, 400, "Bad Request", None);
            let _ = stream.shutdown(Shutdown::Both);
            return;
        }
    };
    let response = dispatch(&request, &inner);
    let _ = write_response(&mut stream, response);
    let _ = stream.shutdown(Shutdown::Both);
}

struct Request {
    method: String,
    target: String,
    headers: HashMap<String, String>,
}

struct Response {
    status: u16,
    reason: &'static str,
    content_type: &'static str,
    content_length: u64,
    content_range: Option<String>,
    body: Option<(File, u64)>,
}

fn read_request(stream: &mut TcpStream) -> io::Result<Request> {
    let mut reader = BufReader::new(stream.try_clone()?);
    let mut bytes = Vec::new();
    loop {
        let mut line = Vec::new();
        let count = reader.read_until(b'\n', &mut line)?;
        if count == 0 {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "empty request",
            ));
        }
        bytes.extend_from_slice(&line);
        if bytes.len() > MAX_REQUEST_BYTES {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "request too large",
            ));
        }
        if bytes.ends_with(b"\r\n\r\n") || bytes.ends_with(b"\n\n") {
            break;
        }
    }
    let text = String::from_utf8(bytes)
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "request is not utf8"))?;
    let mut lines = text.lines();
    let first = lines
        .next()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "missing request line"))?;
    let mut parts = first.split_whitespace();
    let method = parts.next().unwrap_or_default().to_string();
    let target = parts.next().unwrap_or_default().to_string();
    let version = parts.next().unwrap_or_default();
    if method.is_empty() || target.is_empty() || version != "HTTP/1.1" && version != "HTTP/1.0" {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid request line",
        ));
    }
    let mut headers = HashMap::new();
    for line in lines {
        if line.is_empty() {
            break;
        }
        if let Some((key, value)) = line.split_once(':') {
            headers.insert(key.trim().to_ascii_lowercase(), value.trim().to_string());
        }
    }
    Ok(Request {
        method,
        target,
        headers,
    })
}

fn dispatch(request: &Request, inner: &Inner) -> Response {
    if request.method != "GET" && request.method != "HEAD" {
        return empty_response(405, "Method Not Allowed");
    }
    let token = match token_from_target(&request.target) {
        Some(token) => token,
        None => return empty_response(404, "Not Found"),
    };
    let capability = match inner.capabilities.lock() {
        Ok(mut capabilities) => {
            prune_expired(&mut capabilities);
            capabilities
                .get(token)
                .map(|capability| (capability.path.clone(), capability.expires_at))
        }
        Err(_) => None,
    };
    let Some((path, expires_at)) = capability else {
        return empty_response(404, "Not Found");
    };
    if expires_at <= Instant::now() {
        return empty_response(404, "Not Found");
    }
    let metadata = match fs::metadata(&path) {
        Ok(metadata) if metadata.is_file() => metadata,
        _ => return empty_response(404, "Not Found"),
    };
    let length = metadata.len();
    let content_type = content_type_for(&path);
    let range = request
        .headers
        .get("range")
        .map(|value| parse_range(value, length));
    let (status, reason, start, end, content_range) = match range {
        None => (200, "OK", 0, length.saturating_sub(1), None),
        Some(Ok((start, end))) => (
            206,
            "Partial Content",
            start,
            end,
            Some(format!("bytes {}-{}/{}", start, end, length)),
        ),
        Some(Err(())) => {
            return Response {
                status: 416,
                reason: "Range Not Satisfiable",
                content_type,
                content_length: 0,
                content_range: Some(format!("bytes */{}", length)),
                body: None,
            }
        }
    };
    let content_length = if length == 0 { 0 } else { end - start + 1 };
    if request.method == "HEAD" || length == 0 {
        return Response {
            status,
            reason,
            content_type,
            content_length,
            content_range,
            body: None,
        };
    }
    let mut file = match File::open(&path) {
        Ok(file) => file,
        Err(_) => return empty_response(404, "Not Found"),
    };
    if file.seek(SeekFrom::Start(start)).is_err() {
        return empty_response(404, "Not Found");
    }
    Response {
        status,
        reason,
        content_type,
        content_length,
        content_range,
        body: Some((file, content_length)),
    }
}

fn token_from_target(target: &str) -> Option<&str> {
    let path = target
        .split_once('?')
        .map(|(path, _)| path)
        .unwrap_or(target);
    let mut parts = path.split('/');
    if parts.next()? != "" || parts.next()? != "media" {
        return None;
    }
    let token = parts.next()?;
    if parts.next().is_some()
        || token.len() != 32
        || !token.bytes().all(|byte| byte.is_ascii_hexdigit())
    {
        return None;
    }
    Some(token)
}

fn parse_range(value: &str, length: u64) -> Result<(u64, u64), ()> {
    if length == 0 || !value.starts_with("bytes=") {
        return Err(());
    }
    let range = value[6..].trim();
    if range.is_empty() || range.contains(',') {
        return Err(());
    }
    let (start_text, end_text) = range.split_once('-').ok_or(())?;
    if start_text.is_empty() {
        let suffix = end_text.parse::<u64>().map_err(|_| ())?;
        if suffix == 0 {
            return Err(());
        }
        let start = length.saturating_sub(suffix);
        return Ok((start, length - 1));
    }
    let start = start_text.parse::<u64>().map_err(|_| ())?;
    if start >= length {
        return Err(());
    }
    let end = if end_text.is_empty() {
        length - 1
    } else {
        end_text.parse::<u64>().map_err(|_| ())?.min(length - 1)
    };
    if start > end {
        return Err(());
    }
    Ok((start, end))
}

fn content_type_for(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|extension| extension.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase()
        .as_str()
    {
        "mp4" => "video/mp4",
        "webm" => "video/webm",
        "mov" => "video/quicktime",
        _ => "application/octet-stream",
    }
}

fn empty_response(status: u16, reason: &'static str) -> Response {
    Response {
        status,
        reason,
        content_type: "text/plain; charset=utf-8",
        content_length: 0,
        content_range: None,
        body: None,
    }
}

fn write_error(
    stream: &mut TcpStream,
    status: u16,
    reason: &'static str,
    content_range: Option<String>,
) -> io::Result<()> {
    write_response(
        stream,
        Response {
            status,
            reason,
            content_type: "text/plain; charset=utf-8",
            content_length: 0,
            content_range,
            body: None,
        },
    )
}

fn write_response(stream: &mut TcpStream, mut response: Response) -> io::Result<()> {
    let mut headers = format!(
        "HTTP/1.1 {} {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nAccept-Ranges: bytes\r\nConnection: close\r\n",
        response.status, response.reason, response.content_type, response.content_length
    );
    if let Some(content_range) = response.content_range.take() {
        headers.push_str(&format!("Content-Range: {}\r\n", content_range));
    }
    headers.push_str("\r\n");
    stream.write_all(headers.as_bytes())?;
    if let Some((mut file, mut remaining)) = response.body.take() {
        let mut buffer = [0u8; 16 * 1024];
        while remaining > 0 {
            let wanted = remaining.min(buffer.len() as u64) as usize;
            let read = file.read(&mut buffer[..wanted])?;
            if read == 0 {
                break;
            }
            stream.write_all(&buffer[..read])?;
            remaining -= read as u64;
        }
    }
    Ok(())
}

#[cfg(test)]
fn mime_fixture() -> (PathBuf, Vec<u8>) {
    let root = std::env::temp_dir().join(format!(
        "clipgauge-media-server-{}",
        Uuid::new_v4().simple()
    ));
    fs::create_dir_all(&root).expect("create test root");
    let path = root.join("fixture.mp4");
    let bytes = (0u8..=255).cycle().take(4096).collect::<Vec<_>>();
    fs::write(&path, &bytes).expect("write test fixture");
    (path, bytes)
}

#[cfg(test)]
fn request(
    port: u16,
    token_url: &str,
    extra_headers: &[(&str, &str)],
) -> (u16, HashMap<String, String>, Vec<u8>) {
    let target = token_url
        .split_once("127.0.0.1:")
        .and_then(|(_, rest)| rest.split_once('/'))
        .map(|(_, path)| format!("/{}", path))
        .unwrap();
    let mut stream = TcpStream::connect(("127.0.0.1", port)).expect("connect media server");
    let mut text = format!("GET {} HTTP/1.1\r\nHost: 127.0.0.1\r\n", target);
    for (key, value) in extra_headers {
        text.push_str(&format!("{}: {}\r\n", key, value));
    }
    text.push_str("\r\n");
    stream.write_all(text.as_bytes()).expect("write request");
    let mut response = Vec::new();
    stream.read_to_end(&mut response).expect("read response");
    let separator = response
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .expect("response headers");
    let header_text = String::from_utf8_lossy(&response[..separator]);
    let mut lines = header_text.lines();
    let status = lines
        .next()
        .unwrap()
        .split_whitespace()
        .nth(1)
        .unwrap()
        .parse()
        .unwrap();
    let mut headers = HashMap::new();
    for line in lines {
        if let Some((key, value)) = line.split_once(':') {
            headers.insert(key.to_ascii_lowercase(), value.trim().to_string());
        }
    }
    (status, headers, response[separator + 4..].to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(unix)]
    use std::os::unix::fs::symlink;

    #[test]
    fn binds_loopback_with_ephemeral_port() {
        let server = MediaServer::start().unwrap();
        assert!(server.port() > 0);
        assert_eq!(server.inner.listener_addr.ip().to_string(), "127.0.0.1");
    }

    #[test]
    fn serves_full_get_and_correct_headers() {
        let (path, bytes) = mime_fixture();
        let server = MediaServer::start().unwrap();
        let url = server.authorize(path.clone()).unwrap();
        let (status, headers, body) = request(server.port(), &url, &[]);
        assert_eq!(status, 200);
        assert_eq!(body, bytes);
        assert_eq!(
            headers.get("content-length").unwrap(),
            &bytes.len().to_string()
        );
        assert_eq!(headers.get("content-type").unwrap(), "video/mp4");
        assert_eq!(headers.get("accept-ranges").unwrap(), "bytes");
        let _ = fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    fn serves_head_without_body() {
        let (path, bytes) = mime_fixture();
        let server = MediaServer::start().unwrap();
        let url = server.authorize(path.clone()).unwrap();
        let mut stream = TcpStream::connect(("127.0.0.1", server.port())).unwrap();
        let target = format!("/media/{}", url.rsplit('/').next().unwrap());
        write!(
            stream,
            "HEAD {} HTTP/1.1\r\nHost: localhost\r\n\r\n",
            target
        )
        .unwrap();
        let mut response = Vec::new();
        stream.read_to_end(&mut response).unwrap();
        assert!(String::from_utf8_lossy(&response).contains("200 OK"));
        assert!(String::from_utf8_lossy(&response)
            .contains(&format!("Content-Length: {}", bytes.len())));
        assert!(response.ends_with(b"\r\n\r\n"));
        let _ = fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    fn supports_first_middle_open_ended_and_suffix_ranges() {
        let (path, bytes) = mime_fixture();
        let server = MediaServer::start().unwrap();
        let url = server.authorize(path.clone()).unwrap();
        for (range, expected) in [
            ("bytes=0-1023", bytes[0..1024].to_vec()),
            ("bytes=1024-1535", bytes[1024..1536].to_vec()),
            ("bytes=3000-", bytes[3000..].to_vec()),
            ("bytes=-512", bytes[bytes.len() - 512..].to_vec()),
        ] {
            let (status, headers, body) = request(server.port(), &url, &[("Range", range)]);
            assert_eq!(status, 206);
            assert_eq!(body, expected);
            assert_eq!(headers.get("accept-ranges").unwrap(), "bytes");
            assert!(headers.contains_key("content-range"));
        }
        let _ = fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    fn rejects_invalid_and_unsatisfiable_ranges_with_416() {
        let (path, _) = mime_fixture();
        let server = MediaServer::start().unwrap();
        let url = server.authorize(path.clone()).unwrap();
        for range in ["bytes=bad", "bytes=0-1,4-5", "bytes=4096-", "bytes=5-2"] {
            let (status, headers, body) = request(server.port(), &url, &[("Range", range)]);
            assert_eq!(status, 416);
            assert_eq!(body.len(), 0);
            assert_eq!(headers.get("content-range").unwrap(), "bytes */4096");
        }
        let _ = fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    fn rejects_unknown_capability_traversal_and_unsupported_method() {
        let (path, _) = mime_fixture();
        let server = MediaServer::start().unwrap();
        let url = server.authorize(path.clone()).unwrap();
        let unknown = format!(
            "http://127.0.0.1:{}/media/00000000000000000000000000000000",
            server.port()
        );
        assert_eq!(request(server.port(), &unknown, &[]).0, 404);
        assert_eq!(
            request(server.port(), &format!("{}/../etc/passwd", url), &[]).0,
            404
        );
        let mut stream = TcpStream::connect(("127.0.0.1", server.port())).unwrap();
        let target = format!("/media/{}", url.rsplit('/').next().unwrap());
        write!(
            stream,
            "POST {} HTTP/1.1\r\nHost: localhost\r\n\r\n",
            target
        )
        .unwrap();
        let mut response = String::new();
        stream.read_to_string(&mut response).unwrap();
        assert!(response.contains("405 Method Not Allowed"));
        let _ = fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    #[cfg(unix)]
    fn rejects_directory_and_symlink_escape_at_authorization() {
        let (path, _) = mime_fixture();
        let server = MediaServer::start().unwrap();
        assert!(server
            .authorize(path.parent().unwrap().to_path_buf())
            .is_err());
        let outside =
            std::env::temp_dir().join(format!("clipgauge-outside-{}", Uuid::new_v4().simple()));
        fs::write(&outside, b"private").unwrap();
        let link = path.parent().unwrap().join("symlink.mp4");
        symlink(&outside, &link).unwrap();
        assert!(server.authorize(link).is_err());
        let url = server.authorize(path.clone()).unwrap();
        assert_eq!(request(server.port(), &url, &[]).0, 200);
        let _ = fs::remove_dir_all(path.parent().unwrap());
        let _ = fs::remove_file(outside);
    }

    #[test]
    fn concurrent_authorized_files_are_isolated() {
        let (path_a, bytes_a) = mime_fixture();
        let (path_b, bytes_b) = mime_fixture();
        let server = MediaServer::start().unwrap();
        let url_a = server.authorize(path_a.clone()).unwrap();
        let url_b = server.authorize(path_b.clone()).unwrap();
        assert_ne!(url_a, url_b);
        assert_eq!(request(server.port(), &url_a, &[]).2, bytes_a);
        assert_eq!(request(server.port(), &url_b, &[]).2, bytes_b);
        assert_eq!(server.capability_count(), 2);
        let _ = fs::remove_dir_all(path_a.parent().unwrap());
        let _ = fs::remove_dir_all(path_b.parent().unwrap());
    }

    #[test]
    fn clone_lifecycle_and_final_handle_stop_server() {
        let server = MediaServer::start().unwrap();
        let port = server.port();
        let clone = server.clone();
        drop(server);
        assert!(TcpStream::connect(("127.0.0.1", port)).is_ok());
        drop(clone);
        thread::sleep(Duration::from_millis(60));
        assert!(TcpStream::connect(("127.0.0.1", port)).is_err());
    }

    #[test]
    fn capability_expiration_is_pruned() {
        let (path, _) = mime_fixture();
        let server = MediaServer::start().unwrap();
        let token = Uuid::new_v4().simple().to_string();
        server.inner.capabilities.lock().unwrap().insert(
            token,
            Capability {
                path: path.clone(),
                expires_at: Instant::now() - Duration::from_secs(1),
            },
        );
        assert_eq!(server.capability_count(), 1);
        let _ = server.authorize(path.clone()).unwrap();
        assert_eq!(server.capability_count(), 1);
        let _ = fs::remove_dir_all(path.parent().unwrap());
    }
}
