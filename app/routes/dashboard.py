from flask import Blueprint, render_template
from flask_login import login_required
from ..models import db, Building, Tenant, LodgeGuest
from ..utils.ai import analyze_data


dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def home():
    buildings = Building.query.all()
    tenants = Tenant.query.all()
    guests = LodgeGuest.query.all()

    # Compute simple metrics
    total_buildings = len(buildings)
    total_tenants = len(tenants)
    total_guests = len([g for g in guests if g.status == 'checked_in'])
    monthly_revenue = sum(t.rent_amount for t in tenants) + sum(g.monthly_rate for g in guests if g.stay_type == 'monthly')

    # Prepare data for charts
    rent_trends = {
        'labels': ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        'values': [sum(t.rent_amount for t in tenants) / 12.0] * 12,  # placeholder simple trend
    }
    lodge_occupancy = {
        'labels': ["Week 1", "Week 2", "Week 3", "Week 4"],
        'values': [len([g for g in guests if g.status == 'checked_in'])] * 4,  # placeholder
    }

    # AI Insights
    rent_data = [{'tenant': t.name, 'rent_amount': t.rent_amount} for t in tenants]
    lodge_data = [{'guest': g.guest_name, 'stay_type': g.stay_type, 'status': g.status, 'total_amount': g.total_amount} for g in guests]
    insights = analyze_data(rent_data, lodge_data)

    return render_template('dashboard.html',
                           total_buildings=total_buildings,
                           total_tenants=total_tenants,
                           total_guests=total_guests,
                           monthly_revenue=monthly_revenue,
                           rent_trends=rent_trends,
                           lodge_occupancy=lodge_occupancy,
                           insights=insights)
