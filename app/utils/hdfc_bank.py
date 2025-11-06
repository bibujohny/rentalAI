from __future__ import annotations
from typing import List, Dict, Optional
from dateutil import parser as dateparser

try:
    import pdfplumber
except Exception:  # pragma: no cover
    pdfplumber = None

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


def _parse_amount(cell: Optional[str]) -> Optional[float]:
    if not cell:
        return None
    s = str(cell).strip()
    if not s:
        return None
    s = (
        s.replace('INR', '')
        .replace('Rs', '')
        .replace('rs', '')
        .replace('₹', '')
        .replace(',', '')
    )
    s = s.replace('Dr', '').replace('CR', '').replace('Cr', '').replace('dr', '')
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


def _clean_text(cell: Optional[str]) -> str:
    if not cell:
        return ''
    return ' '.join(str(cell).split())


SUMMARY_PREFIXES = (
    'closing balance',
    'total',
    'opening balance',
)


def parse_hdfc_tables(path: str, password: Optional[str] = None) -> List[Dict]:
    if pdfplumber is None:
        return []
    out: List[Dict] = []
    idx_date: Optional[int] = None
    idx_narration: Optional[int] = None
    idx_withdrawal: Optional[int] = None
    idx_deposit: Optional[int] = None
    last_row: Optional[Dict] = None
    last_date_iso: Optional[str] = None

    try:
        with pdfplumber.open(path, password=password) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for tbl in tables:
                    if not tbl:
                        continue
                    header_idx = None
                    for i, row in enumerate(tbl[:4]):
                        lowered = [str(c).strip().lower() if c else '' for c in row]
                        if any('date' in cell for cell in lowered) and any(
                            ('narration' in cell) or ('particular' in cell)
                            for cell in lowered
                        ):
                            header_idx = i
                            break
                    if header_idx is not None:
                        headers = [
                            str(c).strip().lower() if c is not None else ''
                            for c in tbl[header_idx]
                        ]

                        def find_idx(cands: List[str]) -> Optional[int]:
                            for cand in cands:
                                for i, h in enumerate(headers):
                                    if cand in h:
                                        return i
                            return None

                        idx_date = find_idx(['date', 'tran date', 'transaction date', 'value dt'])
                        idx_narration = find_idx(['narration', 'particular', 'details', 'description'])
                        idx_withdrawal = find_idx(['withdrawal', 'withdrawal amt', 'debit', 'dr'])
                        idx_deposit = find_idx(['deposit', 'deposit amt', 'credit', 'cr'])
                        # Fallback to known column positions for standard HDFC layout
                        if idx_date is None:
                            idx_date = 0
                        if idx_narration is None:
                            idx_narration = 1
                        if idx_withdrawal is None and len(tbl[header_idx]) > 4:
                            idx_withdrawal = 4
                        if idx_deposit is None and len(tbl[header_idx]) > 5:
                            idx_deposit = 5
                        data_rows = tbl[header_idx + 1 :]
                    else:
                        if idx_date is None or idx_narration is None:
                            continue
                        data_rows = tbl

                    for row in data_rows:
                        cells = [c if c is not None else '' for c in row]
                        if not any(str(c).strip() for c in cells):
                            continue

                        raw_date = (
                            cells[idx_date]
                            if idx_date is not None and idx_date < len(cells)
                            else ''
                        )
                        narration_cell = (
                            cells[idx_narration]
                            if idx_narration is not None and idx_narration < len(cells)
                            else ''
                        )
                        narr_clean = _clean_text(narration_cell)
                        withdraw = (
                            _parse_amount(cells[idx_withdrawal])
                            if idx_withdrawal is not None and idx_withdrawal < len(cells)
                            else None
                        )
                        deposit = (
                            _parse_amount(cells[idx_deposit])
                            if idx_deposit is not None and idx_deposit < len(cells)
                            else None
                        )

                        d_iso = _parse_date(raw_date)
                        if d_iso:
                            last_date_iso = d_iso
                        else:
                            d_iso = last_date_iso

                        # Treat blank line items without amounts as narration continuation
                        if (
                            narr_clean
                            and withdraw is None
                            and deposit is None
                            and d_iso is None
                            and last_row
                        ):
                            last_row['particulars'] = (
                                last_row.get('particulars', '') + ' ' + narr_clean
                            ).strip()
                            continue

                        if not narr_clean and withdraw is None and deposit is None:
                            continue

                        if narr_clean and any(
                            narr_clean.lower().startswith(pref) for pref in SUMMARY_PREFIXES
                        ):
                            last_row = None
                            continue

                        if d_iso is None:
                            # Without a date we cannot create a new record
                            continue

                        row_obj = {
                            'date': d_iso,
                            'particulars': narr_clean,
                            'debit': withdraw,
                            'credit': deposit,
                        }

                        # If this row is purely a continuation (no amounts) attach to previous record
                        if (
                            withdraw is None
                            and deposit is None
                            and last_row is not None
                            and narr_clean
                            and row_obj['date'] == last_row.get('date')
                        ):
                            last_row['particulars'] = (
                                last_row.get('particulars', '') + ' ' + narr_clean
                            ).strip()
                            continue

                        out.append(row_obj)
                        last_row = row_obj
    except Exception:
        return out
    return out


def parse_hdfc_text(text: str) -> List[Dict]:
    out: List[Dict] = []
    if not text:
        return out
    lines = [ln for ln in text.splitlines() if ln.strip()]
    cur: Optional[Dict] = None

    def flush():
        nonlocal cur
        if cur and (cur.get('debit') is not None or cur.get('credit') is not None):
            cur['particulars'] = _clean_text(cur.get('particulars'))
            out.append(cur)
        cur = None

    for ln in lines:
        stripped = ' '.join(ln.split())
        parts = stripped.split()
        maybe_date = _parse_date(parts[0]) if parts else None
        if maybe_date:
            flush()
            cur = {
                'date': maybe_date,
                'particulars': ' '.join(parts[1:]),
                'debit': None,
                'credit': None,
            }
            if 'withdrawal' in stripped.lower():
                cur['debit'] = _parse_amount(stripped)
            if 'deposit' in stripped.lower() or 'credit' in stripped.lower():
                cur['credit'] = _parse_amount(stripped)
        else:
            if cur:
                cur['particulars'] = (cur.get('particulars', '') + ' ' + stripped).strip()
                if cur.get('debit') is None and 'withdrawal' in stripped.lower():
                    cur['debit'] = _parse_amount(stripped)
                if cur.get('credit') is None and (
                    'deposit' in stripped.lower() or 'credit' in stripped.lower()
                ):
                    cur['credit'] = _parse_amount(stripped)

    flush()
    return out


def parse_hdfc_pdf(path: str, password: Optional[str] = None) -> List[Dict]:
    rows = parse_hdfc_tables(path, password=password)
    if rows:
        return rows
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
    return parse_hdfc_text(text)
