"""Load the sales CSV, validate it, and compute everything the dashboard shows.

One function (`build_report`) produces every number on the page *and* the
Telegram paragraph, so the two can never disagree.
"""

import csv
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime

EXPECTED_COLUMNS = [
    "date", "invoice_no", "region", "branch", "outlet_id", "outlet_name",
    "outlet_type", "salesman", "brand", "sku", "qty_carton",
    "price_per_carton_idr", "gross_sales_idr", "discount_idr", "net_sales_idr",
]
REQUIRED_TEXT = ["invoice_no", "region", "outlet_id", "outlet_name", "brand"]

# The sample file the brief describes. A different file still loads, but the
# dashboard warns that it is not the expected dataset.
PERIOD_START = date(2026, 9, 1)
PERIOD_END = date(2026, 10, 31)
EXPECTED_ROWS = 1891

CANONICAL_REGIONS = [
    "Jabodetabek", "Jawa Barat", "Jawa Tengah", "Jawa Timur", "Sumatera", "Kalimantan",
]
REGION_ALIASES = {"jabar": "Jawa Barat"}

MONTHS_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember",
]

_INT_PLAIN = re.compile(r"^-?\d+$")
_INT_GROUPED = re.compile(r"^-?\d{1,3}([.,]\d{3})+$")


def parse_int(text):
    """'940500', '940,500', '940.500' and '-528,000' -> int. Anything else raises."""
    value = (text or "").strip().replace("Rp", "").replace(" ", "")
    if _INT_PLAIN.match(value):
        return int(value)
    if _INT_GROUPED.match(value):
        return int(value.replace(",", "").replace(".", ""))
    raise ValueError("not a whole number: %r" % text)


def parse_date(text):
    value = (text or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("not a date (expected YYYY-MM-DD): %r" % text)


def normalize_region(raw):
    """Trim, collapse spaces, map aliases, and fix letter case ('JAWA BARAT')."""
    cleaned = " ".join((raw or "").split())
    key = cleaned.casefold()
    if key in REGION_ALIASES:
        return REGION_ALIASES[key]
    for region in CANONICAL_REGIONS:
        if region.casefold() == key:
            return region
    return cleaned


def format_rupiah(amount):
    sign = "-" if amount < 0 else ""
    return "%sRp%s" % (sign, "{:,}".format(abs(amount)).replace(",", "."))


def format_number(n):
    return "{:,}".format(n).replace(",", ".")


def format_share(part, total):
    return ("%.1f" % (100.0 * part / total if total else 0.0)).replace(".", ",") + "%"


def format_change(pct):
    """+3,5% / -33,6%; 'baru' when there was nothing to compare against."""
    if pct is None:
        return "baru"
    return ("%+.1f" % pct).replace(".", ",") + "%"


def _month_pair(rows, first, last):
    """Net sales in the first and the last calendar month of the period."""
    a = sum(r["net_sales_idr"] for r in rows if (r["date"].year, r["date"].month) == first)
    b = sum(r["net_sales_idr"] for r in rows if (r["date"].year, r["date"].month) == last)
    if first == last:  # a one-month file has nothing to compare against
        return {"first": b, "last": b, "change": 0, "change_pct": None}
    return {"first": a, "last": b, "change": b - a,
            "change_pct": (100.0 * (b - a) / a) if a > 0 else None}


def format_date_id(d):
    return "%d %s %d" % (d.day, MONTHS_ID[d.month - 1], d.year)


def format_period(start, end):
    if start.year == end.year:
        return "%d %s–%s" % (start.day, MONTHS_ID[start.month - 1], format_date_id(end))
    return "%s–%s" % (format_date_id(start), format_date_id(end))


def load_rows(path):
    """Return (rows, errors). Rows keep the raw values next to the cleaned ones.

    Any error means the file cannot be trusted, and no totals are calculated.
    """
    errors = []
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            text = handle.read()
    except OSError as exc:
        return [], ["Cannot read %s: %s" % (path, exc)]

    lines = text.splitlines()
    # The artifact page shows the data as a tab-separated table with some text
    # above it, so start at the header row wherever it is.
    start = next((i for i, line in enumerate(lines)
                  if re.match(r"\s*date\s*[,\t]", line, re.IGNORECASE)), None)
    if start is None:
        return [], ["Header row not found. Expected columns: " + ", ".join(EXPECTED_COLUMNS)]
    delimiter = "\t" if "\t" in lines[start] else ","
    reader = csv.reader(lines[start:], delimiter=delimiter)
    header = [h.strip().lower() for h in next(reader)]
    missing = [c for c in EXPECTED_COLUMNS if c not in header]
    if missing:
        return [], ["Missing column(s): " + ", ".join(missing)]

    rows = []
    for offset, values in enumerate(reader, start=start + 2):
        if not any(v.strip() for v in values):
            continue
        if len(values) != len(header):
            errors.append("Line %d: expected %d values, found %d" % (offset, len(header), len(values)))
            continue
        raw = dict(zip(header, values))
        row = {"line": offset, "raw": raw}
        try:
            row["date"] = parse_date(raw["date"])
            for column in ("qty_carton", "price_per_carton_idr", "gross_sales_idr",
                           "discount_idr", "net_sales_idr"):
                row[column] = parse_int(raw[column])
            for column in REQUIRED_TEXT:
                if not raw[column].strip():
                    raise ValueError("%s is empty" % column)
        except ValueError as exc:
            errors.append("Line %d: %s" % (offset, exc))
            continue
        row["region"] = normalize_region(raw["region"])
        for column in ("invoice_no", "branch", "outlet_id", "outlet_name", "outlet_type",
                       "salesman", "brand", "sku"):
            row[column] = " ".join(raw[column].split())
        rows.append(row)

    if not rows and not errors:
        errors.append("The file has a header but no data rows.")
    return rows, errors


def _breakdown(rows, key, total, months):
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    items = [dict(name=name, net=sum(r["net_sales_idr"] for r in group), lines=len(group),
                  **_month_pair(group, *months))
             for name, group in groups.items()]
    for item in items:
        item["share"] = (100.0 * item["net"] / total) if total else 0.0
    return sorted(items, key=lambda item: (-item["net"], item["name"]))


def _most_common(values):
    return Counter(values).most_common(1)[0][0]


def _outlets(rows, months):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["outlet_id"]].append(row)
    outlets = []
    for outlet_id, items in grouped.items():
        outlets.append({
            "outlet_id": outlet_id,
            "outlet_name": _most_common(r["outlet_name"] for r in items),
            "region": _most_common(r["region"] for r in items),
            "branch": _most_common(r["branch"] for r in items),
            "outlet_type": _most_common(r["outlet_type"] for r in items),
            "net": sum(r["net_sales_idr"] for r in items),
            "lines": len(items),
            "invoices": len({r["invoice_no"] for r in items}),
            "last_order": max(r["date"] for r in items).isoformat(),
            **_month_pair(items, *months),
        })
    # Compare each outlet with the typical (median) outlet of the same type:
    # a small warung should not be judged against a grosir.
    by_type = defaultdict(list)
    for outlet in outlets:
        by_type[outlet["outlet_type"]].append(outlet["net"])
    for outlet in outlets:
        median = int(statistics.median(by_type[outlet["outlet_type"]]))
        outlet["peer_median"] = median
        outlet["peer_count"] = len(by_type[outlet["outlet_type"]])
        outlet["peer_pct"] = (100.0 * outlet["net"] / median) if median > 0 else None
    # Weakest first; outlet_id breaks ties so the ranking is deterministic.
    outlets.sort(key=lambda o: (o["net"], o["outlet_id"]))
    return outlets


def _summary(period_label, total, month_names, month_total, regions, brands, weakest, declines):
    """One paragraph for Telegram: the numbers first, then what to do about them."""
    top_region, top_brand, lowest = regions[0], brands[0], weakest[0]
    text = "Ringkasan penjualan %s: total net sales %s" % (period_label, format_rupiah(total))
    if month_total["change_pct"] is not None:
        text += " (%s %s dibanding %s)" % (month_names[1], format_change(month_total["change_pct"]), month_names[0])
    text += ". Region terbesar %s %s (%s); brand terbesar %s %s (%s)." % (
        top_region["name"], format_rupiah(top_region["net"]), format_share(top_region["net"], total),
        top_brand["name"], format_rupiah(top_brand["net"]), format_share(top_brand["net"], total))
    text += " Outlet dengan net sales terendah: %s (%s, %s) %s" % (
        lowest["outlet_name"], lowest["outlet_id"], lowest["region"], format_rupiah(lowest["net"]))
    if lowest["peer_pct"] is not None:
        text += ", hanya %s dari median %s" % (format_share(lowest["net"], lowest["peer_median"]),
                                               lowest["outlet_type"])
    if len(weakest) > 1:
        text += "; disusul " + ", ".join(o["outlet_id"] for o in weakest[1:])
    text += "."
    action = "Tindak lanjut: cek kunjungan salesman ke %d outlet terendah" % len(weakest)
    if declines:
        worst = declines[0]
        text += " Penurunan terbesar %s ke %s: %s (%s, %s) turun %s (%s)." % (
            month_names[0], month_names[1], worst["outlet_name"], worst["outlet_id"], worst["region"],
            format_rupiah(-worst["change"]), format_change(worst["change_pct"]))
        action += " dan cari penyebab penurunan di %s" % worst["outlet_name"]
    return text + " " + action + "."


def _duplicates(rows):
    """Lines that are identical in all 15 columns. Returns (extra lines, their net, labels)."""
    seen = Counter(tuple(r["raw"][c] for c in EXPECTED_COLUMNS) for r in rows)
    repeated = [(key, n) for key, n in seen.items() if n > 1]
    return (sum(n - 1 for _, n in repeated),
            sum((n - 1) * parse_int(key[-1]) for key, n in repeated),
            ["%s/%s ×%d" % (key[1], key[4], n) for key, n in repeated])


def _data_notes(rows):
    """Things a reviewer should know about the raw file. Nothing here is dropped."""
    notes = []
    changed = Counter(r["raw"]["region"] for r in rows if r["raw"]["region"] != r["region"])
    if changed:
        detail = ", ".join("“%s” → %s (%d baris)" % (raw, normalize_region(raw), n)
                           for raw, n in sorted(changed.items()))
        notes.append({"label": "Nama region dinormalisasi", "count": sum(changed.values()), "detail": detail})
    padded = [r for r in rows if r["raw"]["outlet_name"] != r["outlet_name"]]
    if padded:
        notes.append({"label": "Nama outlet dirapikan (spasi berlebih)", "count": len(padded),
                      "detail": "Baris CSV: " + ", ".join(str(r["line"]) for r in padded)})
    negative = [r for r in rows if r["net_sales_idr"] < 0]
    if negative:
        notes.append({"label": "Baris retur / net sales negatif (tetap dihitung, mengurangi total)",
                      "count": len(negative),
                      "detail": "; ".join("baris %d, %s, %s, %s" % (r["line"], r["invoice_no"], r["outlet_id"],
                                                                     format_rupiah(r["net_sales_idr"]))
                                          for r in negative)})
    extra, extra_net, labels = _duplicates(rows)
    if extra:
        notes.append({"label": "Baris kembar identik (tetap dihitung; total tanpa baris ini juga ditampilkan)",
                      "count": extra,
                      "detail": "%s; nilai baris tambahan %s" % (", ".join(labels), format_rupiah(extra_net))})
    blank = [r for r in rows if not r["salesman"]]
    if blank:
        notes.append({"label": "Kolom salesman kosong (tidak memengaruhi angka)", "count": len(blank),
                      "detail": "Baris CSV: " + ", ".join(str(r["line"]) for r in blank)})
    mismatch = [r for r in rows
                if r["qty_carton"] * r["price_per_carton_idr"] != r["gross_sales_idr"]
                or r["gross_sales_idr"] - r["discount_idr"] != r["net_sales_idr"]]
    notes.append({"label": "Baris dengan qty × harga ≠ gross, atau gross − diskon ≠ net",
                  "count": len(mismatch),
                  "detail": ("Baris CSV: " + ", ".join(str(r["line"]) for r in mismatch)) if mismatch
                  else "Semua baris konsisten."})
    return notes


def build_report(path, sample=True):
    """Compute the whole report.

    sample=True is the bundled test file: it must match the brief (1,891 rows,
    1 Sep - 31 Oct 2026) or the page warns. sample=False is a file the user
    supplied: the period is whatever dates the file covers.
    """
    all_rows, errors = load_rows(path)
    report = {"ok": not errors, "errors": errors, "warnings": [], "file": str(path)}
    if errors:
        report["errors"] = errors[:20] + (["… and %d more" % (len(errors) - 20)] if len(errors) > 20 else [])
        return report

    date_min = min(r["date"] for r in all_rows)
    date_max = max(r["date"] for r in all_rows)
    start, end = (PERIOD_START, PERIOD_END) if sample else (date_min, date_max)
    rows = [r for r in all_rows if start <= r["date"] <= end]
    if not rows:
        report["ok"] = False
        report["errors"] = ["No rows fall inside %s to %s." % (start, end)]
        return report
    if sample:
        outside = len(all_rows) - len(rows)
        if outside:
            report["warnings"].append("%d baris di luar periode %s tidak dihitung."
                                      % (outside, format_period(start, end)))
        if len(all_rows) != EXPECTED_ROWS:
            report["warnings"].append("File berisi %s baris, sedangkan dataset contoh seharusnya %s baris. "
                                      "Data mungkin tidak lengkap."
                                      % (format_number(len(all_rows)), format_number(EXPECTED_ROWS)))
        if (date_min, date_max) != (start, end):
            report["warnings"].append("Rentang tanggal di file adalah %s s.d. %s, bukan %s s.d. %s."
                                      % (date_min, date_max, start, end))
        unknown = sorted({r["region"] for r in rows} - set(CANONICAL_REGIONS))
        if unknown:
            report["warnings"].append("Region tidak dikenal (ditampilkan apa adanya): " + ", ".join(unknown))

    total = sum(r["net_sales_idr"] for r in rows)
    months = ((start.year, start.month), (end.year, end.month))
    month_names = [MONTHS_ID[months[0][1] - 1], MONTHS_ID[months[1][1] - 1]]
    month_total = _month_pair(rows, *months)
    regions = _breakdown(rows, "region", total, months)
    brands = _breakdown(rows, "brand", total, months)
    outlets = _outlets(rows, months)
    weakest = [dict(o, rank=i + 1) for i, o in enumerate(outlets[:5])]
    # Second signal: where the most rupiah was lost between the two months.
    # Ranked by rupiah (not %), so a big grosir slipping outranks a tiny outlet halving.
    falling = sorted((o for o in outlets if o["first"] > 0 and o["change"] < 0),
                     key=lambda o: (o["change"], o["outlet_id"]))
    declines = [dict(o, rank=i + 1) for i, o in enumerate(falling[:5])]
    dup_lines, dup_net, _ = _duplicates(rows)
    period_label = format_period(start, end)

    region_sum = sum(r["net"] for r in regions)
    brand_sum = sum(b["net"] for b in brands)
    outlet_sum = sum(o["net"] for o in outlets)
    checks = [
        {"label": "Jumlah semua region = total", "ok": region_sum == total, "detail": format_rupiah(region_sum)},
        {"label": "Jumlah semua brand = total", "ok": brand_sum == total, "detail": format_rupiah(brand_sum)},
        {"label": "Jumlah semua outlet = total", "ok": outlet_sum == total, "detail": format_rupiah(outlet_sum)},
        {"label": "5 outlet terendah punya ID berbeda",
         "ok": len({o["outlet_id"] for o in weakest}) == len(weakest),
         "detail": ", ".join(o["outlet_id"] for o in weakest)},
        {"label": "Jumlah baris & rentang tanggal sesuai dataset contoh" if sample
                  else "Semua baris terbaca tanpa error",
         "ok": (not sample) or (len(all_rows) == EXPECTED_ROWS and (date_min, date_max) == (start, end)),
         "detail": "%s baris, %s s.d. %s" % (format_number(len(all_rows)), date_min, date_max)},
    ]

    raw_regions = Counter(r["raw"]["region"] for r in rows)
    report.update({
        "period": {"start": start.isoformat(), "end": end.isoformat(), "label": period_label},
        "source": {"is_sample": sample, "rows_read": len(all_rows), "rows_counted": len(rows),
                   "date_min": date_min.isoformat(), "date_max": date_max.isoformat(),
                   "invoices": len({r["invoice_no"] for r in rows}), "outlets": len(outlets)},
        "total_net": total,
        "total_net_formatted": format_rupiah(total),
        "by_region": regions,
        "by_brand": brands,
        "weakest_outlets": weakest,
        "months": {"names": month_names, "total": month_total, "single": months[0] == months[1]},
        "duplicates": {"lines": dup_lines, "net": dup_net, "total_without": total - dup_net},
        "biggest_declines": declines,
        "summary": _summary(period_label, total, month_names, month_total, regions, brands, weakest, declines),
        "checks": checks,
        "data_notes": _data_notes(rows),
        "raw_region_values": [{"raw": raw, "normalized": normalize_region(raw), "lines": n}
                              for raw, n in sorted(raw_regions.items(), key=lambda item: (-item[1], item[0]))],
    })
    return report
