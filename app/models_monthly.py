from datetime import date, datetime
import calendar
from sqlalchemy import UniqueConstraint
from .models import db


class MonthlySummary(db.Model):
    __tablename__ = 'monthly_summaries'
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False, index=True)
    month = db.Column(db.Integer, nullable=False, index=True)  # 1..12
    period_start = db.Column(db.Date, nullable=True)
    period_end = db.Column(db.Date, nullable=True)
    lodge_chakravarthy = db.Column(db.Float, default=0.0)
    monthly_rent_building = db.Column(db.Float, default=0.0)
    lodge_relax_inn = db.Column(db.Float, default=0.0)
    misc_income = db.Column(db.Float, default=0.0)
    total_income = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('year', 'month', name='uq_monthly_summaries_year_month'),
    )

    def compute_total(self):
        self.total_income = round(
            (self.lodge_chakravarthy or 0.0)
            + (self.monthly_rent_building or 0.0)
            + (self.lodge_relax_inn or 0.0)
            + (self.misc_income or 0.0),
            2
        )

    def ensure_period_defaults(self):
        if self.year and self.month:
            if not self.period_start:
                self.period_start = date(self.year, self.month, 1)
            if not self.period_end:
                last_day = calendar.monthrange(self.year, self.month)[1]
                self.period_end = date(self.year, self.month, last_day)
