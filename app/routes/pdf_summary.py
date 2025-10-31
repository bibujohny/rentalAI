from flask import Blueprint, render_template, request, flash, current_app
from flask_login import login_required
import os
from werkzeug.utils import secure_filename
from ..utils.pdf_summary import extract_text_from_pdf, summarize_month

pdf_bp = Blueprint('pdf', __name__, url_prefix='/pdf')

UPLOAD_DIR = 'uploads'
ALLOWED_EXT = {'.pdf'}
MAX_SIZE_MB = 10


def allowed_file(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXT


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

        # Save temporarily
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        path = os.path.join(UPLOAD_DIR, secure_filename(f.filename))
        f.save(path)
        try:
            text = extract_text_from_pdf(path, password=password)
            if not text:
                flash('Could not extract text. Check password or PDF type (scanned PDFs may need OCR).', 'danger')
            else:
                result = summarize_month(text)
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    return render_template('pdf_summary.html', result=result)
