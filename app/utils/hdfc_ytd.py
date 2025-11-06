from __future__ import annotations
import logging
from typing import List, Dict, Optional
from dateutil import parser as dateparser
import re

try:
    import pdfplumber
except Exception:  # pragma: no cover
    pdfplumber = None

logger = logging.getLogger(__name__)

SUMMARY_KEYWORDS = ("closing balance", "opening balance", "total")
SUMMARY_LINE_KEYWORDS = (
    "closingbalanceincludes",
    "contentsofthisstatement",
    "hdfcbanklimited",
    "stateaccountbranch",
    "registeredofficeaddress",
    "thisstatement",
    "hdfcbankgstinnumber",
    "statement from",
    "account branch",
    "account type",
    "page no",
    "statementofaccount",
    "address :",
    "city :",
    "state :",
    "phone no",
    "email :",
    "cust id",
    "account no",
    "a/c open date",
    "account status",
    "rtgs/neft ifsc",
    "micr",
    "branch code",
    "nomination",
    "joint holders",
)


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
                    for raw in data_rows:
                        padded = list(raw) + [""] * (7 - len(raw))
                        date_vals = [s.strip() for s in str(padded[0] or "").splitlines() if s.strip()]
                        narration_vals = [s.strip() for s in str(padded[1] or "").splitlines() if s.strip()]
                        withdrawal_vals = [s.strip() for s in str(padded[4] or "").splitlines() if s.strip()]
                        deposit_vals = [s.strip() for s in str(padded[5] or "").splitlines() if s.strip()]

                        max_len = max(len(date_vals), len(narration_vals), len(withdrawal_vals), len(deposit_vals), 1)
                        for idx in range(max_len):
                            date_cell = date_vals[idx] if idx < len(date_vals) else ""
                            narration_cell = narration_vals[idx] if idx < len(narration_vals) else ""
                            withdrawal_cell = withdrawal_vals[idx] if idx < len(withdrawal_vals) else ""
                            deposit_cell = deposit_vals[idx] if idx < len(deposit_vals) else ""

                            narration_lower = narration_cell.lower()
                            if any(tok in narration_lower for tok in SUMMARY_LINE_KEYWORDS):
                                continue

                            current_date = _parse_date(date_cell, last_date)
                            if not current_date:
                                continue
                            last_date = current_date

                            withdrawal_amt = round(_parse_float(withdrawal_cell), 2)
                            deposit_amt = round(_parse_float(deposit_cell), 2)

                            rows.append(
                                {
                                    "date": current_date,
                                    "narration": narration_cell,
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
