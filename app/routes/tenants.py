import os
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, abort
from flask_login import login_required
from werkzeug.utils import secure_filename
from ..models import (
    db,
    Tenant,
    Building,
    TenantChange,
    TenantComplaint,
    TenantTodo,
)


tenants_bp = Blueprint('tenants', __name__)

ALLOWED_AGREEMENT_EXT = {'.pdf'}


def agreements_dir() -> str:
    """Ensure the agreements upload directory exists and return its path."""
    path = os.path.join(current_app.instance_path, 'agreements')
    os.makedirs(path, exist_ok=True)
    return path


def _store_agreement(file_storage, existing_filename=None):
    """Persist an uploaded agreement PDF, replacing any existing file."""
    if not file_storage or file_storage.filename == '':
        return existing_filename
    _, ext = os.path.splitext(file_storage.filename.lower())
    if ext not in ALLOWED_AGREEMENT_EXT:
        raise ValueError("Only PDF files are allowed for agreements.")
    filename = f"{uuid.uuid4().hex}_{secure_filename(file_storage.filename)}"
    dest_dir = agreements_dir()
    dest_path = os.path.join(dest_dir, filename)
    file_storage.save(dest_path)
    # Remove old file if provided
    if existing_filename:
        try:
            os.remove(os.path.join(dest_dir, existing_filename))
        except OSError:
            pass
    return filename


def _remove_agreement(filename: str):
    if not filename:
        return
    try:
        os.remove(os.path.join(agreements_dir(), filename))
    except OSError:
        pass


@tenants_bp.route('/')
@login_required
def list_tenants():
    tenants = (Tenant.query
               .order_by(Tenant.name.asc())
               .all())
    buildings = Building.query.all()
    return render_template('tenants.html', tenants=tenants, buildings=buildings)


@tenants_bp.route('/add', methods=['POST'])
@login_required
def add_tenant():
    form = request.form
    agreement_file = request.files.get('agreement')
    agreement_filename = None
    try:
        agreement_filename = _store_agreement(agreement_file)
    except ValueError as e:
        flash(str(e), 'warning')
        return redirect(url_for('tenants.list_tenants'))
    t = Tenant(
        name=form.get('name'),
        rent_amount=float(form.get('rent_amount') or 0.0),
        start_date=datetime.strptime(form.get('start_date'), '%Y-%m-%d').date() if form.get('start_date') else None,
        end_date=datetime.strptime(form.get('end_date'), '%Y-%m-%d').date() if form.get('end_date') else None,
        consumer_number=form.get('consumer_number'),
        deposit_amount=float(form.get('deposit_amount') or 0.0),
        building_id=int(form.get('building_id')),
        primary_contact=form.get('primary_contact') or None,
        secondary_contact=form.get('secondary_contact') or None,
        agreement_filename=agreement_filename,
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
    t.primary_contact = form.get('primary_contact') or None
    t.secondary_contact = form.get('secondary_contact') or None

    # Agreement handling
    if form.get('remove_agreement'):
        _remove_agreement(t.agreement_filename)
        t.agreement_filename = None
    else:
        new_file = request.files.get('agreement')
        if new_file and new_file.filename:
            try:
                t.agreement_filename = _store_agreement(new_file, t.agreement_filename)
            except ValueError as e:
                flash(str(e), 'warning')
                return redirect(url_for('tenants.list_tenants'))

    db.session.commit()
    flash('Tenant updated successfully', 'success')
    return redirect(url_for('tenants.list_tenants'))


@tenants_bp.route('/delete/<int:tenant_id>', methods=['POST'])
@login_required
def delete_tenant(tenant_id):
    t = Tenant.query.get_or_404(tenant_id)
    _remove_agreement(t.agreement_filename)
    db.session.delete(t)
    db.session.commit()
    flash('Tenant deleted', 'info')
    return redirect(url_for('tenants.list_tenants'))


@tenants_bp.route('/agreement/<int:tenant_id>')
@login_required
def download_agreement(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    if not tenant.agreement_filename:
        abort(404)
    directory = agreements_dir()
    return send_from_directory(directory, tenant.agreement_filename, as_attachment=True)


@tenants_bp.route('/<int:tenant_id>/change', methods=['POST'])
@login_required
def add_change(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    form = request.form
    description = form.get('description')
    if not description:
        flash('Please describe the change or work done.', 'warning')
        return redirect(url_for('tenants.list_tenants') + f"#tenant-{tenant_id}")
    change_date = None
    if form.get('change_date'):
        try:
            change_date = datetime.strptime(form.get('change_date'), '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date for change log.', 'warning')
            return redirect(url_for('tenants.list_tenants') + f"#tenant-{tenant_id}")
    change = TenantChange(
        tenant=tenant,
        description=description,
        change_date=change_date,
        amount_spent=float(form.get('amount_spent') or 0.0),
    )
    db.session.add(change)
    db.session.commit()
    flash('Change log saved.', 'success')
    return redirect(url_for('tenants.list_tenants') + f"#tenant-{tenant_id}")


@tenants_bp.route('/change/<int:change_id>/delete', methods=['POST'])
@login_required
def delete_change(change_id):
    change = TenantChange.query.get_or_404(change_id)
    tenant_id = change.tenant_id
    db.session.delete(change)
    db.session.commit()
    flash('Change log removed.', 'info')
    return redirect(url_for('tenants.list_tenants') + f"#tenant-{tenant_id}")


@tenants_bp.route('/<int:tenant_id>/complaint', methods=['POST'])
@login_required
def add_complaint(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    description = request.form.get('description')
    if not description:
        flash('Complaint details are required.', 'warning')
        return redirect(url_for('tenants.list_tenants') + f"#tenant-{tenant_id}")
    complaint = TenantComplaint(tenant=tenant, description=description.strip())
    db.session.add(complaint)
    db.session.commit()
    flash('Complaint recorded.', 'success')
    return redirect(url_for('tenants.list_tenants') + f"#tenant-{tenant_id}")


@tenants_bp.route('/complaint/<int:complaint_id>/resolve', methods=['POST'])
@login_required
def resolve_complaint(complaint_id):
    complaint = TenantComplaint.query.get_or_404(complaint_id)
    tenant_id = complaint.tenant_id
    complaint.status = 'resolved'
    complaint.resolved_at = datetime.utcnow()
    db.session.commit()
    flash('Complaint marked as resolved.', 'success')
    return redirect(url_for('tenants.list_tenants') + f"#tenant-{tenant_id}")


@tenants_bp.route('/complaint/<int:complaint_id>/delete', methods=['POST'])
@login_required
def delete_complaint(complaint_id):
    complaint = TenantComplaint.query.get_or_404(complaint_id)
    tenant_id = complaint.tenant_id
    db.session.delete(complaint)
    db.session.commit()
    flash('Complaint removed.', 'info')
    return redirect(url_for('tenants.list_tenants') + f"#tenant-{tenant_id}")


@tenants_bp.route('/<int:tenant_id>/todo', methods=['POST'])
@login_required
def add_todo(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    task = request.form.get('task')
    if not task:
        flash('Please provide a task description.', 'warning')
        return redirect(url_for('tenants.list_tenants') + f"#tenant-{tenant_id}")
    due_date = None
    if request.form.get('due_date'):
        try:
            due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid due date.', 'warning')
            return redirect(url_for('tenants.list_tenants') + f"#tenant-{tenant_id}")
    todo = TenantTodo(tenant=tenant, task=task.strip(), due_date=due_date)
    db.session.add(todo)
    db.session.commit()
    flash('To-do added.', 'success')
    return redirect(url_for('tenants.list_tenants') + f"#tenant-{tenant_id}")


@tenants_bp.route('/todo/<int:todo_id>/toggle', methods=['POST'])
@login_required
def toggle_todo(todo_id):
    todo = TenantTodo.query.get_or_404(todo_id)
    tenant_id = todo.tenant_id
    todo.is_done = not todo.is_done
    todo.completed_at = datetime.utcnow() if todo.is_done else None
    db.session.commit()
    flash('To-do updated.', 'success')
    return redirect(url_for('tenants.list_tenants') + f"#tenant-{tenant_id}")


@tenants_bp.route('/todo/<int:todo_id>/delete', methods=['POST'])
@login_required
def delete_todo(todo_id):
    todo = TenantTodo.query.get_or_404(todo_id)
    tenant_id = todo.tenant_id
    db.session.delete(todo)
    db.session.commit()
    flash('To-do removed.', 'info')
    return redirect(url_for('tenants.list_tenants') + f"#tenant-{tenant_id}")
