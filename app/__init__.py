import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_object=None):
    app = Flask(__name__, instance_relative_config=True)

    if config_object is None:
        from config import Config
        app.config.from_object(Config)
    else:
        app.config.from_object(config_object)

    # Ensure instance and upload directories exist
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)

    from app.routes.jobs import jobs_bp
    from app.routes.expenses import expenses_bp
    from app.routes.receipts import receipts_bp
    from app.routes.ui import ui_bp

    app.register_blueprint(jobs_bp, url_prefix="/api/jobs")
    app.register_blueprint(expenses_bp, url_prefix="/api/expenses")
    app.register_blueprint(receipts_bp, url_prefix="/api/receipts")
    app.register_blueprint(ui_bp)

    return app
