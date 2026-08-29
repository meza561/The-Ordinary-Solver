"""
Authentication infrastructure: database, user model, and login manager.

Import these objects in app.py and call init_app:

    from auth import db, login_manager, User

    db.init_app(app)
    login_manager.init_app(app)
"""

from flask_login import LoginManager, UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username}>"


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    return db.session.get(User, int(user_id))

from flask import jsonify, request


@login_manager.unauthorized_handler
def unauthorized():
    """Return JSON 401 for AJAX/JSON requests; redirect to login for browser navigation."""
    from flask import redirect, url_for
    wants_json = (
        request.accept_mimetypes.accept_json
        and not request.accept_mimetypes.accept_html
    ) or request.is_json
    if wants_json:
        return jsonify(error="login_required", login_url=url_for("auth.login")), 401
    return redirect(url_for("auth.login", next=request.url))