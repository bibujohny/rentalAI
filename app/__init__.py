from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from .models import db, User, seed_demo_data
from .routes.dashboard import dashboard_bp
from .routes.buildings import buildings_bp
from .routes.tenants import tenants_bp
from .routes.lodge import lodge_bp
from .routes.summaries import summaries_bp
from .routes.pdf_summary import pdf_bp
from .routes.auth import auth_bp
from config import config_by_name


def create_app(config_name: str = "default"):
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config_by_name[config_name])

    db.init_app(app)
    Migrate(app, db)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Template filters
    @app.template_filter('fmt_money')
    def fmt_money(value):
        try:
            return f"{float(value):,.2f}"
        except Exception:
            try:
                return f"{float(0 if value is None else value):,.2f}"
            except Exception:
                return "0.00"

    # Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(buildings_bp, url_prefix="/buildings")
    app.register_blueprint(tenants_bp, url_prefix="/tenants")
    app.register_blueprint(lodge_bp, url_prefix="/lodge")
    app.register_blueprint(summaries_bp)
    app.register_blueprint(pdf_bp)

    with app.app_context():
        db.create_all()
        # Allow tests and certain deploy contexts to skip seeding
        if not app.config.get('SKIP_SEED', False):
            seed_demo_data()

    return app
