# Dua Kelinci – Sales Dashboard (AI Builder build test)

A one-page sales recap for a sales manager, built on the September–October 2026 sample data.
It is laid out like a ledger sheet: dense tables, exact rupiah, and every total shown as a sum you can check.

It shows:

- total net sales for the period,
- net sales by **region** and by **brand**, highest first, with exact rupiah totals,
- the **5 outlets with the lowest net sales**, each compared with the typical outlet of its own type,
- the **5 biggest September → October declines**, a second view of "which outlets need a closer look",
- a one-paragraph summary in Bahasa Indonesia with a copy button, ready to paste into Telegram.

Every number on the page and the Telegram paragraph come from the same function
(`build_report` in `sales_report.py`), so they cannot disagree.

## Run it

Prerequisite: **Python 3.9 or newer**. Nothing to install: no packages, accounts, or API keys.

```bash
cd dua-kelinci-sales-dashboard
python app.py
```

Then open **http://localhost:8000**. (On macOS/Linux use `python3` if `python` is not found.)

- Another port: `python app.py 8080`
- Stop: `Ctrl+C`

The page loads the Manrope font from Google Fonts when online; offline it falls back to system fonts.

## The data file

Nothing to set up: the sample file (`data/sales.csv`, 1,891 rows, 15 columns) is bundled and shown on first run.

To look at another file, click **Ganti data (CSV)** at the top of the page and pick it.

- The file is checked first. If a column is missing or a value cannot be read, it is rejected with the line
  numbers, and the data already on screen stays as it was.
- An accepted file is saved in `data/uploads/` and shown at once. The "Sumber" line at the top names the file in use.
- **Kembali ke data contoh** switches back to the bundled sample. Uploaded files are moved to
  `data/uploads/archive/`, not deleted.
- Copying a `.csv` into `data/uploads/` by hand works too: the newest file there is used after a refresh.
- For your own file the period is whatever dates the file covers, and the trend compares its first and last
  calendar month. A one-month file shows totals and rankings without the month columns.

Both formats from the job page work: the downloaded comma-separated CSV, and the table copied
as tab-separated text (values such as `940,500` are read as whole rupiah; text above the header row is skipped).
Files up to 5 MB are accepted. The server listens on this computer only (127.0.0.1).

For scripts, `SALES_CSV=/path/to/file.csv python app.py` still overrides everything.

## Calculation rules

| Rule | What the app does |
|---|---|
| Source of truth | `net_sales_idr`. Gross, discount, qty and price are only cross-checked. |
| What is counted | Every product line. Lines sharing an `invoice_no` are all counted. |
| Period | Bundled sample: 1 September – 31 October 2026, and the page warns if the file does not match that. Uploaded file: the dates the file covers. |
| Region names | Trimmed, then `Jabar` → `Jawa Barat`, and letter case fixed (`JAWA BARAT`, `JABODETABEK`, `JAWA TIMUR` → normal spelling). 10 rows change; no row is dropped. An unknown region is shown as-is with a warning. |
| Weakest 5 outlets | Sum `net_sales_idr` per `outlet_id` over the full period, rank lowest to highest, ties broken by `outlet_id`. Grouping is by ID because 8 outlet names are shared by more than one outlet. |
| Outlet name / region shown | The most frequent trimmed value for that `outlet_id` (4 rows have a trailing space in the name). |
| "vs median setipe" | The outlet's net sales as a % of the median outlet with the same `outlet_type`, so a warung is compared with warungs, not with a grosir. |
| Month trend | Net sales in September vs October, shown for the total, each region, each brand and each outlet. |
| Biggest declines | Outlets that sold in September and sold less in October, ranked by rupiah lost (not %), ties by `outlet_id`. An outlet with no September sales is not ranked. |
| Sort order of breakdowns | Net sales, highest first; ties by name. |

### Things in the raw file that are kept, not "fixed"

These are listed on the page under **Catatan kualitas data**, with CSV line numbers:

- **1 return line** (`RTR900001`, OUT1049, −Rp528.000). It is counted, so totals are net of returns.
- **3 exact duplicate lines** (INV500201, INV500386, INV500791; Rp2.070.900 in total). They are counted,
  following the rule "count every product line", and the page also shows the total without them
  (Rp1.725.966.000) so the reader sees both. Removing them would not change the weakest-5 ranking.
- **5 lines with no salesman.** Salesman is not used in any figure.

The original values stay available: the page links to the raw CSV (`/sales.csv`) and to the full
calculation as JSON (`/api/report`), and shows each raw region spelling with the name it was counted under.

### When the data is wrong

- A missing column, an unreadable number or date, or an empty required field **stops the calculation**.
  The page shows a red box with the line numbers instead of totals.
- A row count other than 1,891, or a date range other than 2026-09-01 to 2026-10-31, shows a yellow
  warning ("data may be incomplete") and still calculates.

## Decisions I made, and why

- **"Weakest" has two meanings, so the page shows both.** The brief asks for the 5 weakest outlets, and lowest
  net sales is the plain reading, so that ranking is kept exactly as asked. But those five outlets together sold
  only Rp4.908.000 in two months, and four of the five grew in October. The outlets a manager can lose real money
  on are the large ones that are slipping: the five biggest declines lost Rp80.775.600 between September and
  October, led by Grosir Sentosa (OUT1014, −Rp32.657.200, −33.6%). The second table makes that visible.
- **The Telegram paragraph is written by code, not by an LLM.** It must match the dashboard to the rupiah, and the
  app must run on your machine with no API key. A template guarantees both. It ends with a concrete next step.
- **A work tool, not a marketing page.** Green carries the structure (table heads, rules); red appears only on
  numbers that need attention (declines, the lowest outlets). No cards, gradients, icons or animation. The
  double rule above each total is the accounting convention for "this is a sum".
- **No framework, no build step.** One Python file for the numbers, one HTML file for the page. It is small
  enough to read in ten minutes and to change during a live session.
- **Bad data stops the page; odd data is shown.** A value that cannot be parsed blocks all totals. Returns,
  duplicates and blank salesmen are counted as they are and listed, because deciding what they mean is a business call.

## What I would ask the sales manager

1. Are the 3 identical lines real repeat orders or double entries? It changes the total by Rp2.070.900.
2. Should "weakest" be judged against a target or a visit plan? The data has neither, so the app uses peers and trend.
3. Jawa Timur grew 92% from September to October. Is that real growth, a new salesman, or late September invoices?
4. Is two months enough to call an outlet weak, or are some of these simply new or seasonal?

## Results on the sample data

- Total net sales: **Rp1.728.036.900** (1,891 lines, 824 invoice numbers, 52 outlets)
- Top region: Jabodetabek, Rp495.827.800 (28.7%)
- Top brand: Kacang Dua Kelinci, Rp740.084.500 (42.8%)
- Weakest 5: OUT1003 Toko Sinar Abadi Rp564.000 · OUT1026 Toko Mulia Rp834.000 ·
  OUT1035 Warung Maju Lancar Rp1.122.000 · OUT1045 Toko Anugerah Rp1.158.000 · OUT1042 Toko Mandiri Rp1.230.000
  (all below 10% of the median outlet of their type)
- September Rp849.285.700 → October Rp878.751.200 (+3.5%)
- Biggest declines: OUT1014 Grosir Sentosa −Rp32.657.200 · OUT1025 Grosir Sumber Alam −Rp24.288.400 ·
  OUT1050 Grosir Sinar Abadi −Rp10.936.700 · OUT1041 Toko Anugerah −Rp6.585.300 · OUT1043 Minimarket Sido Muncul −Rp6.308.000

## Checks I ran

```bash
python -m unittest discover -s tests -v
```

30 tests, all passing (Python 3.14, Windows 11). They cover:

- row count is 1,891 and dates run 2026-09-01 to 2026-10-31;
- the grand total equals a separate plain sum of `net_sales_idr` from the raw CSV;
- region totals and brand totals each add up to the grand total and are sorted highest first;
- only the six real regions remain, and Jawa Barat includes the `Jabar` / `JAWA BARAT` rows;
- the weakest 5 match a separate ranking from the raw CSV and have five distinct outlet IDs;
- the Telegram paragraph contains the same period, total, top region, top brand and weakest outlet figures,
  plus the biggest decline and a next step;
- September + October equals the total for the whole file and for every region and brand;
- the biggest declines, the peer medians and the total without duplicates match separate recounts from the raw CSV;
- tab-separated input with `940,500`-style numbers parses; a bad value or missing column is reported as an error;
- upload against a real local server: a valid file becomes the active one, a broken file is rejected and leaves
  nothing behind, reset returns to the sample without deleting the upload, a file copied into `data/uploads/`
  is detected, an oversized file and a request from another site are refused, and a path-like file name
  cannot escape the folder;
- a one-month file uses its own period and reports no trend.

In the browser, started with `python app.py`: the page showed the figures above; the "Jumlah" row of both the
region and the brand table read Rp849.285.700 + Rp878.751.200 = Rp1.728.036.900; both outlet tables matched the
figures above; the five automatic checks read "Cocok"; no console errors. At 1440 px no table needs sideways
scrolling; at 375 px the page itself does not scroll sideways and the wide tables scroll inside their own box.
The copy button showed "Tersalin"; I did not paste into Telegram itself. Both footer links and the logo returned 200.
With a deliberately broken CSV (one `n/a` in `net_sales_idr`) the page showed the red error box with the line
number and no totals.

"Ganti data", in the browser: a broken file showed "ditolak, data sebelumnya tetap dipakai" and the totals did
not change; an October-only file switched the page to 1 Oktober s.d. 31 Oktober 2026 with Rp878.751.200 and no
month columns; "Kembali ke data contoh" brought back Rp1.728.036.900. The file was handed to the page by script,
because the automated browser cannot operate the operating system's file picker; I did not click through that dialog.

Not tested: macOS/Linux, and Python versions older than 3.14 (the code avoids newer syntax and should run on 3.9+).

## Files

```
app.py              local web server (standard library): pages, upload, auto-detect, reset
sales_report.py     loading, validation, normalization, totals, ranking, Telegram paragraph
static/index.html   the page (Dua Kelinci green #004532 for structure, red #C42226 for attention, Manrope)
static/logo.png     Dua Kelinci logo, taken from the job posting page
data/sales.csv      the sample data
data/uploads/       files added with "Ganti data" (created on first upload, not in Git)
tests/              unit tests
```
