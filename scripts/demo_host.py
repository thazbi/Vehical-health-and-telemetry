from __future__ import annotations

import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
GUIDE_ROOT = ROOT / "docs" / "guide"
LOG_ROOT = ROOT / ".runtime-logs"
WEB_HOST = "127.0.0.1"
WEB_PORT = 8787
SERVICES = {
    "vehicle": ("services.vehicle_service.app.main:app", 8811),
    "telemetry": ("services.telemetry_service.app.main:app", 8812),
    "alerts": ("services.alert_service.app.main:app", 8813),
}
HEALTH_PATHS = {
    "vehicle": "/health/live",
    "telemetry": "/health/live",
    "alerts": "/health/ready",
}
STATIC_FILES = {
    "/": "demo.html",
    "/demo.html": "demo.html",
    "/demo.css": "demo.css",
    "/demo.js": "demo.js",
    "/styles.css": "styles.css",
    "/guide.js": "guide.js",
    "/guide": "index.html",
    "/guide/": "index.html",
    "/guide/index.html": "index.html",
    "/guide/styles.css": "styles.css",
    "/guide/guide.js": "guide.js",
}
API_PREFIXES = {
    "/api/vehicle": ("vehicle", 8811),
    "/api/telemetry": ("telemetry", 8812),
    "/api/alerts": ("alerts", 8813),
}
CHILDREN: list[subprocess.Popen[bytes]] = []
SERVER: ThreadingHTTPServer | None = None
STOPPING = threading.Event()


def port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        return probe.connect_ex((WEB_HOST, port)) == 0


def check_service(name: str, port: int) -> bool:
    url = f"http://{WEB_HOST}:{port}{HEALTH_PATHS[name]}"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            payload = json.loads(response.read())
            return response.status == 200 and payload.get("status") == "UP"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def start_services() -> None:
    LOG_ROOT.mkdir(exist_ok=True)
    for name, (app_path, port) in SERVICES.items():
        if port_is_open(port):
            if check_service(name, port):
                print(f"Reusing healthy {name} service on port {port}.")
                continue
            raise RuntimeError(
                f"Port {port} is already in use. Stop that process, then rerun " "START-DEMO.bat."
            )

        environment = os.environ.copy()
        if name == "telemetry":
            environment["VEHICLE_SERVICE_URL"] = f"http://{WEB_HOST}:{SERVICES['vehicle'][1]}"
            environment.setdefault("SERVICE_TIMEOUT_SECONDS", "2")
        elif name == "alerts":
            environment["VEHICLE_SERVICE_URL"] = f"http://{WEB_HOST}:{SERVICES['vehicle'][1]}"
            environment.setdefault("SERVICE_TIMEOUT_SECONDS", "2")
        environment.setdefault("BATTERY_TEMPERATURE_THRESHOLD", "50")
        environment.setdefault("RPM_THRESHOLD", "5000")
        environment.setdefault("SPEED_THRESHOLD", "140")
        environment.setdefault("LOG_LEVEL", "INFO")
        log_path = LOG_ROOT / f"{name}.log"
        log_file = log_path.open("ab")
        child = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                app_path,
                "--host",
                WEB_HOST,
                "--port",
                str(port),
                "--no-access-log",
            ],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        CHILDREN.append(child)
        log_file.close()
        print(f"Starting {name} on http://{WEB_HOST}:{port} (log: {log_path.relative_to(ROOT)})")

        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError(
                    f"{name} exited during startup. Inspect "
                    f"{log_path.relative_to(ROOT)} for details."
                )
            if check_service(name, port):
                print(f"{name} is ready.")
                break
            time.sleep(0.35)
        else:
            raise RuntimeError(
                f"{name} did not become healthy within 35 seconds. Inspect "
                f"{log_path.relative_to(ROOT)}."
            )


def stop_children() -> None:
    for child in reversed(CHILDREN):
        if child.poll() is None:
            child.terminate()
    for child in reversed(CHILDREN):
        if child.poll() is None:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)


class DemoHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(GUIDE_ROOT), **kwargs)

    def do_GET(self) -> None:
        if self._proxy_request():
            return
        path = unquote(urlsplit(self.path).path)
        if path == "/START-DEMO.bat":
            content = (ROOT / "START-DEMO.bat").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", "attachment; filename=START-DEMO.bat")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)
            return
        relative = STATIC_FILES.get(path)
        if relative is None:
            self.send_error(404, "Not found")
            return
        file_path = GUIDE_ROOT / relative
        try:
            content = file_path.read_bytes()
        except OSError:
            self.send_error(404, "Guide file not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(str(file_path)))
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        if not self._proxy_request():
            self.send_error(404, "Not found")

    def do_PUT(self) -> None:
        if not self._proxy_request():
            self.send_error(404, "Not found")

    def _proxy_request(self) -> bool:
        parsed = urlsplit(self.path)
        prefix = next(
            (
                candidate
                for candidate in API_PREFIXES
                if parsed.path == candidate or parsed.path.startswith(candidate + "/")
            ),
            None,
        )
        if prefix is None:
            return False

        _service_name, port = API_PREFIXES[prefix]
        suffix = parsed.path[len(prefix) :]
        target = f"http://{WEB_HOST}:{port}{suffix}"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        try:
            request_body = None
            if self.command in {"POST", "PUT", "PATCH"}:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 65536:
                    self.send_error(413, "Request body too large")
                    return True
                request_body = self.rfile.read(length)
            forwarded_headers = {
                key: self.headers[key]
                for key in ("Content-Type", "X-Request-ID")
                if key in self.headers
            }
            proxy_request = urllib.request.Request(
                target,
                data=request_body,
                headers=forwarded_headers,
                method=self.command,
            )
            with urllib.request.urlopen(proxy_request, timeout=5) as upstream:
                status = upstream.status
                response_body = upstream.read(1_000_001)
                response_type = upstream.headers.get("Content-Type", "application/json")
                request_id = upstream.headers.get("X-Request-ID")
        except urllib.error.HTTPError as error:
            status = error.code
            response_body = error.read(1_000_001)
            response_type = error.headers.get("Content-Type", "application/json")
            request_id = error.headers.get("X-Request-ID")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            response_body = json.dumps(
                {"error": "UPSTREAM_UNAVAILABLE", "message": str(error)}
            ).encode()
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
            return True

        if len(response_body) > 1_000_000:
            self.send_error(502, "Upstream response too large")
            return True
        self.send_response(status)
        self.send_header("Content-Type", response_type)
        self.send_header("Content-Length", str(len(response_body)))
        if request_id:
            self.send_header("X-Request-ID", request_id)
        self.end_headers()
        self.wfile.write(response_body)
        return True

    def log_message(self, format_string: str, *args: Any) -> None:
        logging.info("demo-host: " + format_string, *args)


def shutdown(_signum: int, _frame: Any) -> None:
    if STOPPING.is_set():
        return
    STOPPING.set()
    print("\nStopping services started by this demo...")
    stop_children()
    if SERVER is not None:
        threading.Thread(target=SERVER.shutdown, daemon=True).start()


def main() -> int:
    global SERVER
    if port_is_open(WEB_PORT):
        raise RuntimeError(
            f"Demo web port {WEB_PORT} is already in use. Close the other demo window, then retry."
        )

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)
    try:
        start_services()
        SERVER = ThreadingHTTPServer((WEB_HOST, WEB_PORT), DemoHandler)
        url = f"http://{WEB_HOST}:{WEB_PORT}/demo.html"
        print("\nAll APIs are healthy.")
        print(f"Live project dashboard: {url}")
        print("Keep this window open while using the demo. Press Ctrl+C to stop services.")
        webbrowser.open(url)
        SERVER.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        shutdown(signal.SIGINT, None)
    except Exception as error:
        print(f"\nDEMO STARTUP FAILED: {error}", file=sys.stderr)
        shutdown(signal.SIGTERM, None)
        return 1
    finally:
        stop_children()
        if SERVER is not None:
            SERVER.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
