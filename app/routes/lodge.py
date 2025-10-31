from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from ..models import db, LodgeGuest
from datetime import datetime


lodge_bp = Blueprint('lodge', __name__)


@lodge_bp.route('/')
@login_required
def list_guests():
    status = request.args.get('status')
    stay_type = request.args.get('stay_type')
    q = LodgeGuest.query
    if status:
        q = q.filter_by(status=status)
    if stay_type:
        q = q.filter_by(stay_type=stay_type)
    guests = q.order_by(LodgeGuest.id.desc()).all()
    return render_template('lodge.html', guests=guests)


@lodge_bp.route('/add', methods=['POST'])
@login_required
def add_guest():
    form = request.form
    g = LodgeGuest(
        guest_name=form.get('guest_name'),
        room_no=form.get('room_no'),
        stay_type=form.get('stay_type'),
        check_in_date=datetime.strptime(form.get('check_in_date'), '%Y-%m-%d').date() if form.get('check_in_date') else None,
        check_out_date=datetime.strptime(form.get('check_out_date'), '%Y-%m-%d').date() if form.get('check_out_date') else None,
        rate_per_day=float(form.get('rate_per_day') or 0.0),
        monthly_rate=float(form.get('monthly_rate') or 0.0),
        status=form.get('status') or 'checked_in',
    )
    g.calculate_total()
    db.session.add(g)
    db.session.commit()
    flash('Guest added successfully', 'success')
    return redirect(url_for('lodge.list_guests'))


@lodge_bp.route('/edit/<int:guest_id>', methods=['POST'])
@login_required
def edit_guest(guest_id):
    form = request.form
    g = LodgeGuest.query.get_or_404(guest_id)
    g.guest_name = form.get('guest_name')
    g.room_no = form.get('room_no')
    g.stay_type = form.get('stay_type')
    g.check_in_date = datetime.strptime(form.get('check_in_date'), '%Y-%m-%d').date() if form.get('check_in_date') else None
    g.check_out_date = datetime.strptime(form.get('check_out_date'), '%Y-%m-%d').date() if form.get('check_out_date') else None
    g.rate_per_day = float(form.get('rate_per_day') or 0.0)
    g.monthly_rate = float(form.get('monthly_rate') or 0.0)
    g.status = form.get('status') or 'checked_in'
    g.calculate_total()
    db.session.commit()
    flash('Guest updated successfully', 'success')
    return redirect(url_for('lodge.list_guests'))


@lodge_bp.route('/checkout/<int:guest_id>', methods=['POST'])
@login_required
def checkout_guest(guest_id):
    g = LodgeGuest.query.get_or_404(guest_id)
    if not g.check_out_date:
        g.check_out_date = datetime.utcnow().date()
    g.status = 'checked_out'
    g.calculate_total()
    db.session.commit()
    flash('Guest checked out', 'info')
    return redirect(url_for('lodge.list_guests'))


@lodge_bp.route('/delete/<int:guest_id>', methods=['POST'])
@login_required
def delete_guest(guest_id):
    g = LodgeGuest.query.get_or_404(guest_id)
    db.session.delete(g)
    db.session.commit()
    flash('Entry deleted', 'info')
    return redirect(url_for('lodge.list_guests'))
