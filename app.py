#!/usr/bin/env python3
"""Local app: serves the report and lets the "Run now" button start a scan.

  python3 app.py          then the report opens at http://127.0.0.1:8765

Only reachable from your own computer.
"""
import json
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "output" / "report.html"
HOST, PORT = "127.0.0.1", 8765

state = {"running": False, "started_at": None, "finished_at": None, "exit_code": None, "log": []}
lock = threading.Lock()

EMPTY_PAGE = """<!doctype html><meta charset="utf-8"><title>Sealed Pokémon Scanner</title>
<body style="font:15px system-ui;max-width:560px;margin:80px auto;padding:0 16px">
<h1>Sealed Pokémon Scanner</h1><p>No report yet. Start your first scan:</p>
<button id="run" style="font:inherit;padding:8px 16px;cursor:pointer">Run now</button> <span id="st"></span>
<script>
document.getElementById('run').onclick=async()=>{await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});poll();};
async function poll(){const s=await (await fetch('/api/status')).json();document.getElementById('st').textContent=s.running?(s.log.slice(-1)[0]||'Starting…'):'';
if(s.running)setTimeout(poll,2000);else if(s.exit_code===0)location.reload();}
</script>"""


def run_scan():
    with lock:
        state.update(running=True, started_at=datetime.now().isoformat(timespec="seconds"),
                     finished_at=None, exit_code=None, log=[])
    proc = subprocess.Popen([sys.executable, "-u", "scan.py"], cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    for line in proc.stdout:
        with lock:
            state["log"] = (state["log"] + [line.rstrip()])[-200:]
    code = proc.wait()
    with lock:
        state.update(running=False, exit_code=code, finished_at=datetime.now().isoformat(timespec="seconds"))


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/report.html"):
            self._send(200, REPORT.read_text(encoding="utf-8") if REPORT.exists() else EMPTY_PAGE, "text/html")
        elif path == "/api/status":
            with lock:
                self._send(200, json.dumps(state))
        else:
            self._send(404, '{"error": "not found"}')

    def do_POST(self):
        # JSON content type forces a CORS preflight, so other websites can't trigger scans.
        if self.path != "/api/run" or "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._send(400, '{"error": "bad request"}')
        with lock:
            busy = state["running"]
        if not busy:
            threading.Thread(target=run_scan, daemon=True).start()
        self._send(202, json.dumps({"started": not busy}))

    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/"
    print(f"Scanner app running at {url}  (press Ctrl+C to stop)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
