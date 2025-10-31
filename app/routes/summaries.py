from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import date
from ..models import db
from ..models_monthly import MonthlySummary

summaries_bp = Blueprint('summaries', __name__, url_prefix='/summaries')


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

        ms = MonthlySummary(
            year=year, month=month,
            lodge_chakravarthy=float(request.form.get('lodge_chakravarthy') or 0),
            monthly_rent_building=float(request.form.get('monthly_rent_building') or 0),
            lodge_relax_inn=float(request.form.get('lodge_relax_inn') or 0),
            misc_income=float(request.form.get('misc_income') or 0),
            notes=request.form.get('notes') or None,
        )
        ms.ensure_period_defaults()
        ms.compute_total()
        db.session.add(ms)
        db.session.commit()
        flash('Summary added.', 'success')
        return redirect(url_for('summaries.list_summaries', year=year))

    return render_template('summaries_form.html', item=None)


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

        ms.year = new_year
        ms.month = new_month
        ms.lodge_chakravarthy = float(request.form.get('lodge_chakravarthy') or 0)
        ms.monthly_rent_building = float(request.form.get('monthly_rent_building') or 0)
        ms.lodge_relax_inn = float(request.form.get('lodge_relax_inn') or 0)
        ms.misc_income = float(request.form.get('misc_income') or 0)
        ms.notes = request.form.get('notes') or None
        ms.ensure_period_defaults()
        ms.compute_total()
        db.session.commit()
        flash('Summary updated.', 'success')
        return redirect(url_for('summaries.list_summaries', year=ms.year))

    return render_template('summaries_form.html', item=ms)


@summaries_bp.route('/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_summary(item_id):
    ms = MonthlySummary.query.get_or_404(item_id)
    y = ms.year
    db.session.delete(ms)
    db.session.commit()
    flash('Summary deleted.', 'info')
    return redirect(url_for('summaries.list_summaries', year=y))
