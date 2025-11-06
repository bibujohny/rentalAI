from flask import Blueprint, render_template, request, flash, current_app, jsonify
from flask_login import login_required
import os, uuid, shutil, json
from datetime import date, datetime
from werkzeug.utils import secure_filename
from ..utils.pdf_summary import extract_text_from_pdf, summarize_month
from ..utils.axis_bank import parse_axis_pdf
from ..utils.hdfc_bank import parse_hdfc_pdf
from ..models_monthly import MonthlySummary
from ..models import db

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
                        # Safety: drop any rows that have both debit and credit populated
                        rows = [r for r in (rows or []) if not (r.get('debit') is not None and r.get('credit') is not None)]
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


@pdf_bp.route('/save-monthly', methods=['POST'])
@login_required
def save_monthly():
    try:
        year = int(request.form.get('year'))
        month = int(request.form.get('month'))
    except Exception:
        flash('Select a valid month and year.', 'warning')
        return render_template('pdf_summary.html', result=None)

    mode = request.form.get('mode') or 'net'  # 'income' or 'net'
    try:
        income_total = float(request.form.get('income_total') or 0)
        expense_total = float(request.form.get('expense_total') or 0)
        net_total = float(request.form.get('net') or (income_total - expense_total))
    except Exception:
        flash('Invalid totals provided.', 'danger')
        return render_template('pdf_summary.html', result=None)

    value = income_total if mode == 'income' else net_total

    existing = MonthlySummary.query.filter_by(year=year, month=month).first()
    if existing:
        existing.lodge_chakravarthy = 0.0
        existing.monthly_rent_building = 0.0
        existing.lodge_relax_inn = 0.0
        existing.misc_income = value
        existing.compute_total()
        existing.notes = (existing.notes or '') + ' Imported from PDF summary.'
        existing.ensure_period_defaults()
        db.session.commit()
        flash('Monthly summary updated.', 'success')
        return render_template('pdf_summary.html', result={
            'income_total': income_total,
            'expense_total': expense_total,
            'net': net_total,
            'income_entries': int(request.form.get('income_entries') or 0),
            'expense_entries': int(request.form.get('expense_entries') or 0),
        })

    ms = MonthlySummary(
        year=year,
        month=month,
        lodge_chakravarthy=0.0,
        monthly_rent_building=0.0,
        lodge_relax_inn=0.0,
        misc_income=value,
        notes='Imported from PDF summary.',
    )
    ms.ensure_period_defaults()
    ms.compute_total()
    db.session.add(ms)
    db.session.commit()
    flash('Monthly summary saved.', 'success')
    return render_template('pdf_summary.html', result={
        'income_total': income_total,
        'expense_total': expense_total,
        'net': net_total,
        'income_entries': int(request.form.get('income_entries') or 0),
        'expense_entries': int(request.form.get('expense_entries') or 0),
    })


@pdf_bp.route('/axis', methods=['GET', 'POST'])
@login_required
def axis_to_json():
    """Upload an Axis Bank statement PDF and return structured table of transactions with totals.
    Optional: save the parsed JSON data on the server for a selected month/year, and view saved data.
    """
    json_rows = None
    totals = None
    cur_year = date.today().year
    cur_month = date.today().month
    years = list(range(2022, 2036))
    saved_files = None
    saved_all = None
    loaded_file = None

    def saved_data_dir(y: int, m: int) -> str:
        updir = upload_dir()
        path = os.path.join(updir, 'axis_data', str(y), f"{y}-{m:02d}")
        os.makedirs(path, exist_ok=True)
        return path

    # View saved data (GET)
    view_year = request.args.get('view_year', type=int)
    view_month = request.args.get('view_month', type=int)
    view_file = request.args.get('view_file')
    if request.method == 'GET' and view_year and view_month:
        try:
            sdir = saved_data_dir(view_year, view_month)
            files = [os.path.join(sdir, f) for f in os.listdir(sdir) if f.endswith('.json')]
            files_meta = []
            for p in files:
                try:
                    st = os.stat(p)
                    files_meta.append({
                        'name': os.path.basename(p),
                        'mtime': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M'),
                        'size_kb': round(st.st_size / 1024, 1),
                        'path': p,
                    })
                except Exception:
                    continue
            # sort by mtime desc using actual file mtime
            files_meta.sort(key=lambda x: os.path.getmtime(os.path.join(sdir, x['name'])), reverse=True)
            saved_files = files_meta
            if not files_meta:
                flash('No saved data found for the selected month.', 'warning')
            else:
                chosen = None
                if view_file and any(f['name'] == view_file for f in files_meta):
                    chosen = os.path.join(sdir, view_file)
                else:
                    chosen = os.path.join(sdir, files_meta[0]['name'])
                loaded_file = os.path.basename(chosen)
                with open(chosen, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                rows = data.get('rows') or []
                # Recompute subtotals if not stored
                office_income_total = 0.0
                lodge_income_total = 0.0
                for r in rows:
                    credit = r.get('credit') or 0.0
                    if credit:
                        itype = r.get('income_type')
                        if itype == 'office':
                            office_income_total += credit
                        elif itype == 'lodge':
                            lodge_income_total += credit
                json_rows = rows
                income_total = round(sum((r.get('credit') or 0.0) for r in rows), 2)
                expense_total = round(sum((r.get('debit') or 0.0) for r in rows), 2)
                totals = {
                    'income_total': income_total,
                    'expense_total': expense_total,
                    'net': round(income_total - expense_total, 2),
                    'count': len(rows),
                    'office_income_total': round(office_income_total, 2),
                    'lodge_income_total': round(lodge_income_total, 2),
                }
                flash(f"Loaded saved data for {view_year}-{view_month:02d}", 'info')
        except Exception:
            current_app.logger.exception('Failed to load saved axis data')
            flash('Failed to load saved data.', 'danger')

    if request.method == 'POST':
        f = request.files.get('file')
        password = request.form.get('password') or (current_app.config.get('PDF_DEFAULT_PASSWORD') or None)
        save_json = True if request.form.get('save_json') else False
        save_year = request.form.get('save_year', type=int) or cur_year
        save_month = request.form.get('save_month', type=int) or cur_month

        if not f or f.filename == '':
            flash('Please choose a PDF file.', 'warning')
            return render_template('pdf_axis.html', json_rows=json_rows, totals=totals, years=years, cur_year=cur_year, cur_month=cur_month)
        if not allowed_file(f.filename):
            flash('Only PDF files are allowed.', 'warning')
            return render_template('pdf_axis.html', json_rows=json_rows, totals=totals, years=years, cur_year=cur_year, cur_month=cur_month)
        f.seek(0, os.SEEK_END)
        size_mb = f.tell() / (1024 * 1024)
        f.seek(0)
        if size_mb > MAX_SIZE_MB:
            flash(f'File too large: {size_mb:.1f} MB (max {MAX_SIZE_MB} MB).', 'warning')
            return render_template('pdf_axis.html', json_rows=json_rows, totals=totals, years=years, cur_year=cur_year, cur_month=cur_month)
        try:
            updir = upload_dir()
            unique_name = f"{uuid.uuid4().hex}_{secure_filename(f.filename)}"
            tmp_path = os.path.join(updir, unique_name)
            f.save(tmp_path)
        except Exception as e:
            current_app.logger.exception("Upload save failed (axis)")
            flash(f'Upload failed: {e}', 'danger')
            return render_template('pdf_axis.html', json_rows=json_rows, totals=totals, years=years, cur_year=cur_year, cur_month=cur_month)
        try:
            current_app.logger.info(f"Axis parse started file={tmp_path}, password_used={bool(password)}")
            rows = parse_axis_pdf(tmp_path, password=password)
            current_app.logger.info(f"Axis parsed {len(rows)} rows before filtering")
            # Remove summary rows and hide any row that has both debit and credit
            filtered = []
            for r in rows:
                part = (r.get('particulars') or '').strip().lower()
                if part.startswith('transaction total') or part.startswith('closing balance'):
                    continue
                if r.get('debit') is not None and r.get('credit') is not None:
                    continue
                filtered.append(r)
            rows = filtered
            current_app.logger.info(f"Axis kept {len(rows)} rows after removing summary rows and double-sided entries")

            # Classify incomes: Office Rental vs Lodge based on payer names in particulars
            office_keywords = [
                'hi tech med gas solutions',
                'meerathan',
                'brilliant',
                'rinuraju',
            ]
            office_income_total = 0.0
            lodge_income_total = 0.0
            for r in rows:
                r['income_type'] = None
                credit = r.get('credit') or 0.0
                if credit:
                    part = (r.get('particulars') or '').lower()
                    if any(k in part for k in office_keywords):
                        r['income_type'] = 'office'
                        office_income_total += credit
                    else:
                        r['income_type'] = 'lodge'
                        lodge_income_total += credit

            json_rows = rows
            if rows:
                income_total = round(sum((r.get('credit') or 0.0) for r in rows), 2)
                expense_total = round(sum((r.get('debit') or 0.0) for r in rows), 2)
                totals = {
                    'income_total': income_total,
                    'expense_total': expense_total,
                    'net': round(income_total - expense_total, 2),
                    'count': len(rows),
                    'office_income_total': round(office_income_total, 2),
                    'lodge_income_total': round(lodge_income_total, 2),
                }
                if save_json and (save_year in years) and (1 <= save_month <= 12):
                    try:
                        sdir = saved_data_dir(save_year, save_month)
                        fname = f"axis_{save_year}-{save_month:02d}_{uuid.uuid4().hex[:6]}.json"
                        fpath = os.path.join(sdir, fname)
                        with open(fpath, 'w', encoding='utf-8') as fh:
                            json.dump({'rows': rows, 'totals': totals, 'year': save_year, 'month': save_month}, fh, ensure_ascii=False)
                        flash(f'Saved parsed data as {fname}', 'success')
                    except Exception:
                        current_app.logger.exception('Failed to save parsed JSON')
                        flash('Failed to save parsed data.', 'danger')
            else:
                flash('No transactions found. Check that this is an Axis Bank statement with a visible transactions table.', 'warning')
        except Exception as e:
            current_app.logger.exception("Axis PDF parsing failed")
            flash(f'Error parsing Axis statement: {e}', 'danger')
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
    # JSON toggle
    if request.args.get('format') == 'json':
        return jsonify(json_rows or [])

    # Build flat list of all saved JSON across months for quick access
    try:
        base = os.path.join(upload_dir(), 'axis_data')
        if os.path.isdir(base):
            all_items = []
            for yname in sorted(os.listdir(base), reverse=True):
                ypath = os.path.join(base, yname)
                if not os.path.isdir(ypath):
                    continue
                for mname in sorted(os.listdir(ypath), reverse=True):
                    mpath = os.path.join(ypath, mname)
                    if not os.path.isdir(mpath):
                        continue
                    # Expect mname like YYYY-MM
                    try:
                        parts = mname.split('-')
                        yy = int(parts[0]); mm = int(parts[1])
                    except Exception:
                        continue
                    for fname in sorted(os.listdir(mpath)):
                        if not fname.endswith('.json'):
                            continue
                        fpath = os.path.join(mpath, fname)
                        try:
                            st = os.stat(fpath)
                            all_items.append({
                                'year': yy,
                                'month': mm,
                                'name': fname,
                                'mtime': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M'),
                                'size_kb': round(st.st_size / 1024, 1),
                            })
                        except Exception:
                            continue
            # Sort by mtime desc
            saved_all = sorted(all_items, key=lambda x: (x['year'], x['month'], x['mtime']), reverse=True)
    except Exception:
        current_app.logger.exception('Failed to list all saved axis JSONs')
        saved_all = None

    return render_template('pdf_axis.html', json_rows=json_rows, totals=totals, years=years, cur_year=cur_year, cur_month=cur_month, saved_files=saved_files, saved_all=saved_all, loaded_file=loaded_file, view_year=view_year, view_month=view_month)


@pdf_bp.route('/hdfc', methods=['GET', 'POST'])
@login_required
def hdfc_to_json():
    """Upload an HDFC Bank statement PDF and return structured transaction data."""
    json_rows = None
    totals = None
    cur_year = date.today().year
    cur_month = date.today().month
    years = list(range(2022, 2036))
    saved_files = None
    saved_all = None
    loaded_file = None

    def saved_data_dir(y: int, m: int) -> str:
        base = upload_dir()
        path = os.path.join(base, 'hdfc_data', str(y), f"{y}-{m:02d}")
        os.makedirs(path, exist_ok=True)
        return path

    view_year = request.args.get('view_year', type=int)
    view_month = request.args.get('view_month', type=int)
    view_file = request.args.get('view_file')
    if request.method == 'GET' and view_year and view_month:
        try:
            sdir = saved_data_dir(view_year, view_month)
            files = [
                os.path.join(sdir, f)
                for f in os.listdir(sdir)
                if f.endswith('.json')
            ]
            files_meta = []
            for p in files:
                try:
                    st = os.stat(p)
                    files_meta.append(
                        {
                            'name': os.path.basename(p),
                            'mtime': datetime.fromtimestamp(st.st_mtime).strftime(
                                '%Y-%m-%d %H:%M'
                            ),
                            'size_kb': round(st.st_size / 1024, 1),
                            'path': p,
                        }
                    )
                except Exception:
                    continue
            files_meta.sort(
                key=lambda x: os.path.getmtime(os.path.join(sdir, x['name'])),
                reverse=True,
            )
            saved_files = files_meta
            if files_meta:
                chosen = None
                if view_file and any(f['name'] == view_file for f in files_meta):
                    chosen = os.path.join(sdir, view_file)
                else:
                    chosen = os.path.join(sdir, files_meta[0]['name'])
                loaded_file = os.path.basename(chosen)
                with open(chosen, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                rows = data.get('rows') or []
                json_rows = rows
                income_total = round(sum((r.get('credit') or 0.0) for r in rows), 2)
                expense_total = round(sum((r.get('debit') or 0.0) for r in rows), 2)
                office_income_total = round(
                    sum((r.get('credit') or 0.0) for r in rows if r.get('income_type') == 'office'),
                    2,
                )
                lodge_income_total = round(
                    sum((r.get('credit') or 0.0) for r in rows if r.get('income_type') == 'lodge'),
                    2,
                )
                totals = {
                    'income_total': income_total,
                    'expense_total': expense_total,
                    'net': round(income_total - expense_total, 2),
                    'count': len(rows),
                    'office_income_total': office_income_total,
                    'lodge_income_total': lodge_income_total,
                }
                flash(f"Loaded saved data for {view_year}-{view_month:02d}", 'info')
            else:
                flash('No saved data found for the selected month.', 'warning')
        except Exception:
            current_app.logger.exception('Failed to load saved HDFC data')
            flash('Failed to load saved data.', 'danger')

    if request.method == 'POST':
        f = request.files.get('file')
        password = request.form.get('password') or (
            current_app.config.get('PDF_DEFAULT_PASSWORD') or None
        )
        save_json = True if request.form.get('save_json') else False
        save_year = request.form.get('save_year', type=int) or cur_year
        save_month = request.form.get('save_month', type=int) or cur_month

        if not f or f.filename == '':
            flash('Please choose a PDF file.', 'warning')
            return render_template(
                'pdf_hdfc.html',
                json_rows=json_rows,
                totals=totals,
                years=years,
                cur_year=cur_year,
                cur_month=cur_month,
            )
        if not allowed_file(f.filename):
            flash('Only PDF files are allowed.', 'warning')
            return render_template(
                'pdf_hdfc.html',
                json_rows=json_rows,
                totals=totals,
                years=years,
                cur_year=cur_year,
                cur_month=cur_month,
            )
        f.seek(0, os.SEEK_END)
        size_mb = f.tell() / (1024 * 1024)
        f.seek(0)
        if size_mb > MAX_SIZE_MB:
            flash(
                f'File too large: {size_mb:.1f} MB (max {MAX_SIZE_MB} MB).',
                'warning',
            )
            return render_template(
                'pdf_hdfc.html',
                json_rows=json_rows,
                totals=totals,
                years=years,
                cur_year=cur_year,
                cur_month=cur_month,
            )
        try:
            updir = upload_dir()
            unique_name = f"{uuid.uuid4().hex}_{secure_filename(f.filename)}"
            tmp_path = os.path.join(updir, unique_name)
            f.save(tmp_path)
        except Exception as e:
            current_app.logger.exception("Upload save failed (hdfc)")
            flash(f'Upload failed: {e}', 'danger')
            return render_template(
                'pdf_hdfc.html',
                json_rows=json_rows,
                totals=totals,
                years=years,
                cur_year=cur_year,
                cur_month=cur_month,
            )
        try:
            current_app.logger.info(
                f"HDFC parse started file={tmp_path}, password_used={bool(password)}"
            )
            rows = parse_hdfc_pdf(tmp_path, password=password)
            current_app.logger.info(f"HDFC parsed {len(rows)} rows before filtering")
            filtered = []
            for r in rows:
                part = (r.get('particulars') or '').strip().lower()
                if not part:
                    continue
                if part.startswith('closing balance') or part.startswith('opening balance'):
                    continue
                if r.get('debit') is not None and r.get('credit') is not None:
                    continue
                filtered.append(r)
            rows = filtered
            current_app.logger.info(f"HDFC kept {len(rows)} rows after filtering")

            office_keywords = [
                'hi tech med gas solutions',
                'meerathan',
                'brilliant',
                'rinuraju',
            ]
            office_income_total = 0.0
            lodge_income_total = 0.0
            for r in rows:
                r['income_type'] = None
                credit = r.get('credit') or 0.0
                if credit:
                    part = (r.get('particulars') or '').lower()
                    if any(k in part for k in office_keywords):
                        r['income_type'] = 'office'
                        office_income_total += credit
                    else:
                        r['income_type'] = 'lodge'
                        lodge_income_total += credit

            json_rows = rows
            if rows:
                income_total = round(sum((r.get('credit') or 0.0) for r in rows), 2)
                expense_total = round(sum((r.get('debit') or 0.0) for r in rows), 2)
                totals = {
                    'income_total': income_total,
                    'expense_total': expense_total,
                    'net': round(income_total - expense_total, 2),
                    'count': len(rows),
                    'office_income_total': round(office_income_total, 2),
                    'lodge_income_total': round(lodge_income_total, 2),
                }
                if save_json and (save_year in years) and (1 <= save_month <= 12):
                    try:
                        sdir = saved_data_dir(save_year, save_month)
                        fname = f"hdfc_{save_year}-{save_month:02d}_{uuid.uuid4().hex[:6]}.json"
                        fpath = os.path.join(sdir, fname)
                        with open(fpath, 'w', encoding='utf-8') as fh:
                            json.dump(
                                {
                                    'rows': rows,
                                    'totals': totals,
                                    'year': save_year,
                                    'month': save_month,
                                },
                                fh,
                                ensure_ascii=False,
                            )
                        flash(f'Saved parsed data as {fname}', 'success')
                    except Exception:
                        current_app.logger.exception('Failed to save HDFC parsed JSON')
                        flash('Failed to save parsed data.', 'danger')
            else:
                flash(
                    'No transactions found. Ensure this is an HDFC Bank statement with visible tables.',
                    'warning',
                )
        except Exception as e:
            current_app.logger.exception("HDFC PDF parsing failed")
            flash(f'Error parsing HDFC statement: {e}', 'danger')
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    if request.args.get('format') == 'json':
        return jsonify(json_rows or [])

    try:
        base = os.path.join(upload_dir(), 'hdfc_data')
        if os.path.isdir(base):
            all_items = []
            for yname in sorted(os.listdir(base), reverse=True):
                ypath = os.path.join(base, yname)
                if not os.path.isdir(ypath):
                    continue
                for mname in sorted(os.listdir(ypath), reverse=True):
                    mpath = os.path.join(ypath, mname)
                    if not os.path.isdir(mpath):
                        continue
                    try:
                        yy, mm = (int(mname.split('-')[0]), int(mname.split('-')[1]))
                    except Exception:
                        continue
                    for fname in sorted(os.listdir(mpath)):
                        if not fname.endswith('.json'):
                            continue
                        fpath = os.path.join(mpath, fname)
                        try:
                            st = os.stat(fpath)
                            all_items.append(
                                {
                                    'year': yy,
                                    'month': mm,
                                    'name': fname,
                                    'mtime': datetime.fromtimestamp(st.st_mtime).strftime(
                                        '%Y-%m-%d %H:%M'
                                    ),
                                    'size_kb': round(st.st_size / 1024, 1),
                                }
                            )
                        except Exception:
                            continue
            saved_all = sorted(
                all_items, key=lambda x: (x['year'], x['month'], x['mtime']), reverse=True
            )
    except Exception:
        current_app.logger.exception('Failed to list all saved HDFC JSONs')
        saved_all = None

    return render_template(
        'pdf_hdfc.html',
        json_rows=json_rows,
        totals=totals,
        years=years,
        cur_year=cur_year,
        cur_month=cur_month,
        saved_files=saved_files,
        saved_all=saved_all,
        loaded_file=loaded_file,
        view_year=view_year,
        view_month=view_month,
    )
