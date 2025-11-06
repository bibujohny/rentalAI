from __future__ import annotations
import os
from typing import List, Dict, Optional
from dateutil import parser as dateparser

try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


def _parse_amount(cell: Optional[str]) -> Optional[float]:
    if not cell:
        return None
    s = str(cell).strip()
    if not s:
        return None
    # Remove currency, commas, extra annotations like 'Cr'/'Dr'
    s = s.replace('INR', '').replace('Rs', '').replace('rs', '').replace('₹', '')
    s = s.replace('Cr', '').replace('DR', '').replace('Dr', '').strip()
    s = s.replace(',', '')
    # Handle parentheses as negatives
    neg = s.startswith('(') and s.endswith(')')
    s = s.replace('(', '').replace(')', '')
    try:
        val = float(s)
        return -val if neg else val
    except Exception:
        return None


def _parse_date(cell: Optional[str]) -> Optional[str]:
    if not cell:
        return None
    s = str(cell).strip()
    if not s:
        return None
    try:
        dt = dateparser.parse(s, dayfirst=True, fuzzy=True)
        if dt:
            return dt.date().isoformat()
    except Exception:
        return None
    return None


def _clean_particulars(cell: Optional[str]) -> str:
    if not cell:
        return ''
    return ' '.join(str(cell).split())


SUMMARY_TOKENS = ("transaction total", "closing balance", "opening balance")


def _strip_summary_tokens(text: str) -> str:
    """Remove summary phrases (TRANSACTION TOTAL, CLOSING BALANCE, OPENING BALANCE) from particulars.
    Keeps content before the first summary token, trims whitespace."""
    if not text:
        return ""
    low = text.lower()
    cut = len(text)
    for tok in SUMMARY_TOKENS:
        idx = low.find(tok)
        if idx >= 0:
            cut = min(cut, idx)
    cleaned = text[:cut].strip()
    return ' '.join(cleaned.split())


def parse_axis_statement_from_tables(path: str, password: Optional[str] = None) -> List[Dict]:
    """Use pdfplumber to extract tables and parse Axis Bank transactions.
    Only uses column 0 (date), column 2 (particulars), column 3 (debit) and column 4 (credit).
    """
    if pdfplumber is None:
        return []
    out: List[Dict] = []
    last_row: Optional[Dict] = None
    last_date: Optional[str] = None

    try:
        with pdfplumber.open(path, password=password) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for tbl in tables:
                    if not tbl or len(tbl) < 1:
                        continue
                    data_rows = tbl[1:] if any('date' in (str(c).lower() if c else '') for c in tbl[0]) else tbl

                    for row in data_rows:
                        cells = [c if c is not None else '' for c in row]
                        if not any(str(x).strip() for x in cells):
                            continue

                        date_vals = str(cells[0]).splitlines()
                        part_vals = str(cells[2]).splitlines() if len(cells) > 2 else ['']
                        debit_vals = str(cells[3]).splitlines() if len(cells) > 3 else []
                        credit_vals = str(cells[4]).splitlines() if len(cells) > 4 else []

                        max_len = max(len(date_vals), len(part_vals), len(debit_vals) or 0, len(credit_vals) or 0, 1)

                        for i in range(max_len):
                            raw_date = date_vals[i] if i < len(date_vals) else ''
                            raw_part = part_vals[i] if i < len(part_vals) else ''
                            raw_debit = debit_vals[i] if i < len(debit_vals) else ''
                            raw_credit = credit_vals[i] if i < len(credit_vals) else ''

                            d_iso = _parse_date(raw_date) if raw_date else None
                            if d_iso:
                                last_date = d_iso
                            else:
                                d_iso = last_date

                            part_clean = _strip_summary_tokens(_clean_particulars(raw_part))
                            if part_clean and part_clean.lower().startswith(('opening balance','transaction total','closing balance')):
                                last_row = None
                                continue

                            debit = _parse_amount(raw_debit) if raw_debit else None
                            credit = _parse_amount(raw_credit) if raw_credit else None

                            if not part_clean and debit is None and credit is None:
                                continue

                            if d_iso is None:
                                if last_row and part_clean:
                                    last_row['particulars'] = (last_row.get('particulars','') + ' ' + part_clean).strip()
                                    if debit is not None and last_row.get('debit') is None:
                                        last_row['debit'] = debit
                                    if credit is not None and last_row.get('credit') is None:
                                        last_row['credit'] = credit
                                continue

                            item = {
                                'date': d_iso,
                                'particulars': part_clean,
                                'debit': debit,
                                'credit': credit,
                            }
                            out.append(item)
                            last_row = item
    except Exception:
        return out

    if not out:
        return out
    merged: List[Dict] = []
    for item in out:
        if merged:
            prev = merged[-1]
            if (
                item['date'] == prev['date']
                and item['debit'] is None
                and item['credit'] is None
                and item['particulars']
            ):
                prev['particulars'] = (prev['particulars'] + ' ' + item['particulars']).strip()
                continue
        merged.append(item)
    cleaned = [
        r for r in merged
        if not (
            r['particulars'] == ''
            and (r['debit'] is not None or r['credit'] is not None)
        )
    ]
    return cleaned


def parse_axis_statement_from_text(text: str) -> List[Dict]:
    """Fallback heuristic parser from extracted text when tables aren't available.
    We look for lines starting with a date, capture particulars, and any debit/credit tokens.
    """
    out: List[Dict] = []
    lines = [ln for ln in (text or '').splitlines() if ln.strip()]
    buf_date: Optional[str] = None
    buf_part: str = ''
    buf_debit: Optional[float] = None
    buf_credit: Optional[float] = None

    def flush():
        nonlocal buf_date, buf_part, buf_debit, buf_credit
        if buf_date and buf_part and (buf_debit is not None or buf_credit is not None):
            out.append({
                'date': buf_date, 'particulars': _clean_particulars(buf_part),
                'debit': buf_debit, 'credit': buf_credit,
            })
        buf_date = None; buf_part = ''; buf_debit = None; buf_credit = None

    for ln in lines:
        s = ' '.join(ln.split())
        # date at start
        d = _parse_date(s.split()[0] if s.split() else '')
        if d:
            # flush previous
            flush()
            buf_date = d
            # remove first token and the next if it's also a date-like (value date); keep remainder as particulars/amounts
            rest = ' '.join(s.split()[1:])
            # extract amounts near end
            tokens = rest.split()
            # Try to find explicit Cr/Dr tokens
            joined = rest.lower()
            # Extract numbers (last two tokens are often amounts)
            nums = [t for t in tokens if any(c.isdigit() for c in t)]
            if nums:
                # Assign by Cr/Dr hints
                if ' cr' in joined or 'credit' in joined:
                    buf_credit = _parse_amount(nums[-1])
                if ' dr' in joined or 'debit' in joined:
                    buf_debit = _parse_amount(nums[-1] if buf_credit is None else (nums[-2] if len(nums) > 1 else None))
            # particulars as rest without trailing numeric chunk
            buf_part = rest
        else:
            # continuation line; append to particulars
            if buf_date:
                buf_part = (buf_part + ' ' + s).strip()
                # update amounts if tags appear
                if ' cr' in s.lower() and buf_credit is None:
                    buf_credit = _parse_amount(s)
                if ' dr' in s.lower() and buf_debit is None:
                    buf_debit = _parse_amount(s)

    flush()
    # Filter out obvious non-rows
    out = [r for r in out if r['particulars'].lower() != 'opening balance']
    return out


def parse_axis_pdf(path: str, password: Optional[str] = None) -> List[Dict]:
    # Prefer structured tables
    rows = parse_axis_statement_from_tables(path, password=password)
    if rows:
        return rows
    # Fallback to text: try pypdf/pdfplumber text extraction (handled upstream), pass here if already extracted
    # Here we read again via pypdf/pdfplumber to get raw text for heuristic parse
    text = ''
    if PdfReader is not None:
        try:
            reader = PdfReader(path)
            if reader.is_encrypted and password:
                reader.decrypt(password)
            for page in reader.pages:
                text += page.extract_text() or '\n'
        except Exception:
            text = ''
    if not text and pdfplumber is not None:
        try:
            with pdfplumber.open(path, password=password) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or '\n'
        except Exception:
            pass
    if not text:
        return []
    return parse_axis_statement_from_text(text)
