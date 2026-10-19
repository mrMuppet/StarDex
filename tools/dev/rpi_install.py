"""Install .pkg files on the PS4 through the Remote Package Installer (flatz, port 12800).

  python rpi_install.py PKG [PKG ...] [--ps4 PS4-IP] --host PC-IP [--port 8765]

Serves the packages from this PC over HTTP with Range support (RPI fetches in parts; python's
http.server cannot do that), sends one install request per package and keeps serving until every
package has been transferred completely (the PS4 downloads in the background).
"""
import argparse
import json
import urllib.error
import re
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # tools/
from local_config import host  # noqa: E402

FILES: dict[str, Path] = {}
SENT: dict[str, int] = {}
LOCK = threading.Lock()
VERBOSE = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if VERBOSE:
            print(f"  [{self.address_string()}] {fmt % args} Range={self.headers.get('Range')}", flush=True)

    def _send(self, body: bool):
        path = FILES.get(self.path.lstrip("/"))
        if not path:
            self.send_error(404)
            return
        size = path.stat().st_size
        start, end = 0, size - 1
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if m:
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = size - int(m.group(2))
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        if not body:
            return
        with path.open("rb") as f:
            f.seek(start)
            left = end - start + 1
            try:
                while left:
                    chunk = f.read(min(left, 1 << 20))
                    self.wfile.write(chunk)
                    left -= len(chunk)
                    with LOCK:
                        SENT[path.name] = SENT.get(path.name, 0) + len(chunk)
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                pass

    def do_GET(self):
        self._send(True)

    def do_HEAD(self):
        self._send(False)


def api(ps4, endpoint, payload):
    req = urllib.request.Request(f"http://{ps4}:12800/api/{endpoint}", json.dumps(payload).encode())
    try:
        return urllib.request.urlopen(req, timeout=60).read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode(errors='replace')}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pkgs", nargs="+", type=Path)
    ap.add_argument("--ps4", default=host("ps4"))
    ap.add_argument("--host", required=True, help="this PC's address as seen from the PS4")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("-v", "--verbose", action="store_true", help="log every HTTP request")
    a = ap.parse_args()
    global VERBOSE
    VERBOSE = a.verbose
    for p in a.pkgs:
        FILES[p.name] = p.resolve()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for name in FILES:
        r = api(a.ps4, "install", {"type": "direct", "packages": [f"http://{a.host}:{a.port}/{name}"]})
        print(f"{name}: {r.strip()}", flush=True)
    # keep serving until each package went over the wire at least once in full
    last = time.time()
    while True:
        with LOCK:
            done = [n for n, p in FILES.items() if SENT.get(n, 0) >= p.stat().st_size]
            total = sum(SENT.values())
        if len(done) == len(FILES):
            break
        time.sleep(5)
        with LOCK:
            if sum(SENT.values()) != total:
                last = time.time()
        if time.time() - last > 300:
            print("no transfer for 5 min, stopping", flush=True)
            break
    print(f"transferred: {len(done)}/{len(FILES)}", flush=True)
    time.sleep(10)
    srv.shutdown()


if __name__ == "__main__":
    main()
