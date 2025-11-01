from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import date
from ..models import db
from ..models_monthly import MonthlySummary
import json
import re

summaries_bp = Blueprint('summaries', __name__, url_prefix='/summaries')

PB_START = "[[PB:"
PB_END = "]]"

def _parse_breakdown(notes: str | None):
    """Extract payment breakdown from notes.
    Format: [[PB:{"chakravarthy":{"cash":0,"upi":0},"relax_inn":{"cash":0,"upi":0}}]] optional free text after.
    Returns (breakdown_dict, free_text)
    """
    default = {"chakravarthy": {"cash": 0.0, "upi": 0.0}, "relax_inn": {"cash": 0.0, "upi": 0.0}}
    if not notes:
        return default, ""
    s = notes.strip()
    m = re.search(re.escape(PB_START) + r"(.*?)" + re.escape(PB_END), s)
    if not m:
        return default, s
    try:
        data = json.loads(m.group(1))
        # free text is notes with the PB block removed
        free = (s[:m.start()] + s[m.end():]).strip()
        # coerce
        for lod in ("chakravarthy", "relax_inn"):
            if lod not in data or not isinstance(data[lod], dict):
                data[lod] = {"cash": 0.0, "upi": 0.0}
            else:
                data[lod]["cash"] = float(data[lod].get("cash") or 0.0)
                data[lod]["upi"] = float(data[lod].get("upi") or 0.0)
        return data, free
    except Exception:
        return default, s


def _embed_breakdown(breakdown: dict, free_text: str | None) -> str:
    pb = PB_START + json.dumps(breakdown, separators=(",", ":")) + PB_END
    txt = (free_text or "").strip()
    return pb + (" " + txt if txt else "")


def month_name(m):
    return ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][m]


@summaries_bp.route('/')
@login_required
def list_summaries():
    year = request.args.get('year', type=int) or date.today().year
    years = [row[0] for row in db.session.query(MonthlySummary.year).distinct().order_by(MonthlySummary.year.desc()).all()]
    if year not in years:
        years = sorted(set(years + [year]), reverse=True)
    rows = (MonthlySummary.query.filter(MonthlySummary.year == year)
            .order_by(MonthlySummary.month.asc()).all())

    # Attach breakdown fields for display
    for r in rows:
        pb, _ = _parse_breakdown(r.notes)
        r.pb_chak_cash = pb["chakravarthy"]["cash"]
        r.pb_chak_upi = pb["chakravarthy"]["upi"]
        r.pb_rel_cash = pb["relax_inn"]["cash"]
        r.pb_rel_upi = pb["relax_inn"]["upi"]

    chart_labels = [f"{month_name(r.month)}" for r in rows]
    chart_values = [r.total_income or 0 for r in rows]

    return render_template('summaries_list.html', rows=rows, years=years, selected_year=year,
                           chart_labels=chart_labels, chart_values=chart_values)


@summaries_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_summary():
    if request.method == 'POST':
        year = int(request.form.get('year'))
        month = int(request.form.get('month'))
        if MonthlySummary.query.filter_by(year=year, month=month).first():
            flash('A summary for this month already exists.', 'warning')
            return redirect(url_for('summaries.list_summaries', year=year))

        # Payment breakdown inputs
        pb = {
            "chakravarthy": {
                "cash": float(request.form.get('chak_cash') or 0),
                "upi": float(request.form.get('chak_upi') or 0),
            },
            "relax_inn": {
                "cash": float(request.form.get('relax_cash') or 0),
                "upi": float(request.form.get('relax_upi') or 0),
            },
        }
        free_notes = request.form.get('notes') or None
        notes = _embed_breakdown(pb, free_notes)

        ms = MonthlySummary(
            year=year, month=month,
            lodge_chakravarthy=round(pb["chakravarthy"]["cash"] + pb["chakravarthy"]["upi"], 2),
            monthly_rent_building=float(request.form.get('monthly_rent_building') or 0),
            lodge_relax_inn=round(pb["relax_inn"]["cash"] + pb["relax_inn"]["upi"], 2),
            misc_income=float(request.form.get('misc_income') or 0),
            notes=notes,
        )
        ms.ensure_period_defaults()
        ms.compute_total()
        db.session.add(ms)
        db.session.commit()
        flash('Summary added.', 'success')
        return redirect(url_for('summaries.list_summaries', year=year))

    # Defaults for new item
    default_pb = {"chakravarthy": {"cash": 0.0, "upi": 0.0}, "relax_inn": {"cash": 0.0, "upi": 0.0}}
    return render_template('summaries_form.html', item=None, pb=default_pb, free_notes="")


@summaries_bp.route('/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
def edit_summary(item_id):
    ms = MonthlySummary.query.get_or_404(item_id)
    if request.method == 'POST':
        new_year = int(request.form.get('year'))
        new_month = int(request.form.get('month'))
        existing = MonthlySummary.query.filter_by(year=new_year, month=new_month).first()
        if existing and existing.id != ms.id:
            flash('A summary for this month already exists.', 'warning')
            return redirect(url_for('summaries.edit_summary', item_id=ms.id))

        # Read payment breakdown and recompute per-lodge totals
        pb = {
            "chakravarthy": {
                "cash": float(request.form.get('chak_cash') or 0),
                "upi": float(request.form.get('chak_upi') or 0),
            },
            "relax_inn": {
                "cash": float(request.form.get('relax_cash') or 0),
                "upi": float(request.form.get('relax_upi') or 0),
            },
        }
        free_notes = request.form.get('notes') or None
        notes = _embed_breakdown(pb, free_notes)

        ms.year = new_year
        ms.month = new_month
        ms.lodge_chakravarthy = round(pb["chakravarthy"]["cash"] + pb["chakravarthy"]["upi"], 2)
        ms.monthly_rent_building = float(request.form.get('monthly_rent_building') or 0)
        ms.lodge_relax_inn = round(pb["relax_inn"]["cash"] + pb["relax_inn"]["upi"], 2)
        ms.misc_income = float(request.form.get('misc_income') or 0)
        ms.notes = notes
        ms.ensure_period_defaults()
        ms.compute_total()
        db.session.commit()
        flash('Summary updated.', 'success')
        return redirect(url_for('summaries.list_summaries', year=ms.year))

    # Pre-fill with existing breakdown and free text notes
    pb, free = _parse_breakdown(ms.notes)
    return render_template('summaries_form.html', item=ms, pb=pb, free_notes=free)


@summaries_bp.route('/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_summary(item_id):
    ms = MonthlySummary.query.get_or_404(item_id)
    y = ms.year
    db.session.delete(ms)
    db.session.commit()
    flash('Summary deleted.', 'info')
    return redirect(url_for('summaries.list_summaries', year=y))
