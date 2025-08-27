from __future__ import annotations

from flask import Flask


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="dev-secret-change",  # replace in production
        SESSION_COOKIE_NAME="lead_scraper_session",
    )

    from .routes import bp as main_bp
    app.register_blueprint(main_bp)

    return app
