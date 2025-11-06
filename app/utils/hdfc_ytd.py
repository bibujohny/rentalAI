from __future__ import annotations
from typing import List, Dict, Optional
from dateutil import parser as dateparser

try:
    import pdfplumber
except Exception:  # pragma: no cover
    pdfplumber = None

SUMMARY_KEYWORDS = ("closing balance", "opening balance", "total")


def _parse_float(value: Optional[str]) -> float:
    if not value:
        return 0.0
    s = str(value).strip()
    if not s:
        return 0.0
    s = (
        s.replace("INR", "")
        .replace("Rs", "")
        .replace("rs", "")
        .replace("₹", "")
        .replace(",", "")
    )
    try:
        return float(s)
    except Exception:
        return 0.0


def _parse_date(value: Optional[str], fallback: Optional[str]) -> Optional[str]:
    candidate = value.strip() if value else ""
    if not candidate:
        candidate = fallback or ""
    if not candidate:
        return None
    try:
        dt = dateparser.parse(candidate, dayfirst=True, fuzzy=True)
        if dt:
            return dt.date().isoformat()
    except Exception:
        return fallback
    return fallback


def parse_hdfc_ytd(path: str, password: Optional[str] = None) -> List[Dict]:
    """Parse an HDFC statement PDF and return transaction rows."""
    if pdfplumber is None:
        return []

    rows: List[Dict] = []
    last_date: Optional[str] = None

    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 3,
        "join_tolerance": 3,
        "intersection_y_tolerance": 3,
    }

    try:
        with pdfplumber.open(path, password=password) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables(table_settings=table_settings) or []
                for tbl in tables:
                    if not tbl or len(tbl[0]) < 6:
                        continue
                    data_rows = tbl[1:] if "date" in (str(tbl[0][0]).lower()) else tbl
                    for raw in data_rows:
                        # Ensure we have at least 6 columns (date, narration, ..., withdrawal, deposit)
                        padded = list(raw) + [""] * (6 - len(raw))
                        date_cell = padded[0] or ""
                        narration_cell = padded[1] or ""
                        withdrawal_cell = padded[4] or ""
                        deposit_cell = padded[5] or ""

                        narration_lines = [line.strip() for line in str(narration_cell).splitlines() if line.strip()]
                        narration = " ".join(narration_lines)
                        if not narration:
                            continue
                        low = narration.lower()
                        if any(tok in low for tok in SUMMARY_KEYWORDS):
                            continue

                        current_date = _parse_date(date_cell, last_date)
                        if not current_date:
                            continue
                        last_date = current_date

                        rows.append(
                            {
                                "date": current_date,
                                "narration": narration,
                                "withdrawal": round(_parse_float(withdrawal_cell), 2),
                                "deposit": round(_parse_float(deposit_cell), 2),
                            }
                        )
    except Exception:
        return rows
    return rows


def compute_ytd_totals(rows: List[Dict]) -> List[Dict]:
    bucket: Dict[int, Dict[str, float]] = {}
    for row in rows or []:
        date_str = row.get("date")
        if not date_str:
            continue
        try:
            year = int(date_str.split("-")[0])
        except Exception:
            continue
        info = bucket.setdefault(
            year,
            {
                "income_total": 0.0,
                "expense_total": 0.0,
                "income_entries": 0,
                "expense_entries": 0,
            },
        )
        deposit = float(row.get("deposit") or 0.0)
        withdrawal = float(row.get("withdrawal") or 0.0)
        if deposit:
            info["income_total"] += deposit
            info["income_entries"] += 1
        if withdrawal:
            info["expense_total"] += withdrawal
            info["expense_entries"] += 1

    results = []
    for year, info in sorted(bucket.items(), key=lambda x: x[0], reverse=True):
        info["net"] = round(info["income_total"] - info["expense_total"], 2)
        results.append({"year": year, **info})
    return results
