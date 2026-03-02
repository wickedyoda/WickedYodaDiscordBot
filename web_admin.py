import os
import sqlite3
import threading
from datetime import datetime, timezone
from functools import wraps
from typing import Callable

from flask import Flask, flash, redirect, render_template_string, request, session, url_for


SENSITIVE_ENV_KEYS = {
    "DISCORD_TOKEN",
    "WEB_ADMIN_DEFAULT_PASSWORD",
    "WEB_ADMIN_SESSION_SECRET",
}


def _ensure_actions_table(db_path: str) -> None:
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                moderator TEXT,
                target TEXT,
                reason TEXT,
                guild TEXT
            )
            """
        )
        conn.commit()


def _fetch_actions(db_path: str, limit: int = 200) -> list[dict]:
    _ensure_actions_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT created_at, action, status, moderator, target, reason, guild
            FROM actions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def _fetch_counts(db_path: str) -> dict:
    _ensure_actions_table(db_path)
    with sqlite3.connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
        success = conn.execute("SELECT COUNT(*) FROM actions WHERE status='success'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM actions WHERE status='failed'").fetchone()[0]
    return {
        "total": total,
        "success": success,
        "failed": failed,
    }


PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: linear-gradient(180deg, #f3f6fa 0%, #ffffff 55%); min-height: 100vh; }
    .card-soft { border: 0; border-radius: 14px; box-shadow: 0 8px 24px rgba(0,0,0,0.08); }
    .brand { font-weight: 700; letter-spacing: .2px; }
    .table-wrap { overflow-x: auto; }
    .status-pill { text-transform: capitalize; }
  </style>
</head>
<body>
  <nav class="navbar navbar-expand-lg bg-white border-bottom sticky-top">
    <div class="container-fluid px-3 px-lg-4">
      <a class="navbar-brand brand" href="{{ url_for('dashboard') }}">WickedYoda's Little Helper</a>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#topNav">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="topNav">
        {% if session.get("user") %}
        <ul class="navbar-nav me-auto mb-2 mb-lg-0">
          <li class="nav-item"><a class="nav-link" href="{{ url_for('dashboard') }}">Dashboard</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('actions') }}">Actions</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
        </ul>
        <div class="d-flex">
          <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('logout') }}">Logout</a>
        </div>
        {% endif %}
      </div>
    </div>
  </nav>

  <main class="container px-3 px-lg-4 py-4">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
            {{ message }}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
          </div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    {% if page == "login" %}
      <div class="row justify-content-center mt-4">
        <div class="col-12 col-sm-10 col-md-7 col-lg-5">
          <div class="card card-soft p-4">
            <h1 class="h4 mb-3">Admin Login</h1>
            <form method="post">
              <div class="mb-3">
                <label class="form-label" for="username">Username</label>
                <input class="form-control" id="username" name="username" required autocomplete="username">
              </div>
              <div class="mb-3">
                <label class="form-label" for="password">Password</label>
                <input class="form-control" id="password" name="password" type="password" required autocomplete="current-password">
              </div>
              <button class="btn btn-primary w-100" type="submit">Sign in</button>
            </form>
          </div>
        </div>
      </div>
    {% elif page == "dashboard" %}
      <div class="row g-3 mb-3">
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Bot</p>
            <p class="mb-0 fw-semibold">{{ snapshot.bot_name }}</p>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Guild</p>
            <p class="mb-0 fw-semibold">{{ snapshot.guild_id }}</p>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Latency</p>
            <p class="mb-0 fw-semibold">{{ snapshot.latency_ms }} ms</p>
          </div>
        </div>
      </div>
      <div class="row g-3 mb-3">
        <div class="col-6 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Total Actions</p>
            <p class="mb-0 fs-5 fw-bold">{{ counts.total }}</p>
          </div>
        </div>
        <div class="col-6 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Success</p>
            <p class="mb-0 fs-5 fw-bold text-success">{{ counts.success }}</p>
          </div>
        </div>
        <div class="col-6 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Failed</p>
            <p class="mb-0 fs-5 fw-bold text-danger">{{ counts.failed }}</p>
          </div>
        </div>
      </div>
      <div class="card card-soft p-3">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <h2 class="h6 mb-0">Latest Actions</h2>
          <a href="{{ url_for('actions') }}" class="btn btn-sm btn-outline-primary">View all</a>
        </div>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Time (UTC)</th><th>Action</th><th>Status</th><th>Moderator</th><th>Target</th></tr></thead>
            <tbody>
              {% for row in actions %}
              <tr>
                <td class="small">{{ row.created_at }}</td>
                <td>{{ row.action }}</td>
                <td><span class="badge text-bg-{{ 'success' if row.status == 'success' else 'danger' }} status-pill">{{ row.status }}</span></td>
                <td class="small">{{ row.moderator or '-' }}</td>
                <td class="small">{{ row.target or '-' }}</td>
              </tr>
              {% else %}
              <tr><td colspan="5" class="text-secondary">No actions logged yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "actions" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Moderation Actions</h1>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Time (UTC)</th><th>Action</th><th>Status</th><th>Moderator</th><th>Target</th><th>Reason</th><th>Guild</th></tr></thead>
            <tbody>
              {% for row in actions %}
              <tr>
                <td class="small">{{ row.created_at }}</td>
                <td>{{ row.action }}</td>
                <td><span class="badge text-bg-{{ 'success' if row.status == 'success' else 'danger' }} status-pill">{{ row.status }}</span></td>
                <td class="small">{{ row.moderator or '-' }}</td>
                <td class="small">{{ row.target or '-' }}</td>
                <td class="small">{{ row.reason or '-' }}</td>
                <td class="small">{{ row.guild or '-' }}</td>
              </tr>
              {% else %}
              <tr><td colspan="7" class="text-secondary">No actions logged yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "settings" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Runtime Settings</h1>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Key</th><th>Value</th></tr></thead>
            <tbody>
              {% for item in settings %}
              <tr><td><code>{{ item.key }}</code></td><td class="small">{{ item.value }}</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% endif %}
  </main>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""


def create_app(db_path: str, get_bot_snapshot: Callable[[], dict]) -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("WEB_ADMIN_SESSION_SECRET", "change-me-in-env")
    admin_user = os.getenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    admin_password = os.getenv("WEB_ADMIN_DEFAULT_PASSWORD", "ChangeMe123!")

    def login_required(handler):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            if not session.get("user"):
                return redirect(url_for("login"))
            return handler(*args, **kwargs)

        return wrapped

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if username.lower() == admin_user.lower() and password == admin_password:
                session["user"] = username
                flash("Logged in.", "success")
                return redirect(url_for("dashboard"))
            flash("Invalid credentials.", "danger")
        return render_template_string(PAGE_TEMPLATE, page="login", title="Web Admin Login")

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    def index():
        if session.get("user"):
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.get("/admin")
    @login_required
    def dashboard():
        counts = _fetch_counts(db_path)
        actions = _fetch_actions(db_path, limit=15)
        snapshot = get_bot_snapshot()
        return render_template_string(
            PAGE_TEMPLATE,
            page="dashboard",
            title="Web Admin Dashboard",
            counts=counts,
            actions=actions,
            snapshot=snapshot,
        )

    @app.get("/admin/actions")
    @login_required
    def actions():
        return render_template_string(
            PAGE_TEMPLATE,
            page="actions",
            title="Moderation Action History",
            actions=_fetch_actions(db_path, limit=300),
        )

    @app.get("/admin/settings")
    @login_required
    def settings():
        keys = [
            "DISCORD_TOKEN",
            "GUILD_ID",
            "Bot_Log_Channel",
            "WEB_ENABLED",
            "WEB_BIND_HOST",
            "WEB_PORT",
            "WEB_ADMIN_DEFAULT_USERNAME",
        ]
        settings_view = []
        for key in keys:
            raw_value = os.getenv(key, "")
            value = "********" if key in SENSITIVE_ENV_KEYS and raw_value else raw_value
            settings_view.append({"key": key, "value": value or "(not set)"})
        return render_template_string(
            PAGE_TEMPLATE,
            page="settings",
            title="Web Admin Settings",
            settings=settings_view,
        )

    return app


def start_web_admin(
    db_path: str,
    get_bot_snapshot: Callable[[], dict],
    host: str,
    port: int,
) -> threading.Thread:
    app = create_app(db_path, get_bot_snapshot)

    def run() -> None:
        app.run(host=host, port=port, debug=False, use_reloader=False)

    thread = threading.Thread(target=run, daemon=True, name="web-admin")
    thread.start()
    return thread
