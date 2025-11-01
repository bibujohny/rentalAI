from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date


db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


class Building(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255))
    pincode = db.Column(db.String(20), index=True)
    total_rooms = db.Column(db.Integer, default=0)

    tenants = db.relationship("Tenant", backref="building", lazy=True)


class Tenant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    rent_amount = db.Column(db.Float, default=0.0)
    start_date = db.Column(db.Date, nullable=False, default=date.today)
    end_date = db.Column(db.Date, nullable=True)
    consumer_number = db.Column(db.String(120), nullable=True)
    deposit_amount = db.Column(db.Float, default=0.0)
    building_id = db.Column(db.Integer, db.ForeignKey("building.id"), nullable=False)


class LodgeGuest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    guest_name = db.Column(db.String(120), nullable=False)
    room_no = db.Column(db.String(50), nullable=False)
    stay_type = db.Column(db.String(20), nullable=False)  # 'daily' or 'monthly'
    check_in_date = db.Column(db.Date, default=date.today)
    check_out_date = db.Column(db.Date, nullable=True)
    rate_per_day = db.Column(db.Float, default=0.0)
    monthly_rate = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default="checked_in")  # checked_in / checked_out

    def calculate_total(self):
        if self.stay_type == 'daily' and self.check_in_date and self.check_out_date:
            days = (self.check_out_date - self.check_in_date).days or 1
            self.total_amount = round(days * (self.rate_per_day or 0.0), 2)
        elif self.stay_type == 'monthly':
            self.total_amount = round(self.monthly_rate or 0.0, 2)
        else:
            self.total_amount = self.total_amount or 0.0


def seed_demo_data():
    # Seed a default user
    if not User.query.filter_by(username="admin").first():
        from werkzeug.security import generate_password_hash
        db.session.add(User(username="admin", password=generate_password_hash("admin", method='pbkdf2:sha256')))
        db.session.commit()

    # Seed building
    if not Building.query.first():
        b = Building(name="Puthenpurayil Arcade", address="Kayamkulam", pincode="691501", total_rooms=20)
        db.session.add(b)
        db.session.commit()

        # Tenants
        t1 = Tenant(name="Anu Mathew", rent_amount=12000, start_date=date(2024, 1, 1), consumer_number="CN001", deposit_amount=24000, building_id=b.id)
        t2 = Tenant(name="Rahul Nair", rent_amount=9000, start_date=date(2024, 3, 15), consumer_number="CN002", deposit_amount=18000, building_id=b.id)
        db.session.add_all([t1, t2])

        # Lodge Guests
        g1 = LodgeGuest(guest_name="John Doe", room_no="101", stay_type="daily", check_in_date=date(2024, 5, 1), check_out_date=date(2024, 5, 3), rate_per_day=800, status="checked_out")
        g1.calculate_total()
        g2 = LodgeGuest(guest_name="Mary Ann", room_no="102", stay_type="monthly", check_in_date=date(2024, 5, 1), monthly_rate=15000, status="checked_in")
        g2.calculate_total()
        db.session.add_all([g1, g2])

        db.session.commit()
