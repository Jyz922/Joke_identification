"""Download Kuperman et al. (2012) AoA ratings to data/aoa_kuperman.csv.

Not committed to git (data/ is gitignored) — run this once per clone:

    py -3.11 scripts/fetch_aoa.py

Source: Ghent CRR "AoA_51715_words.zip". Its AoA_Kup column is the
Kuperman, Stadthagen-Gonzalez & Brysbaert (2012) rating for each SURFACE
word form (inflections like "banks"/"ran" have no AoA_Kup value). Only
Word + AoA_Kup are extracted. The original crr.ugent.be URL is dead (404 as
of 2026-09-24), so this pulls the Internet Archive capture of 2022-12-07 and
refuses anything whose sha256 differs from the pinned value.

Citation: Kuperman, V., Stadthagen-Gonzalez, H., & Brysbaert, M. (2012).
Age-of-acquisition ratings for 30,000 English words. Behavior Research
Methods, 44(4), 978-990.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

URL = (
    "https://web.archive.org/web/20221207143117id_/"
    "http://crr.ugent.be/papers/AoA_51715_words.zip"
)
SHA256 = "ce1c17a65d3b0b1130b6bcfda47a416b4f6625d187d1fe7d83e618453c3d4f89"
OUT = Path(__file__).resolve().parents[1] / "data" / "aoa_kuperman.csv"

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _xlsx_rows(xlsx: bytes):
    """Yield each row of the first sheet as {column_letter: str}. Stdlib only."""
    z = zipfile.ZipFile(io.BytesIO(xlsx))
    shared = [
        "".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t"))
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS)
    ]
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    for row in sheet.iter(f"{{{_NS['m']}}}row"):
        out = {}
        for c in row.findall("m:c", _NS):
            v = c.find("m:v", _NS)
            if v is None:
                continue
            col = re.match(r"[A-Z]+", c.get("r")).group(0)
            out[col] = shared[int(v.text)] if c.get("t") == "s" else v.text
        yield out


def main() -> None:
    blob = urllib.request.urlopen(URL, timeout=120).read()
    got = hashlib.sha256(blob).hexdigest()
    if got != SHA256:
        sys.exit(f"sha256 mismatch: expected {SHA256}, got {got}. Not writing.")
    xlsx = zipfile.ZipFile(io.BytesIO(blob)).read("AoA_51715_words.xlsx")
    rows = _xlsx_rows(xlsx)
    header = next(rows)
    col = {name: letter for letter, name in header.items()}
    word_c, aoa_c = col["Word"], col["AoA_Kup"]
    n = 0
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["word", "aoa"])
        for r in rows:
            word, aoa = r.get(word_c), r.get(aoa_c)
            if word is None or aoa is None:
                continue
            try:
                aoa_f = float(aoa)
            except ValueError:  # non-numeric cells (e.g. "NA") are unrated
                continue
            w.writerow([word, round(aoa_f, 4)])
            n += 1
    print(f"wrote {n} rated words to {OUT}")


if __name__ == "__main__":
    main()
