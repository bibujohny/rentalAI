from __future__ import annotations
import logging
from typing import List, Dict, Optional
from dateutil import parser as dateparser

try:
    import pdfplumber
except Exception:  # pragma: no cover
    pdfplumber = None

logger = logging.getLogger(__name__)

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
        logger.debug("Opening HDFC PDF path=%s", path)
        with pdfplumber.open(path, password=password) as pdf:
            for page_number, page in enumerate(pdf.pages):
                tables = page.extract_tables(table_settings=table_settings) or []
                logger.debug("Page %s extracted %s tables", page_number, len(tables))
                for tbl in tables:
                    if not tbl or len(tbl[0]) < 6:
                        logger.debug("Skipping table with insufficient columns on page %s", page_number)
                        continue
                    data_rows = tbl[1:] if "date" in (str(tbl[0][0]).lower()) else tbl
                    logger.debug("Processing table on page %s with %s data rows", page_number, len(data_rows))
                    pending_deposits: List[float] = []
                    for raw in data_rows:
                        padded = list(raw) + [""] * (6 - len(raw))
                        date_vals = str(padded[0] or "").splitlines()
                        narration_vals = str(padded[1] or "").splitlines()
                        withdrawal_vals = str(padded[4] or "").splitlines()
                        deposit_vals_raw = str(padded[5] or "").splitlines()

                        max_len = max(
                            len(date_vals) or 1,
                            len(narration_vals) or 1,
                            len(withdrawal_vals) or 0,
                            len(deposit_vals_raw) or 0,
                        )

                        deposit_vals = [''] * max_len
                        start = max_len - len(deposit_vals_raw)
                        if start < 0:
                            start = 0
                        for offset, val in enumerate(deposit_vals_raw[-max_len:]):
                            deposit_vals[start + offset] = val

                        for idx in range(max_len):
                            date_cell = date_vals[idx] if idx < len(date_vals) else ""
                            narration_cell = narration_vals[idx] if idx < len(narration_vals) else ""
                            withdrawal_cell = withdrawal_vals[idx] if idx < len(withdrawal_vals) else ""
                            deposit_cell = deposit_vals[idx]

                            narration_raw_lines = [line.strip() for line in str(narration_cell).splitlines() if line.strip()]
                            narration = " ".join(narration_raw_lines)
                            if not narration:
                                continue
                            low = narration.lower()
                            if any(tok in low for tok in SUMMARY_KEYWORDS):
                                logger.debug("Skipping summary row narration=%s", narration)
                                continue

                            current_date = _parse_date(date_cell, last_date)
                            if not current_date:
                                logger.debug("Unable to parse date date_cell=%s last_date=%s", date_cell, last_date)
                                continue
                            last_date = current_date

                            withdrawal_amt = round(_parse_float(withdrawal_cell), 2)
                            deposit_amt = round(_parse_float(deposit_cell), 2)
                            if deposit_amt and withdrawal_amt:
                                pending_deposits.append(deposit_amt)
                                deposit_amt = 0.0
                            if not deposit_amt and pending_deposits and withdrawal_amt == 0.0:
                                deposit_amt = pending_deposits.pop(0)

                            rows.append(
                                {
                                    "date": current_date,
                                    "narration": narration,
                                    "withdrawal": withdrawal_amt,
                                    "deposit": deposit_amt,
                                }
                            )
    except Exception as exc:
        logger.exception("Failed to parse HDFC PDF path=%s error=%s", path, exc)
        return rows

    logger.info("HDFC YTD parser produced %s rows for %s", len(rows), path)
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
