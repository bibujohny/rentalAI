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
    """Parse tables using pdfplumber with explicit column mapping based on the
    standard HDFC layout (Date, Narration, Chq/Ref, Value Dt, Withdrawal, Deposit, Balance).
    """
    if pdfplumber is None:
        return []
    out: List[Dict] = []
    last_row: Optional[Dict] = None
    current_date: Optional[str] = None

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
                    if not tbl or len(tbl) < 2:
                        continue
                    # identify header row
                    header_row = None
                    data_start_idx = 0
                    for i, row in enumerate(tbl[:4]):
                        cell0 = (row[0] or '').strip().lower()
                        cell1 = (row[1] or '').strip().lower()
                        if 'date' in cell0 and ('narration' in cell1 or 'details' in cell1):
                            header_row = row
                            data_start_idx = i + 1
                            break
                    if header_row is None:
                        # if we can't locate headers, skip to next table
                        continue

                    for raw_row in tbl[data_start_idx:]:
                        cells = [c.strip() if isinstance(c, str) else '' for c in raw_row]
                        if len(cells) < 2:
                            continue
                        date_cell = cells[0]
                        narration_cell = cells[1]
                        withdraw_cell = cells[4] if len(cells) > 4 else ''
                        deposit_cell = cells[5] if len(cells) > 5 else ''

                        if date_cell:
                            parsed_date = _parse_date(date_cell)
                            if parsed_date:
                                current_date = parsed_date
                        if not current_date and not narration_cell:
                            continue

                        narration = _clean_text(narration_cell)
                        if narration and any(
                            narration.lower().startswith(prefix) for prefix in SUMMARY_PREFIXES
                        ):
                            last_row = None
                            continue

                        debit = _parse_amount(withdraw_cell)
                        credit = _parse_amount(deposit_cell)

                        if not narration and debit is None and credit is None:
                            continue

                        if (
                            (not date_cell or not current_date)
                            and narration
                            and debit is None
                            and credit is None
                            and last_row is not None
                        ):
                            last_row['particulars'] = (
                                last_row.get('particulars', '') + ' ' + narration
                            ).strip()
                            continue

                        if current_date is None:
                            continue

                        row_obj = {
                            'date': current_date,
                            'particulars': narration,
                            'debit': debit,
                            'credit': credit,
                        }
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
