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
    "pageno",
    "address :",
    "address",
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
    "mr bibu",
    "tower 2 id",
    "link rd",
    "ernakulam",
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
            current_entry = None
            for page_number, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                logger.debug("Page %s extracted text length=%s", page_number, len(text))
                for raw_line in text.splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    match = re.match(r'^(\d{2}/\d{2}/\d{2})\s+(.*)$', line)
                    if match:
                        if current_entry:
                            rows.append(current_entry)
                        date_str_iso = _parse_date(match.group(1), last_date)
                        last_date = date_str_iso or last_date
                        rest = match.group(2).strip()
                        rest_lower = rest.lower()
                        if any(kw in rest_lower for kw in SUMMARY_LINE_KEYWORDS):
                            current_entry = None
                            continue

                        closing_match = re.search(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2}))\s*$', rest)
                        if closing_match:
                            rest = rest[:closing_match.start()].rstrip()

                        rest = re.sub(r'\s\d{6,}\b', ' ', rest)
                        rest = re.sub(r'\b\d{2}/\d{2}/\d{2}\b', ' ', rest, count=1)

                        numbers = re.findall(r'\d{1,3}(?:,\d{3})*(?:\.\d{2})', rest)
                        withdrawal_amt = deposit_amt = 0.0
                        if len(numbers) == 1:
                            withdrawal_amt = _parse_float(numbers[0])
                        elif len(numbers) >= 2:
                            withdrawal_amt = _parse_float(numbers[-2])
                            deposit_amt = _parse_float(numbers[-1])

                        narration = re.sub(r'\d{1,3}(?:,\d{3})*(?:\.\d{2})', ' ', rest)
                        narration = " ".join(narration.split())

                        current_entry = {
                            "date": date_str_iso,
                            "narration": narration,
                            "withdrawal": round(withdrawal_amt, 2),
                            "deposit": round(deposit_amt, 2),
                        }
                    else:
                        lower_line = line.lower()
                        if any(kw in lower_line for kw in SUMMARY_LINE_KEYWORDS):
                            continue
                        if current_entry:
                            current_entry["narration"] = (
                                current_entry["narration"] + " " + line
                            ).strip()
            if current_entry:
                rows.append(current_entry)
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
