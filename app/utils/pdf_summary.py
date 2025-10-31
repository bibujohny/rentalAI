import re
from typing import Tuple, Dict

try:
    import pdfplumber
except Exception:  # pragma: no cover
    pdfplumber = None

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


INCOME_KEYWORDS = [
    r"\brent\b", r"\blodge\b", r"\breceipt\b", r"\bincome\b", r"\brevenue\b",
    r"\badvance\b", r"\bdeposit\b", r"\broombooking\b", r"\broombook\b",
]
EXPENSE_KEYWORDS = [
    r"\belectricity\b", r"\bmaintenance\b", r"\bsalary\b", r"\bexpense\b",
    r"\bpayment\b", r"\boutflow\b", r"\btax\b", r"\bwater\b", r"\brentpaid\b",
]
AMOUNT_RE = re.compile(r"(?i)(?:rs\.?|inr|₹)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)")


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
    return text


def summarize_month(text: str) -> Dict[str, float | str]:
    """Heuristic parse. Classify lines into income vs expenses using keyword matches; sum amounts.
    Returns a dict with totals and small breakdown counts."""
    income_total = 0.0
    expense_total = 0.0
    income_lines = 0
    expense_lines = 0

    lines = [ln.strip().lower() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        # detect amounts in the line; sum all found amounts on the line
        amounts = [float(a.replace(',', '')) for a in AMOUNT_RE.findall(ln)]
        if not amounts:
            continue
        amt = sum(amounts)
        # classify by keywords
        if any(re.search(k, ln) for k in INCOME_KEYWORDS):
            income_total += amt
            income_lines += 1
        elif any(re.search(k, ln) for k in EXPENSE_KEYWORDS):
            expense_total += amt
            expense_lines += 1
        else:
            # fallback: positive amounts without keywords are ambiguous; ignore
            pass

    net = round(income_total - expense_total, 2)
    return {
        "income_total": round(income_total, 2),
        "expense_total": round(expense_total, 2),
        "net": net,
        "income_entries": income_lines,
        "expense_entries": expense_lines,
    }
