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
    Works across pages that may omit headers after page 1 by carrying forward the last-known column indexes.
    Also cleans merged rows where summary phrases appear after the particulars by stripping them out.
    """
    if pdfplumber is None:
        return []
    out: List[Dict] = []
    # Persist indices across tables/pages if headers are missing
    idx_date: Optional[int] = None
    idx_part: Optional[int] = None
    idx_debit: Optional[int] = None
    idx_credit: Optional[int] = None
    last_row: Optional[Dict] = None

    try:
        with pdfplumber.open(path, password=password) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for tbl in tables:
                    if not tbl or len(tbl) < 1:
                        continue
                    # Try to locate a header row in first few lines
                    header_idx = None
                    for i, row in enumerate(tbl[:5]):
                        row_l = [str(c).strip().lower() if c is not None else '' for c in row]
                        if any('tran' in x and 'date' in x for x in row_l) and any('particular' in x for x in row_l):
                            header_idx = i
                            break
                    if header_idx is not None:
                        headers = [str(c).strip() if c is not None else '' for c in tbl[header_idx]]
                        headers_l = [h.lower() for h in headers]
                        def find_idx(cands: list[str]) -> Optional[int]:
                            for cand in cands:
                                for i,h in enumerate(headers_l):
                                    if cand in h:
                                        return i
                            return None
                        idx_date = find_idx(['tran date', 'transaction date', 'date'])
                        idx_part = find_idx(['particular', 'description'])
                        idx_debit = find_idx(['debit', 'withdrawal', '(dr)'])
                        idx_credit = find_idx(['credit', 'deposit', '(cr)'])
                        data_rows = tbl[header_idx+1:]
                    else:
                        # No header found on this table; if we have previous indexes, treat all rows as data
                        if idx_date is None or idx_part is None:
                            # Can't parse without at least date and particulars
                            continue
                        data_rows = tbl

                    for row in data_rows:
                        cells = [c if c is not None else '' for c in row]
                        if not any(str(x).strip() for x in cells):
                            continue
                        raw_date = cells[idx_date] if idx_date is not None and idx_date < len(cells) else ''
                        raw_part = cells[idx_part] if idx_part is not None and idx_part < len(cells) else ''
                        d_iso = _parse_date(str(raw_date)) if raw_date else None

                        # Continuation lines (no date) -> append to previous row
                        if not d_iso and last_row and str(raw_part).strip():
                            cont_text = ' '.join(str(c).strip() for c in cells if str(c).strip())
                            # Try to update debit/credit from columns if present
                            if idx_debit is not None and idx_debit < len(cells):
                                deb = _parse_amount(cells[idx_debit])
                                if deb is not None:
                                    last_row['debit'] = deb
                            if idx_credit is not None and idx_credit < len(cells):
                                cr = _parse_amount(cells[idx_credit])
                                if cr is not None:
                                    last_row['credit'] = cr
                            # Also scan particulars text for Cr/Dr tokens
                            lower = cont_text.lower()
                            if (' cr' in lower or 'credit' in lower) and (last_row.get('credit') is None):
                                last_row['credit'] = _parse_amount(cont_text)
                            if (' dr' in lower or 'debit' in lower) and (last_row.get('debit') is None):
                                last_row['debit'] = _parse_amount(cont_text)
                            # Append cleaned particulars (strip summary tokens if merged)
                            last_row['particulars'] = (last_row.get('particulars','') + ' ' + _strip_summary_tokens(_clean_particulars(raw_part))).strip()
                            continue

                        if not d_iso:
                            # Can't parse this line
                            continue

                        # Skip pure summary rows
                        low_part = str(raw_part).strip().lower()
                        if low_part.startswith(('opening balance','transaction total','closing balance')):
                            last_row = None
                            continue

                        debit = _parse_amount(cells[idx_debit]) if idx_debit is not None and idx_debit < len(cells) else None
                        credit = _parse_amount(cells[idx_credit]) if idx_credit is not None and idx_credit < len(cells) else None

                        # Fallback: amounts embedded in particulars
                        if (debit is None and credit is None) and raw_part:
                            lower = str(raw_part).lower()
                            if ' cr' in lower or 'credit' in lower:
                                credit = _parse_amount(raw_part)
                            if ' dr' in lower or 'debit' in lower and credit is None:
                                debit = _parse_amount(raw_part)

                        part_clean = _strip_summary_tokens(_clean_particulars(raw_part))
                        if not part_clean:
                            last_row = None
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
