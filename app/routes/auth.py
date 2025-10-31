from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from ..models import db, User


auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard.home'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'warning')
            return redirect(url_for('auth.register'))
        user = User(username=username, password=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        flash('Registration successful. Please login.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile/password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password')
        new_pw = request.form.get('new_password')
        confirm_pw = request.form.get('confirm_password')

        # Validate
        if not check_password_hash(current_user.password, current_pw):
            flash('Current password is incorrect', 'danger')
            return redirect(url_for('auth.change_password'))
        if not new_pw or len(new_pw) < 8:
            flash('New password must be at least 8 characters', 'warning')
            return redirect(url_for('auth.change_password'))
        if new_pw != confirm_pw:
            flash('New passwords do not match', 'warning')
            return redirect(url_for('auth.change_password'))

        # Update
        current_user.password = generate_password_hash(new_pw)
        db.session.commit()
        flash('Password updated successfully', 'success')
        return redirect(url_for('dashboard.home'))

    return render_template('change_password.html')
