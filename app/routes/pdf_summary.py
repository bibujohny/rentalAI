from flask import Blueprint, render_template, request, flash, current_app
from flask_login import login_required
import os, uuid
from werkzeug.utils import secure_filename
from ..utils.pdf_summary import extract_text_from_pdf, summarize_month

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
            text = extract_text_from_pdf(path, password=password)
            if not text:
                flash('Could not extract text. Check password or PDF type (scanned PDFs may need OCR).', 'danger')
            else:
                result = summarize_month(text)
        except Exception as e:
            current_app.logger.exception("PDF processing failed")
            flash(f'Error processing PDF: {e}', 'danger')
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    return render_template('pdf_summary.html', result=result)
