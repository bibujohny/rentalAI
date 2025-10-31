import re
from typing import Tuple, Dict
from .ocr import ocr_pdf_to_text

try:
    import pdfplumber
except Exception:  # pragma: no cover
    pdfplumber = None

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

# Broadened keyword lists for better matching
INCOME_KEYWORDS = [
    r"\brent\b", r"\blodge\b", r"\bincome\b", r"\brevenue\b", r"\breceipt\b", r"\breceived\b",
    r"\badvance\b", r"\bdeposit\b", r"\bcollection\b", r"\broom\b", r"\bbooking\b", r"\bcredit\b", r"\bcr\b",
    r"\bmonthly\s+rent\b", r"\btenants?\b",
]
EXPENSE_KEYWORDS = [
    r"\bexpense\b", r"\bpaid\b", r"\bpayment\b", r"\boutflow\b", r"\bdebit\b", r"\bdr\b",
    r"\belectricity\b", r"\bpower\b", r"\bkseb\b", r"\bwater\b", r"\bgst\b", r"\btax\b",
    r"\bmaintenance\b", r"\brepair\b", r"\bwage\b", r"\bsalary\b", r"\bpurchase\b", r"\bsuppl(y|ies)\b",
]

# Amount detection: capture currency or plain numeric tokens with commas/decimals, optional parentheses for negatives
CURRENCY = r"(?:₹|rs\.?|inr)"
AMOUNT_TOKEN = re.compile(rf"(?i)(?<![\w])((?:{CURRENCY})?\s*\(?[+-]?\d{{1,3}}(?:,\d{{2,3}})*(?:\.\d{{1,2}})?|\d+(?:\.\d{{1,2}})?)\)?(?![\w])")


def extract_text_from_pdf(path: str, password: str | None = None) -> str:
    """Extract text from a (possibly encrypted) PDF using pypdf, fallback to pdfplumber."""
    text = ""
    # First try pypdf
    if PdfReader is not None:
        try:
            reader = PdfReader(path)
            if reader.is_encrypted and password:
                reader.decrypt(password)
            for page in reader.pages:
                text += page.extract_text() or "\n"
        except Exception:
            text = ""
    # Fallback to pdfplumber (often better for layout)
    if not text and pdfplumber is not None:
        try:
            with pdfplumber.open(path, password=password) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or "\n"
        except Exception:
            pass
    if not text:
        # Attempt OCR fallback for scanned PDFs
        text = ocr_pdf_to_text(path)
    return text


def _parse_amount_tokens(line: str, keywords_present: bool) -> float:
    """Find and sum amount tokens in a line.
    If there is no currency symbol present, we only consider bare numbers when keywords are present to reduce false positives.
    Parentheses or leading '-' make the number negative."""
    total = 0.0
    found_any = False
    for m in AMOUNT_TOKEN.finditer(line):
        raw = m.group(1)
        if not raw:
            continue
        if not re.search(CURRENCY, raw, re.IGNORECASE):
            if not keywords_present:
                # Skip bare numbers if the line has no relevant keywords
                continue
        neg = raw.strip().startswith('-') or '(' in raw
        cleaned = re.sub(CURRENCY, '', raw, flags=re.IGNORECASE)
        cleaned = cleaned.replace(',', '').replace('(', '').replace(')', '').strip()
        try:
            val = float(cleaned)
            total += (-val if neg else val)
            found_any = True
        except Exception:
            continue
    return total if found_any else 0.0


def summarize_month(text: str) -> Dict[str, float | str]:
    """Heuristic parse. Classify lines into income vs expenses using keyword matches; sum amounts.
    Returns a dict with totals and small breakdown counts."""
    income_total = 0.0
    expense_total = 0.0
    income_lines = 0
    expense_lines = 0

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        lower = ln.lower()
        has_income_kw = any(re.search(k, lower) for k in INCOME_KEYWORDS)
        has_expense_kw = any(re.search(k, lower) for k in EXPENSE_KEYWORDS)

        # Special totals
        if 'total income' in lower:
            amt = _parse_amount_tokens(lower, True)
            if amt:
                income_total += abs(amt)
                income_lines += 1
                continue
        if 'total expense' in lower or 'total expenses' in lower:
            amt = _parse_amount_tokens(lower, True)
            if amt:
                expense_total += abs(amt)
                expense_lines += 1
                continue

        amt = _parse_amount_tokens(lower, has_income_kw or has_expense_kw)
        if not amt:
            continue

        if has_income_kw and not has_expense_kw:
            income_total += abs(amt)
            income_lines += 1
        elif has_expense_kw and not has_income_kw:
            expense_total += abs(amt)
            expense_lines += 1
        else:
            # fallback based on signs / credit-debit hints
            if 'credit' in lower or ' cr' in lower:
                income_total += abs(amt)
                income_lines += 1
            elif 'debit' in lower or ' dr' in lower:
                expense_total += abs(amt)
                expense_lines += 1
            else:
                # Ambiguous; skip
                pass

    net = round(income_total - expense_total, 2)
    return {
        "income_total": round(income_total, 2),
        "expense_total": round(expense_total, 2),
        "net": net,
        "income_entries": income_lines,
        "expense_entries": expense_lines,
    }
