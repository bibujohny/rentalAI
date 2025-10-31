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


def _parse_amount(cell: str | None) -> Optional[float]:
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


def _parse_date(cell: str | None) -> Optional[str]:
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


def _clean_particulars(cell: str | None) -> str:
    if not cell:
        return ''
    return ' '.join(str(cell).split())


def parse_axis_statement_from_tables(path: str, password: Optional[str] = None) -> List[Dict]:
    """Use pdfplumber to extract tables and parse Axis Bank transactions.
    Expected headers often include: 'Tran Date', 'Particulars', 'Chq No', 'Init. Br', 'Debit', 'Credit', 'Balance'
    We'll map debit/credit from headers that contain 'Debit'/'Withdrawal' and 'Credit'/'Deposit'.
    """
    if pdfplumber is None:
        return []
    out: List[Dict] = []
    try:
        with pdfplumber.open(path, password=password) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for tbl in tables:
                    if not tbl or len(tbl) < 2:
                        continue
                    # Find header row: look for a row containing 'Tran Date' and 'Particulars'
                    header_idx = None
                    for i, row in enumerate(tbl[:3]):  # first few rows
                        row_l = [str(c).strip().lower() if c is not None else '' for c in row]
                        if any('tran' in x and 'date' in x for x in row_l) and any('particular' in x for x in row_l):
                            header_idx = i
                            break
                    if header_idx is None:
                        continue
                    headers = [str(c).strip() if c is not None else '' for c in tbl[header_idx]]
                    # Column indexes
                    idx_date = next((i for i,h in enumerate(headers) if 'Tran' in h or 'Date' in h), None)
                    idx_part = next((i for i,h in enumerate(headers) if 'Particular' in h), None)
                    idx_debit = next((i for i,h in enumerate(headers) if 'Debit' in h or 'Withdrawal' in h), None)
                    idx_credit = next((i for i,h in enumerate(headers) if 'Credit' in h or 'Deposit' in h), None)
                    # Iterate rows after header
                    for row in tbl[header_idx+1:]:
                        cells = [c if c is not None else '' for c in row]
                        # skip header repeats or blank
                        if not any(str(x).strip() for x in cells):
                            continue
                        raw_date = cells[idx_date] if idx_date is not None and idx_date < len(cells) else ''
                        raw_part = cells[idx_part] if idx_part is not None and idx_part < len(cells) else ''
                        # Skip opening balance or header repeats
                        if str(raw_part).strip().lower().startswith('opening balance'):
                            continue
                        d_iso = _parse_date(str(raw_date))
                        if not d_iso:
                            # Not a transaction row
                            continue
                        debit = _parse_amount(cells[idx_debit]) if idx_debit is not None and idx_debit < len(cells) else None
                        credit = _parse_amount(cells[idx_credit]) if idx_credit is not None and idx_credit < len(cells) else None
                        item = {
                            'date': d_iso,
                            'particulars': _clean_particulars(raw_part),
                            'debit': debit,
                            'credit': credit,
                        }
                        out.append(item)
    except Exception:
        return out
    return out


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
