from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from ..models import db, Building, Tenant
# News integration removed per request


buildings_bp = Blueprint('buildings', __name__)


@buildings_bp.route('/')
@login_required
def list_buildings():
    buildings = Building.query.all()
    return render_template('buildings.html', buildings=buildings)


@buildings_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_building():
    if request.method == 'POST':
        name = request.form.get('name')
        address = request.form.get('address')
        pincode = request.form.get('pincode')
        total_rooms = int(request.form.get('total_rooms') or 0)
        b = Building(name=name, address=address, pincode=pincode, total_rooms=total_rooms)
        db.session.add(b)
        db.session.commit()
        flash('Building added successfully', 'success')
        return redirect(url_for('buildings.list_buildings'))
    return render_template('buildings.html', buildings=Building.query.all(), show_add=True)


@buildings_bp.route('/edit/<int:building_id>', methods=['GET', 'POST'])
@login_required
def edit_building(building_id):
    b = Building.query.get_or_404(building_id)
    if request.method == 'POST':
        b.name = request.form.get('name')
        b.address = request.form.get('address')
        b.pincode = request.form.get('pincode')
        b.total_rooms = int(request.form.get('total_rooms') or 0)
        db.session.commit()
        flash('Building updated successfully', 'success')
        return redirect(url_for('buildings.list_buildings'))
    return render_template('buildings.html', buildings=Building.query.all(), edit_building=b)


@buildings_bp.route('/delete/<int:building_id>', methods=['POST'])
@login_required
def delete_building(building_id):
    b = Building.query.get_or_404(building_id)
    db.session.delete(b)
    db.session.commit()
    flash('Building deleted', 'info')
    return redirect(url_for('buildings.list_buildings'))


@buildings_bp.route('/detail/<int:building_id>')
@login_required
def building_detail(building_id):
    b = Building.query.get_or_404(building_id)
    tenants = Tenant.query.filter_by(building_id=b.id).all()
    return render_template('building_detail.html', building=b, tenants=tenants)
