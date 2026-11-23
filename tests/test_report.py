"""Run from the project folder:  python -m unittest discover -s tests -v"""

import csv
import os
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sales_report as sr  # noqa: E402

CSV = ROOT / "data" / "sales.csv"


def write_temp(text):
    handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="")
    handle.write(text)
    handle.close()
    return handle.name


class ParsingTests(unittest.TestCase):
    def test_parse_int_accepts_grouped_values(self):
        self.assertEqual(sr.parse_int("940500"), 940500)
        self.assertEqual(sr.parse_int("940,500"), 940500)
        self.assertEqual(sr.parse_int("1.728.036.900"), 1728036900)
        self.assertEqual(sr.parse_int("-528,000"), -528000)

    def test_parse_int_rejects_garbage(self):
        for bad in ["", "abc", "12.5", "1,23", "9 40 x"]:
            with self.assertRaises(ValueError):
                sr.parse_int(bad)

    def test_region_normalization(self):
        self.assertEqual(sr.normalize_region("Jabar"), "Jawa Barat")
        self.assertEqual(sr.normalize_region("JAWA BARAT"), "Jawa Barat")
        self.assertEqual(sr.normalize_region(" jabodetabek "), "Jabodetabek")
        self.assertEqual(sr.normalize_region("Sulawesi"), "Sulawesi")

    def test_rupiah_format(self):
        self.assertEqual(sr.format_rupiah(1728036900), "Rp1.728.036.900")
        self.assertEqual(sr.format_rupiah(-528000), "-Rp528.000")

    def test_tab_separated_paste_with_grouped_numbers(self):
        header = "\t".join(sr.EXPECTED_COLUMNS)
        line = "\t".join(["2026-09-01", "INV1", "Jabar", "Bandung", "OUT1", "Toko A", "Grosir", "Andi",
                          "Sukro", "Sukro Pedas 100g", "5", "198,000", "990,000", "49,500", "940,500"])
        path = write_temp("Sample data\n" + header + "\n" + line + "\n")
        try:
            rows, errors = sr.load_rows(path)
        finally:
            os.unlink(path)
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["net_sales_idr"], 940500)
        self.assertEqual(rows[0]["region"], "Jawa Barat")
        self.assertEqual(rows[0]["raw"]["region"], "Jabar")

    def test_unparseable_value_is_an_error_not_a_silent_zero(self):
        header = ",".join(sr.EXPECTED_COLUMNS)
        line = "2026-09-01,INV1,Jabar,Bandung,OUT1,Toko A,Grosir,Andi,Sukro,Sukro Pedas 100g,5,198000,990000,0,n/a"
        path = write_temp(header + "\n" + line + "\n")
        try:
            report = sr.build_report(path)
        finally:
            os.unlink(path)
        self.assertFalse(report["ok"])
        self.assertIn("Line 2", report["errors"][0])
        self.assertNotIn("total_net", report)

    def test_missing_column_is_an_error(self):
        path = write_temp("date,invoice_no,region\n2026-09-01,INV1,Jabar\n")
        try:
            report = sr.build_report(path)
        finally:
            os.unlink(path)
        self.assertFalse(report["ok"])
        self.assertIn("Missing column", report["errors"][0])

    def test_incomplete_file_warns(self):
        with open(CSV, encoding="utf-8-sig") as handle:
            head = "".join(handle.readlines()[:101])
        path = write_temp(head)
        try:
            report = sr.build_report(path)
        finally:
            os.unlink(path)
        self.assertTrue(report["ok"])
        self.assertTrue(any("tidak lengkap" in w for w in report["warnings"]))


class SampleDataTests(unittest.TestCase):
    """The report must agree with an independent, naive recount of the CSV."""

    @classmethod
    def setUpClass(cls):
        cls.report = sr.build_report(CSV)
        with open(CSV, encoding="utf-8-sig", newline="") as handle:
            cls.raw = list(csv.DictReader(handle))

    def test_row_count_and_date_range(self):
        r = self.report
        self.assertTrue(r["ok"], r.get("errors"))
        self.assertEqual(r["warnings"], [])
        self.assertEqual(r["source"]["rows_read"], 1891)
        self.assertEqual(r["source"]["rows_counted"], 1891)
        self.assertEqual((r["source"]["date_min"], r["source"]["date_max"]), ("2026-09-01", "2026-10-31"))

    def test_grand_total_matches_raw_sum(self):
        self.assertEqual(self.report["total_net"], sum(int(row["net_sales_idr"]) for row in self.raw))
        self.assertEqual(self.report["total_net"], 1728036900)

    def test_breakdowns_add_up_and_are_sorted(self):
        for key in ("by_region", "by_brand"):
            items = self.report[key]
            self.assertEqual(sum(i["net"] for i in items), self.report["total_net"])
            self.assertEqual(sum(i["lines"] for i in items), 1891)
            self.assertEqual([i["net"] for i in items], sorted((i["net"] for i in items), reverse=True))

    def test_regions_are_the_six_canonical_ones(self):
        self.assertEqual(sorted(i["name"] for i in self.report["by_region"]), sorted(sr.CANONICAL_REGIONS))

    def test_jawa_barat_includes_jabar_and_uppercase_rows(self):
        expected = sum(int(row["net_sales_idr"]) for row in self.raw
                       if row["region"].strip().lower() in ("jawa barat", "jabar"))
        actual = next(i for i in self.report["by_region"] if i["name"] == "Jawa Barat")
        self.assertEqual(actual["net"], expected)

    def test_bottom_five_matches_independent_ranking(self):
        totals = defaultdict(int)
        for row in self.raw:
            totals[row["outlet_id"]] += int(row["net_sales_idr"])
        expected = sorted(totals.items(), key=lambda item: (item[1], item[0]))[:5]
        actual = [(o["outlet_id"], o["net"]) for o in self.report["weakest_outlets"]]
        self.assertEqual(actual, expected)
        self.assertEqual(len({o["outlet_id"] for o in self.report["weakest_outlets"]}), 5)
        self.assertEqual([o["rank"] for o in self.report["weakest_outlets"]], [1, 2, 3, 4, 5])

    def test_all_checks_pass(self):
        self.assertTrue(all(c["ok"] for c in self.report["checks"]), self.report["checks"])

    def test_summary_uses_the_dashboard_figures(self):
        r, text = self.report, self.report["summary"]
        lowest = r["weakest_outlets"][0]
        for expected in [
            r["period"]["label"], sr.format_rupiah(r["total_net"]),
            r["by_region"][0]["name"], sr.format_rupiah(r["by_region"][0]["net"]),
            r["by_brand"][0]["name"], sr.format_rupiah(r["by_brand"][0]["net"]),
            lowest["outlet_name"], lowest["outlet_id"], sr.format_rupiah(lowest["net"]),
        ]:
            self.assertIn(expected, text)
        self.assertNotIn("\n", text)

    def test_month_split_adds_up_everywhere(self):
        r = self.report
        self.assertEqual(r["months"]["names"], ["September", "Oktober"])
        self.assertEqual(r["months"]["total"]["first"] + r["months"]["total"]["last"], r["total_net"])
        sep = sum(int(row["net_sales_idr"]) for row in self.raw if row["date"].startswith("2026-09"))
        self.assertEqual(r["months"]["total"]["first"], sep)
        for key in ("by_region", "by_brand"):
            for item in r[key]:
                self.assertEqual(item["first"] + item["last"], item["net"])

    def test_total_without_duplicate_lines(self):
        seen, extra = set(), 0
        for row in self.raw:
            key = tuple(row.values())
            if key in seen:
                extra += int(row["net_sales_idr"])
            seen.add(key)
        d = self.report["duplicates"]
        self.assertEqual((d["lines"], d["net"]), (3, extra))
        self.assertEqual(d["total_without"], self.report["total_net"] - extra)

    def test_biggest_declines_match_independent_ranking(self):
        months = defaultdict(lambda: [0, 0])
        for row in self.raw:
            months[row["outlet_id"]][0 if row["date"].startswith("2026-09") else 1] += int(row["net_sales_idr"])
        drops = sorted(((b - a, oid) for oid, (a, b) in months.items() if a > 0 and b < a))[:5]
        actual = [(o["change"], o["outlet_id"]) for o in self.report["biggest_declines"]]
        self.assertEqual(actual, drops)
        self.assertTrue(all(o["change"] < 0 for o in self.report["biggest_declines"]))

    def test_peer_median_uses_same_outlet_type(self):
        import statistics
        totals, kind = defaultdict(int), {}
        for row in self.raw:
            totals[row["outlet_id"]] += int(row["net_sales_idr"])
            kind[row["outlet_id"]] = row["outlet_type"]
        for outlet in self.report["weakest_outlets"]:
            peers = [v for oid, v in totals.items() if kind[oid] == outlet["outlet_type"]]
            self.assertEqual(outlet["peer_median"], int(statistics.median(peers)))

    def test_summary_names_the_biggest_decline_and_an_action(self):
        worst, text = self.report["biggest_declines"][0], self.report["summary"]
        self.assertIn(worst["outlet_id"], text)
        self.assertIn(sr.format_rupiah(-worst["change"]), text)
        self.assertIn("Tindak lanjut", text)


if __name__ == "__main__":
    unittest.main()
