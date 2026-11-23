"""Upload, auto-detect and reset, tested against a real server on a free port."""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
import sales_report as sr  # noqa: E402

SAMPLE = (ROOT / "data" / "sales.csv").read_text(encoding="utf-8-sig")
HEADER = SAMPLE.splitlines()[0]
OCTOBER = "\n".join([HEADER] + [line for line in SAMPLE.splitlines() if line.startswith("2026-10")]) + "\n"
BROKEN = HEADER + "\n2026-09-01,INV1,Jabar,Bandung,OUT1,Toko A,Grosir,Andi,Sukro,Sukro Pedas 100g,5,198000,990000,0,n/a\n"


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_dir, self.old_env = app.UPLOAD_DIR, os.environ.pop("SALES_CSV", None)
        app.UPLOAD_DIR = Path(self.tmp.name) / "uploads"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        app.UPLOAD_DIR = self.old_dir
        if self.old_env is not None:
            os.environ["SALES_CSV"] = self.old_env
        self.tmp.cleanup()

    def call(self, path, body=None, headers=None):
        request = urllib.request.Request(self.base + path, data=body, headers=headers or {},
                                         method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def upload(self, text, name="data.csv"):
        return self.call("/api/upload", text.encode("utf-8"),
                         {"X-Requested-With": "sales-recap", "X-Filename": name})

    def test_starts_on_the_bundled_sample(self):
        _, report = self.call("/api/report")
        self.assertTrue(report["is_sample"])
        self.assertFalse(report["can_reset"])
        self.assertEqual(report["file"], "data/sales.csv")
        self.assertEqual(report["total_net"], 1728036900)

    def test_valid_upload_becomes_the_active_file(self):
        status, result = self.upload(OCTOBER, "oktober saja.csv")
        self.assertEqual((status, result["ok"]), (200, True))
        _, report = self.call("/api/report")
        self.assertFalse(report["is_sample"])
        self.assertTrue(report["can_reset"])
        self.assertTrue(report["file"].endswith("oktober_saja.csv"))
        self.assertEqual(report["total_net"], 878751200)
        self.assertEqual(report["warnings"], [])

    def test_rejected_upload_leaves_current_data_untouched(self):
        status, result = self.upload(BROKEN)
        self.assertEqual(status, 200)
        self.assertFalse(result["ok"])
        self.assertIn("Line 2", result["errors"][0])
        self.assertEqual(list(app.UPLOAD_DIR.glob("*")), [])
        _, report = self.call("/api/report")
        self.assertTrue(report["is_sample"])

    def test_reset_returns_to_sample_without_deleting_the_upload(self):
        self.upload(OCTOBER)
        status, result = self.call("/api/reset", b"", {"X-Requested-With": "sales-recap"})
        self.assertEqual((status, result["moved"]), (200, 1))
        self.assertEqual(len(list((app.UPLOAD_DIR / "archive").glob("*.csv"))), 1)
        _, report = self.call("/api/report")
        self.assertTrue(report["is_sample"])

    def test_file_copied_into_the_folder_by_hand_is_detected(self):
        app.UPLOAD_DIR.mkdir(parents=True)
        (app.UPLOAD_DIR / "manual.csv").write_text(OCTOBER, encoding="utf-8")
        _, report = self.call("/api/report")
        self.assertEqual(report["file"], "manual.csv")

    def test_upload_without_the_app_header_is_refused(self):
        status, result = self.call("/api/upload", OCTOBER.encode("utf-8"), {"X-Filename": "x.csv"})
        self.assertEqual(status, 403)
        self.assertFalse(result["ok"])

    def test_oversized_and_path_like_names_are_handled(self):
        status, _ = self.call("/api/upload", b"x" * (app.MAX_UPLOAD_BYTES + 1),
                              {"X-Requested-With": "sales-recap", "X-Filename": "big.csv"})
        self.assertEqual(status, 413)
        self.upload(OCTOBER, "..\\..\\evil.csv")
        saved = list(app.UPLOAD_DIR.glob("*.csv"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].parent, app.UPLOAD_DIR)


class OtherPeriodTests(unittest.TestCase):
    def write(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="")
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_one_month_file_uses_its_own_period_and_has_no_trend(self):
        report = sr.build_report(self.write(OCTOBER), sample=False)
        self.assertTrue(report["ok"])
        self.assertEqual((report["period"]["start"], report["period"]["end"]), ("2026-10-01", "2026-10-31"))
        self.assertTrue(report["months"]["single"])
        self.assertEqual(report["biggest_declines"], [])
        self.assertEqual(sum(r["net"] for r in report["by_region"]), report["total_net"])
        self.assertNotIn("dibanding", report["summary"])
        self.assertTrue(all(c["ok"] for c in report["checks"]))

    def test_same_file_as_sample_warns_that_it_is_incomplete(self):
        report = sr.build_report(self.write(OCTOBER), sample=True)
        self.assertTrue(any("tidak lengkap" in w for w in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
