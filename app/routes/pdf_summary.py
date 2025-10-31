from flask import Blueprint, render_template, request, flash, current_app
from flask_login import login_required
import os, uuid
from werkzeug.utils import secure_filename
from ..utils.pdf_summary import extract_text_from_pdf, summarize_month
from ..utils.axis_bank import parse_axis_pdf

pdf_bp = Blueprint('pdf', __name__, url_prefix='/pdf')

ALLOWED_EXT = {'.pdf'}
MAX_SIZE_MB = 20  # align with nginx client_max_body_size


def allowed_file(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXT


def upload_dir() -> str:
    # Place uploads under app root to avoid surprises with working dir
    root = current_app.root_path
    path = os.path.join(root, 'uploads')
    os.makedirs(path, exist_ok=True)
    return path


@pdf_bp.route('/summary', methods=['GET', 'POST'])
@login_required
def summary():
    result = None
    if request.method == 'POST':
        f = request.files.get('file')
        password = request.form.get('password') or (current_app.config.get('PDF_DEFAULT_PASSWORD') or None)
        if not f or f.filename == '':
            flash('Please choose a PDF file.', 'warning')
            return render_template('pdf_summary.html', result=None)
        if not allowed_file(f.filename):
            flash('Only PDF files are allowed.', 'warning')
            return render_template('pdf_summary.html', result=None)
        f.seek(0, os.SEEK_END)
        size_mb = f.tell() / (1024 * 1024)
        f.seek(0)
        if size_mb > MAX_SIZE_MB:
            flash(f'File too large: {size_mb:.1f} MB (max {MAX_SIZE_MB} MB).', 'warning')
            return render_template('pdf_summary.html', result=None)

        # Save temporarily (unique filename)
        try:
            updir = upload_dir()
            unique_name = f"{uuid.uuid4().hex}_{secure_filename(f.filename)}"
            path = os.path.join(updir, unique_name)
            f.save(path)
        except Exception as e:
            current_app.logger.exception("Upload save failed")
            flash(f'Upload failed: {e}', 'danger')
            return render_template('pdf_summary.html', result=None)
        try:
            using_default = '(default)' if (not request.form.get('password') and password) else ''
            current_app.logger.info(f"PDF processing started file={path}, password_used={bool(password)} {using_default}")
            text = extract_text_from_pdf(path, password=password)
            current_app.logger.info(f"PDF extracted length={len(text) if text else 0}")
            if not text:
                flash('Could not extract text. Check password or PDF type (scanned PDFs may need OCR).', 'danger')
            else:
                result = summarize_month(text)
                current_app.logger.info(f"PDF summary result={result}")
                # Fallback: if heuristic found nothing, try Axis transaction parser to compute totals
                try:
                    if (not result) or ((result.get('income_entries', 0) == 0) and (result.get('expense_entries', 0) == 0)):
                        rows = parse_axis_pdf(path, password=password)
                        if rows:
                            income_total = round(sum((r.get('credit') or 0.0) for r in rows), 2)
                            expense_total = round(sum((r.get('debit') or 0.0) for r in rows), 2)
                            result = {
                                'income_total': income_total,
                                'expense_total': expense_total,
                                'net': round(income_total - expense_total, 2),
                                'income_entries': sum(1 for r in rows if r.get('credit') not in (None, 0.0)),
                                'expense_entries': sum(1 for r in rows if r.get('debit') not in (None, 0.0)),
                            }
                            flash('Used transaction table fallback to compute totals.', 'info')
                            current_app.logger.info(f"PDF axis-fallback totals={result} rows={len(rows)}")
                except Exception:
                    current_app.logger.exception("Axis fallback failed")
        except Exception as e:
            current_app.logger.exception("PDF processing failed")
            flash(f'Error processing PDF: {e}', 'danger')
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    return render_template('pdf_summary.html', result=result)


@pdf_bp.route('/axis', methods=['GET', 'POST'])
@login_required
def axis_to_json():
    """Upload an Axis Bank statement PDF and return structured table of transactions with totals."""
    json_rows = None
    totals = None
    if request.method == 'POST':
        f = request.files.get('file')
        password = request.form.get('password') or (current_app.config.get('PDF_DEFAULT_PASSWORD') or None)
        if not f or f.filename == '':
            flash('Please choose a PDF file.', 'warning')
            return render_template('pdf_axis.html', json_rows=None)
        if not allowed_file(f.filename):
            flash('Only PDF files are allowed.', 'warning')
            return render_template('pdf_axis.html', json_rows=None)
        f.seek(0, os.SEEK_END)
        size_mb = f.tell() / (1024 * 1024)
        f.seek(0)
        if size_mb > MAX_SIZE_MB:
            flash(f'File too large: {size_mb:.1f} MB (max {MAX_SIZE_MB} MB).', 'warning')
            return render_template('pdf_axis.html', json_rows=None)
        try:
            updir = upload_dir()
            unique_name = f"{uuid.uuid4().hex}_{secure_filename(f.filename)}"
            path = os.path.join(updir, unique_name)
            f.save(path)
        except Exception as e:
            current_app.logger.exception("Upload save failed (axis)")
            flash(f'Upload failed: {e}', 'danger')
            return render_template('pdf_axis.html', json_rows=None)
        try:
            current_app.logger.info(f"Axis parse started file={path}, password_used={bool(password)}")
            rows = parse_axis_pdf(path, password=password)
            current_app.logger.info(f"Axis parsed {len(rows)} rows")
            json_rows = rows
            if rows:
                income_total = round(sum((r.get('credit') or 0.0) for r in rows), 2)
                expense_total = round(sum((r.get('debit') or 0.0) for r in rows), 2)
                totals = {
                    'income_total': income_total,
                    'expense_total': expense_total,
                    'net': round(income_total - expense_total, 2),
                    'count': len(rows),
                }
            else:
                flash('No transactions found. Check that this is an Axis Bank statement with a visible transactions table.', 'warning')
        except Exception as e:
            current_app.logger.exception("Axis PDF parsing failed")
            flash(f'Error parsing Axis statement: {e}', 'danger')
        finally:
            try:
                os.remove(path)
            except Exception:
                pass
    return render_template('pdf_axis.html', json_rows=json_rows, totals=totals)
