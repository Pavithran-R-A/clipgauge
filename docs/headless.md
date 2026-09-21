# Headless ClipGauge

The optional headless image packages the Python pipeline, CLI, FastAPI
service, and FFmpeg. It does not replace the desktop application.

Build and run locally:

```text
docker compose -f docker-compose.headless.yml up --build
```

Set `CLIPGAUGE_SERVER_TOKEN` before starting. The image binds the service
inside the container and maps it to loopback on the host. The persistent home
is mounted at `/data/.clipgauge`.

The image does not advertise GPU support. Models and runtimes are not silently
downloaded during container startup. Readiness reports setup requirements.
CPU processing requires realistic RAM, disk, and FFmpeg headroom for the
selected models and input media.
