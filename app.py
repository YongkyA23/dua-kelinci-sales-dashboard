"""Local web server for the Dua Kelinci sales dashboard. Standard library only.

    python app.py            -> http://localhost:8000
    python app.py 8080       -> another port
    SALES_CSV=path python app.py   -> another data file
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sales_report import build_report

ROOT = Path(__file__).resolve().parent
CSV_PATH = Path(os.environ.get("SALES_CSV", ROOT / "data" / "sales.csv"))
INDEX = ROOT / "static" / "index.html"
LOGO = ROOT / "static" / "logo.png"


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", INDEX.read_bytes())
        elif path == "/api/report":
            # Re-read the file on every request: replace sales.csv, refresh the page.
            try:
                report = build_report(CSV_PATH)
            except Exception as exc:  # never show the manager a blank page
                report = {"ok": False, "errors": ["Unexpected error: %s" % exc], "warnings": [],
                          "file": str(CSV_PATH)}
            body = json.dumps(report, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        elif path == "/logo.png":
            self._send(200, "image/png", LOGO.read_bytes())
        elif path == "/sales.csv" and CSV_PATH.is_file():
            self._send(200, "text/csv; charset=utf-8", CSV_PATH.read_bytes())
        else:
            self._send(404, "text/plain; charset=utf-8", b"Not found")

    def log_message(self, fmt, *args):
        sys.stderr.write("%s  %s\n" % (self.log_date_time_string(), fmt % args))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("Dua Kelinci sales dashboard: http://localhost:%d" % port)
    print("Data file: %s" % CSV_PATH)
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
