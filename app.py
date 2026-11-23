"""Local web server for the Dua Kelinci sales recap. Standard library only.

    python app.py            -> http://localhost:8000
    python app.py 8080       -> another port

Which file is shown, in order:
  1. SALES_CSV, if that environment variable is set
  2. the newest .csv in data/uploads/ (put there by the page's "Ganti data"
     button, or copied in by hand)
  3. data/sales.csv, the bundled sample
"""

import json
import os
import re
import shutil
import sys
import time
from urllib.parse import unquote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sales_report import build_report

ROOT = Path(__file__).resolve().parent
SAMPLE_CSV = ROOT / "data" / "sales.csv"
UPLOAD_DIR = ROOT / "data" / "uploads"
INDEX = ROOT / "static" / "index.html"
LOGO = ROOT / "static" / "logo.png"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def active_csv():
    """Return (path, is_sample) for the file the page should show."""
    override = os.environ.get("SALES_CSV")
    if override:
        return Path(override), False
    uploads = sorted(UPLOAD_DIR.glob("*.csv"), key=lambda f: f.stat().st_mtime) if UPLOAD_DIR.is_dir() else []
    if uploads:
        return uploads[-1], False
    return SAMPLE_CSV, True


def current_report():
    path, is_sample = active_csv()
    report = build_report(path, sample=is_sample)
    report["file"] = path.name if path.parent == UPLOAD_DIR else str(path.relative_to(ROOT)).replace("\\", "/") \
        if ROOT in path.parents else str(path)
    report["is_sample"] = is_sample
    report["can_reset"] = (not is_sample) and not os.environ.get("SALES_CSV")
    return report


def save_upload(name, body):
    """Check an uploaded file first; keep it only if every row can be read.

    A rejected file never replaces the data that is currently shown.
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name or "sales.csv").name).strip("._") or "sales"
    if not safe.lower().endswith(".csv"):
        safe += ".csv"
    pending = UPLOAD_DIR / (safe + ".part")  # not *.csv, so it is never picked up half-written
    pending.write_bytes(body)
    try:
        report = build_report(pending, sample=False)
    except Exception as exc:
        report = {"ok": False, "errors": ["Unexpected error: %s" % exc]}
    if not report["ok"]:
        pending.unlink()
        return {"ok": False, "errors": report["errors"]}
    final = UPLOAD_DIR / ("%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), safe))
    pending.replace(final)
    return {"ok": True, "file": final.name}


def reset_to_sample():
    """Move uploaded files aside (not deleted) so the bundled sample shows again."""
    archive = UPLOAD_DIR / "archive"
    moved = 0
    if UPLOAD_DIR.is_dir():
        for path in UPLOAD_DIR.glob("*.csv"):
            archive.mkdir(exist_ok=True)
            shutil.move(str(path), str(archive / path.name))
            moved += 1
    return {"ok": True, "moved": moved}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, status=200):
        self._send(status, "application/json; charset=utf-8", json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", INDEX.read_bytes())
        elif path == "/api/report":
            # Re-read the file on every request: change the data, refresh the page.
            try:
                report = current_report()
            except Exception as exc:  # never show the manager a blank page
                report = {"ok": False, "errors": ["Unexpected error: %s" % exc], "warnings": [],
                          "file": str(active_csv()[0])}
            self._json(report)
        elif path == "/logo.png":
            self._send(200, "image/png", LOGO.read_bytes())
        elif path == "/sales.csv" and active_csv()[0].is_file():
            self._send(200, "text/csv; charset=utf-8", active_csv()[0].read_bytes())
        else:
            self._send(404, "text/plain; charset=utf-8", b"Not found")

    def do_POST(self):
        path = self.path.split("?")[0]
        # Browsers cannot add this header from another website without asking
        # first, so a page on the internet cannot push files into this app.
        if self.headers.get("X-Requested-With") != "sales-recap":
            self._json({"ok": False, "errors": ["Request not allowed."]}, 403)
        elif path == "/api/upload":
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                self._json({"ok": False, "errors": ["The file is empty."]}, 400)
            elif length > MAX_UPLOAD_BYTES:
                # Read and drop the body so the browser gets the answer instead of a broken connection.
                remaining = min(length, 20 * MAX_UPLOAD_BYTES)
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                self._json({"ok": False, "errors": ["The file is larger than 5 MB."]}, 413)
            else:
                self._json(save_upload(unquote(self.headers.get("X-Filename") or ""), self.rfile.read(length)))
        elif path == "/api/reset":
            self._json(reset_to_sample())
        else:
            self._json({"ok": False, "errors": ["Not found."]}, 404)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s  %s\n" % (self.log_date_time_string(), fmt % args))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("Dua Kelinci sales recap: http://localhost:%d" % port)
    print("Data file: %s" % active_csv()[0])
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
