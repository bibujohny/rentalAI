from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from ..models import db, Tenant, Building
from datetime import datetime


tenants_bp = Blueprint('tenants', __name__)


@tenants_bp.route('/')
@login_required
def list_tenants():
    tenants = Tenant.query.all()
    buildings = Building.query.all()
    return render_template('tenants.html', tenants=tenants, buildings=buildings)


@tenants_bp.route('/add', methods=['POST'])
@login_required
def add_tenant():
    form = request.form
    t = Tenant(
        name=form.get('name'),
        rent_amount=float(form.get('rent_amount') or 0.0),
        start_date=datetime.strptime(form.get('start_date'), '%Y-%m-%d').date() if form.get('start_date') else None,
        end_date=datetime.strptime(form.get('end_date'), '%Y-%m-%d').date() if form.get('end_date') else None,
        consumer_number=form.get('consumer_number'),
        deposit_amount=float(form.get('deposit_amount') or 0.0),
        building_id=int(form.get('building_id')),
    )
    db.session.add(t)
    db.session.commit()
    flash('Tenant added successfully', 'success')
    return redirect(url_for('tenants.list_tenants'))


@tenants_bp.route('/edit/<int:tenant_id>', methods=['POST'])
@login_required
def edit_tenant(tenant_id):
    form = request.form
    t = Tenant.query.get_or_404(tenant_id)
    t.name = form.get('name')
    t.rent_amount = float(form.get('rent_amount') or 0.0)
    t.start_date = datetime.strptime(form.get('start_date'), '%Y-%m-%d').date() if form.get('start_date') else None
    t.end_date = datetime.strptime(form.get('end_date'), '%Y-%m-%d').date() if form.get('end_date') else None
    t.consumer_number = form.get('consumer_number')
    t.deposit_amount = float(form.get('deposit_amount') or 0.0)
    t.building_id = int(form.get('building_id'))
    db.session.commit()
    flash('Tenant updated successfully', 'success')
    return redirect(url_for('tenants.list_tenants'))


@tenants_bp.route('/delete/<int:tenant_id>', methods=['POST'])
@login_required
def delete_tenant(tenant_id):
    t = Tenant.query.get_or_404(tenant_id)
    db.session.delete(t)
    db.session.commit()
    flash('Tenant deleted', 'info')
    return redirect(url_for('tenants.list_tenants'))
