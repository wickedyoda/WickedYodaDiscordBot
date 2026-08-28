"""WickedYoda Web Admin - GUI Variant 1.

Theme: "Modern Sidebar Dashboard"
- Persistent left sidebar (collapsible on mobile)
- Top: breadcrumbs, server selector, theme switch
- Main area: the legacy template's page body, wrapped in a clean tile-grid
  for the home page.

This variant uses the same body content as the existing template for non-home
pages, but adds a brand-new sidebar+topbar shell and a tile-grid home dashboard.
"""

from __future__ import annotations

PAGE_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="csrf-token" content="{{ csrf_token }}">
  <title>{{ title }} · WickedYoda Admin</title>
  <link rel="icon" href="{{ url_for('static', filename='wicked-yoda-favicon.png') }}">
  <link rel="apple-touch-icon" sizes="180x180" href="{{ url_for('static', filename='wicked-yoda-avatar.png') }}">
  <meta property="og:image" content="{{ url_for('static', filename='wicked-yoda-avatar.png') }}">
  <meta name="twitter:image" content="{{ url_for('static', filename='wicked-yoda-avatar.png') }}">
  {% if page == "status_public" and status_refresh_seconds and status_refresh_seconds > 0 %}
  <meta http-equiv="refresh" content="{{ status_refresh_seconds }}">
  {% endif %}
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet">
  <style>
    :root {
      --bg: #0e1116; --bg-2: #161b25; --bg-card: #1a1f2b; --bg-card-2: #232938;
      --border: #2b3344; --fg: #e7edf7; --muted: #94a3b8;
      --accent: #6366f1; --accent-2: #818cf8;
      --success: #10b981; --warn: #f59e0b; --danger: #ef4444; --info: #3b82f6;
    }
    body[data-theme="light"] {
      --bg: #f4f6fb; --bg-2: #ffffff; --bg-card: #ffffff; --bg-card-2: #f8fafc;
      --border: #e2e8f0; --fg: #0f172a; --muted: #64748b;
    }
    * { box-sizing: border-box; }
    html, body { background: var(--bg); color: var(--fg); margin: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; font-size: 14px; min-height: 100vh; }
    a { color: var(--accent-2); text-decoration: none; }
    a:hover { color: var(--accent); }

    .wy-sidebar { position: fixed; top: 0; left: 0; bottom: 0; width: 248px; background: var(--bg-2); border-right: 1px solid var(--border); overflow-y: auto; z-index: 100; transition: transform .2s ease; }
    .wy-sidebar.collapsed { transform: translateX(-200px); margin-right: -48px; }
    .wy-sidebar-header { padding: 18px 18px 14px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; }
    .wy-sidebar-header img { width: 32px; height: 32px; border-radius: 6px; }
    .wy-sidebar-header h1 { margin: 0; font-size: 15px; font-weight: 700; }
    .wy-sidebar-header small { color: var(--muted); display: block; font-size: 11px; }
    .wy-nav-group { padding: 14px 12px 6px; }
    .wy-nav-group-title { font-size: 10px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: var(--muted); padding: 0 8px 8px; }
    .wy-nav a { display: flex; align-items: center; gap: 10px; padding: 8px 10px; margin: 2px 0; border-radius: 7px; color: var(--fg); font-size: 13px; font-weight: 500; transition: background .15s ease; }
    .wy-nav a:hover { background: var(--bg-card); }
    .wy-nav a.active { background: var(--accent); color: white; }
    .wy-nav a.active i { color: white; }
    .wy-nav i { font-size: 16px; color: var(--muted); width: 18px; text-align: center; }
    .wy-nav a:hover i { color: var(--accent-2); }

    .wy-topbar { position: sticky; top: 0; margin-left: 248px; background: var(--bg-2); border-bottom: 1px solid var(--border); padding: 12px 24px; display: flex; align-items: center; gap: 12px; z-index: 50; }
    .wy-topbar .wy-toggle { background: transparent; border: 1px solid var(--border); color: var(--fg); width: 36px; height: 36px; border-radius: 7px; cursor: pointer; }
    .wy-topbar .wy-breadcrumb { font-size: 13px; color: var(--muted); margin: 0; }
    .wy-topbar .wy-breadcrumb .active { color: var(--fg); font-weight: 600; }
    .wy-topbar .wy-right { margin-left: auto; display: flex; align-items: center; gap: 10px; }

    .wy-main { margin-left: 248px; padding: 24px; min-height: 100vh; }
    .wy-sidebar.collapsed ~ .wy-main, .wy-sidebar.collapsed ~ .wy-topbar { margin-left: 48px; }

    .wy-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 18px; margin-bottom: 18px; }
    .wy-card h2, .wy-card h3 { color: var(--fg); }
    .wy-card-title { font-size: 16px; font-weight: 700; margin: 0 0 14px; display: flex; align-items: center; gap: 8px; }
    .wy-card-title i { color: var(--accent-2); }
    .wy-tile { display: block; background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 18px; color: var(--fg); transition: transform .12s ease, border-color .12s ease, background .12s ease; text-decoration: none; height: 100%; }
    .wy-tile:hover { transform: translateY(-2px); border-color: var(--accent); background: var(--bg-card-2); }
    .wy-tile i.wy-tile-icon { font-size: 24px; color: var(--accent-2); margin-bottom: 10px; display: block; }
    .wy-tile-title { font-weight: 600; font-size: 14px; margin-bottom: 4px; }
    .wy-tile-desc { color: var(--muted); font-size: 12px; line-height: 1.4; }

    .wy-form-control { background: var(--bg-2); border: 1px solid var(--border); color: var(--fg); border-radius: 7px; padding: 8px 10px; width: 100%; font-size: 13px; }
    .wy-form-control:focus { outline: 2px solid var(--accent); outline-offset: -1px; border-color: var(--accent); }
    .wy-form-label { font-size: 12px; font-weight: 600; margin-bottom: 6px; display: block; color: var(--fg); }
    .wy-form-help { font-size: 11px; color: var(--muted); margin-top: 4px; }

    .wy-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 7px; background: var(--accent); color: white; border: 0; cursor: pointer; font-size: 13px; font-weight: 500; }
    .wy-btn:hover { background: var(--accent-2); color: white; }
    .wy-btn.secondary { background: var(--bg-card-2); color: var(--fg); border: 1px solid var(--border); }
    .wy-btn.danger { background: var(--danger); }
    .wy-btn:disabled { opacity: .5; cursor: not-allowed; }

    .wy-flash { padding: 10px 14px; border-radius: 7px; margin-bottom: 14px; border: 1px solid var(--border); }
    .wy-flash-success { background: rgba(16, 185, 129, .15); border-color: var(--success); color: #a7f3d0; }
    .wy-flash-danger { background: rgba(239, 68, 68, .15); border-color: var(--danger); color: #fecaca; }
    .wy-flash-warning { background: rgba(245, 158, 11, .15); border-color: var(--warn); color: #fde68a; }
    .wy-flash-info { background: rgba(59, 130, 246, .15); border-color: var(--info); color: #bfdbfe; }

    .wy-table { width: 100%; border-collapse: collapse; }
    .wy-table th, .wy-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); font-size: 13px; }
    .wy-table th { color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; }
    .wy-table tbody tr:hover { background: var(--bg-card-2); }

    .wy-section-title { font-size: 22px; font-weight: 700; margin: 0 0 18px; }
    .wy-section-subtitle { color: var(--muted); margin: 0 0 24px; }

    .wy-theme-toggle { display: flex; gap: 4px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 7px; padding: 3px; }
    .wy-theme-toggle button { background: transparent; border: 0; color: var(--muted); padding: 4px 8px; border-radius: 5px; cursor: pointer; font-size: 12px; }
    .wy-theme-toggle button.active { background: var(--accent); color: white; }

    .wy-grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }
    .wy-grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
    .wy-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
    @media (max-width: 992px) { .wy-grid-4 { grid-template-columns: repeat(2, 1fr); } .wy-grid-3 { grid-template-columns: 1fr; } }
    @media (max-width: 600px)  { .wy-grid-2, .wy-grid-3, .wy-grid-4 { grid-template-columns: 1fr; } }

    @media (max-width: 992px) {
      .wy-sidebar { transform: translateX(-200px); margin-right: -48px; }
      .wy-sidebar.open { transform: translateX(0); margin-right: 0; }
      .wy-main, .wy-topbar { margin-left: 48px !important; }
    }
    .wy-mask { display: none; }
    .wy-mask.active { display: block; position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 90; }

    .wy-login-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, var(--bg) 0%, var(--bg-2) 100%); }
    .wy-login-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; padding: 32px; width: 100%; max-width: 380px; }
    .wy-stat { display: flex; gap: 14px; align-items: center; }
    .wy-stat-icon { width: 40px; height: 40px; border-radius: 8px; display: flex; align-items: center; justify-content: center; background: var(--accent); color: white; font-size: 18px; }
    .wy-stat-value { font-size: 22px; font-weight: 700; }
    .wy-stat-label { color: var(--muted); font-size: 12px; }
    .wy-pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; background: var(--bg-card-2); color: var(--muted); }
    .wy-pill.success { background: rgba(16,185,129,.18); color: var(--success); }
    .wy-pill.warn { background: rgba(245,158,11,.18); color: var(--warn); }
    .wy-pill.danger { background: rgba(239,68,68,.18); color: var(--danger); }
    .wy-toggle-switch { position: relative; display: inline-block; width: 42px; height: 24px; }
    .wy-toggle-switch input { opacity: 0; width: 0; height: 0; }
    .wy-toggle-slider { position: absolute; cursor: pointer; inset: 0; background-color: var(--border); border-radius: 24px; transition: .2s; }
    .wy-toggle-slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background-color: white; border-radius: 50%; transition: .2s; }
    input:checked + .wy-toggle-slider { background-color: var(--accent); }
    input:checked + .wy-toggle-slider:before { transform: translateX(18px); }
    .wy-tile-group-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2px; color: var(--muted); margin: 24px 0 10px; padding: 0 4px; }
    .wy-tile-group-title:first-child { margin-top: 0; }

    /* Light theme compatibility for legacy Bootstrap classes used in page bodies */
    .wy-main .form-control,
    .wy-main .form-select { background: var(--bg-2); color: var(--fg); border-color: var(--border); }
    .wy-main .form-control:focus,
    .wy-main .form-select:focus { background: var(--bg-2); color: var(--fg); border-color: var(--accent); }
    .wy-main .form-label { color: var(--fg); }
    .wy-main .table { color: var(--fg); }
    .wy-main .table > :not(caption) > * > * { background: transparent; color: var(--fg); border-bottom-color: var(--border); }
    .wy-main .modal-content { background: var(--bg-card); color: var(--fg); }
    .wy-main .btn-close { filter: invert(1) brightness(1.5); }
  </style>
</head>
<body data-theme="dark">
  {% set is_authed = session.get("user") %}
  {% set is_login_page = page in ["login", "forgot_password", "reset_password", "status_public", "public_status", "public_status_everything"] %}

  {% if is_login_page or not is_authed %}
    <div class="wy-main" style="margin-left:0; padding:0;">
      {% if page == "login" %}
        <div class="wy-login-page">
          <div class="wy-login-card">
            <div style="text-align:center; margin-bottom: 24px;">
              <img src="{{ url_for('static', filename='wicked-yoda-avatar.png') }}" alt="logo" style="width:64px;height:64px;border-radius:12px;margin-bottom:12px;">
              <h1 style="margin:0; font-size: 22px;">WickedYoda Admin</h1>
              <p style="color: var(--muted); margin: 4px 0 0; font-size: 13px;">Sign in to continue</p>
            </div>
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% for cat, msg in messages %}
                <div class="wy-flash wy-flash-{{ cat if cat in ['success','danger','warning'] else 'info' }}">{{ msg }}</div>
              {% endfor %}
            {% endwith %}
            <form method="post">
              <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
              <div style="margin-bottom: 14px;">
                <label class="wy-form-label" for="username">Email</label>
                <input class="wy-form-control" id="username" name="username" required autocomplete="username" autocapitalize="none" spellcheck="false">
              </div>
              <div style="margin-bottom: 14px;">
                <label class="wy-form-label" for="password">Password</label>
                <input class="wy-form-control" id="password" name="password" type="password" required autocomplete="current-password">
              </div>
              <div style="margin-bottom: 14px; display: flex; align-items: center; gap: 6px;">
                <input type="checkbox" id="remember_login" name="remember_login" value="1">
                <label for="remember_login" style="font-size: 12px; color: var(--muted);">Keep me signed in for 5 days</label>
              </div>
              <button class="wy-btn" type="submit" style="width:100%; justify-content:center;">Sign in</button>
            </form>
            {% if password_reset_enabled %}
            <div style="text-align:center; margin-top: 16px;">
              <a href="{{ url_for('forgot_password') }}" style="font-size: 12px;">Forgot your password?</a>
            </div>
            {% endif %}
          </div>
        </div>
      {% elif page == "forgot_password" %}
        <div class="wy-login-page">
          <div class="wy-login-card">
            <h1 style="margin:0 0 8px; font-size: 22px;">Reset Password</h1>
            <p style="color: var(--muted); font-size: 13px; margin-bottom: 20px;">Enter your email to receive a one-time reset link.</p>
            <form method="post" action="{{ url_for('forgot_password') }}">
              <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
              <div style="margin-bottom: 14px;">
                <label class="wy-form-label" for="forgot_email">Email</label>
                <input class="wy-form-control" id="forgot_email" name="email" type="email" required>
              </div>
              <button class="wy-btn" type="submit" style="width:100%; justify-content:center;">Send Reset Link</button>
            </form>
            <div style="text-align:center; margin-top: 16px;">
              <a href="{{ url_for('login') }}" style="font-size: 12px;">Back to login</a>
            </div>
          </div>
        </div>
      {% elif page == "reset_password" %}
        <div class="wy-login-page">
          <div class="wy-login-card">
            <h1 style="margin:0 0 16px; font-size: 22px;">Set New Password</h1>
            <p style="color: var(--muted); font-size: 13px; margin-bottom: 20px;">Account: <strong>{{ reset_email }}</strong></p>
            <form method="post" action="{{ url_for('password_reset_confirm', token=request.view_args.token) }}">
              <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
              <div style="margin-bottom: 14px;">
                <label class="wy-form-label" for="reset_new_password">New Password</label>
                <input class="wy-form-control" id="reset_new_password" name="new_password" type="password" required autocomplete="new-password">
              </div>
              <div style="margin-bottom: 14px;">
                <label class="wy-form-label" for="reset_confirm_new_password">Confirm Password</label>
                <input class="wy-form-control" id="reset_confirm_new_password" name="confirm_new_password" type="password" required autocomplete="new-password">
              </div>
              <button class="wy-btn" type="submit" style="width:100%; justify-content:center;">Set New Password</button>
            </form>
          </div>
        </div>
      {% else %}
        <div class="wy-main" style="margin-left:0;">
          <h1 class="wy-section-title">{{ title }}</h1>
          <div class="wy-card">
            {{ wy_page_body | safe if wy_page_body else "" }}
          </div>
        </div>
      {% endif %}
    </div>
  {% else %}
    <aside class="wy-sidebar" id="wySidebar">
      <div class="wy-sidebar-header">
        <img src="{{ url_for('static', filename='wicked-yoda-avatar.png') }}" alt="logo">
        <div>
          <h1>WickedYoda</h1>
          <small>{{ selected_guild_name or "Admin Console" }}</small>
        </div>
      </div>
      <div class="wy-nav-group">
        <div class="wy-nav-group-title">Overview</div>
        <nav class="wy-nav">
          <a href="{{ url_for('home') }}" class="{% if page == 'home' %}active{% endif %}"><i class="bi bi-house"></i> Home</a>
          <a href="{{ url_for('dashboard') }}" class="{% if page == 'dashboard' %}active{% endif %}"><i class="bi bi-speedometer2"></i> Dashboard</a>
          <a href="{{ url_for('status_page') }}" class="{% if page == 'status_admin' %}active{% endif %}"><i class="bi bi-activity"></i> Status</a>
          <a href="{{ url_for('observability') }}" class="{% if page == 'observability' %}active{% endif %}"><i class="bi bi-graph-up"></i> Observability</a>
        </nav>
      </div>
      <div class="wy-nav-group">
        <div class="wy-nav-group-title">Server</div>
        <nav class="wy-nav">
          <a href="{{ url_for('guilds_page') }}" class="{% if page == 'guilds' %}active{% endif %}"><i class="bi bi-hdd-rack"></i> Servers</a>
          <a href="{{ url_for('guild_settings') }}" class="{% if page == 'guild_settings' %}active{% endif %}"><i class="bi bi-gear"></i> Guild Settings</a>
          <a href="{{ url_for('command_permissions') }}" class="{% if page == 'command_permissions' %}active{% endif %}"><i class="bi bi-shield-check"></i> Command Permissions</a>
          <a href="{{ url_for('role_access') }}" class="{% if page == 'role_access' %}active{% endif %}"><i class="bi bi-person-badge"></i> Role Access</a>
        </nav>
      </div>
      <div class="wy-nav-group">
        <div class="wy-nav-group-title">Feeds</div>
        <nav class="wy-nav">
          <a href="{{ url_for('youtube_subscriptions') }}" class="{% if page == 'youtube' %}active{% endif %}"><i class="bi bi-youtube"></i> YouTube</a>
          <a href="{{ url_for('reddit_feeds') }}" class="{% if page == 'reddit' %}active{% endif %}"><i class="bi bi-reddit"></i> Reddit</a>
          <a href="{{ url_for('wordpress_feeds') }}" class="{% if page == 'wordpress' %}active{% endif %}"><i class="bi bi-wordpress"></i> WordPress</a>
          <a href="{{ url_for('linkedin_feeds') }}" class="{% if page == 'linkedin' %}active{% endif %}"><i class="bi bi-linkedin"></i> LinkedIn</a>
          <a href="{{ url_for('spicy_prompts') }}" class="{% if page == 'spicy_prompts' %}active{% endif %}"><i class="bi bi-fire"></i> Spicy Prompts</a>
        </nav>
      </div>
      <div class="wy-nav-group">
        <div class="wy-nav-group-title">Tools</div>
        <nav class="wy-nav">
          <a href="{{ url_for('uptime_monitors_page') }}" class="{% if page == 'uptime_monitors' %}active{% endif %}"><i class="bi bi-heart-pulse"></i> Uptime Monitors</a>
          <a href="{{ url_for('uptime_kuma_page') }}" class="{% if page in ['uptime_kuma','uptime_kuma_monitor_form'] %}active{% endif %}"><i class="bi bi-bar-chart"></i> Uptime Kuma</a>
          <a href="{{ url_for('translation_page') }}" class="{% if page == 'translation' %}active{% endif %}"><i class="bi bi-translate"></i> Auto-Translation</a>
          <a href="{{ url_for('honeypot') }}" class="{% if page == 'honeypot' %}active{% endif %}"><i class="bi bi-bug"></i> Honeypot</a>
          <a href="{{ url_for('reaction_roles') }}" class="{% if page == 'reaction_roles' %}active{% endif %}"><i class="bi bi-emoji-smile"></i> Reaction Roles</a>
        </nav>
      </div>
      <div class="wy-nav-group">
        <div class="wy-nav-group-title">Admin</div>
        <nav class="wy-nav">
          <a href="{{ url_for('tag_responses') }}" class="{% if page == 'tag_responses' %}active{% endif %}"><i class="bi bi-tags"></i> Tag Responses</a>
          <a href="{{ url_for('member_activity_page') }}" class="{% if page == 'member_activity' %}active{% endif %}"><i class="bi bi-people"></i> Member Activity</a>
          <a href="{{ url_for('random_user_page') }}" class="{% if page == 'random_user' %}active{% endif %}"><i class="bi bi-shuffle"></i> Random User</a>
          <a href="{{ url_for('actions') }}" class="{% if page == 'actions' %}active{% endif %}"><i class="bi bi-list-ul"></i> Action Log</a>
        </nav>
      </div>
      {% if session.get('is_admin') %}
      <div class="wy-nav-group">
        <div class="wy-nav-group-title">System</div>
        <nav class="wy-nav">
          <a href="{{ url_for('users') }}" class="{% if page == 'users' %}active{% endif %}"><i class="bi bi-people-fill"></i> Users</a>
          <a href="{{ url_for('guild_access') }}" class="{% if page == 'guild_access' %}active{% endif %}"><i class="bi bi-shield-lock"></i> Guild Access</a>
          <a href="{{ url_for('settings') }}" class="{% if page == 'settings' %}active{% endif %}"><i class="bi bi-sliders"></i> Global Settings</a>
          <a href="{{ url_for('logs') }}" class="{% if page == 'logs' %}active{% endif %}"><i class="bi bi-file-text"></i> Logs</a>
          <a href="{{ url_for('bot_profile') }}" class="{% if page == 'bot_profile' %}active{% endif %}"><i class="bi bi-robot"></i> Bot Profile</a>
        </nav>
      </div>
      {% endif %}
      <div class="wy-nav-group">
        <div class="wy-nav-group-title">Account</div>
        <nav class="wy-nav">
          <a href="{{ url_for('account') }}" class="{% if page == 'account' %}active{% endif %}"><i class="bi bi-person"></i> My Account</a>
          <a href="{{ url_for('documentation') }}" class="{% if page in ['documentation','wiki'] %}active{% endif %}"><i class="bi bi-book"></i> Docs</a>
          <a href="{{ url_for('logout') }}"><i class="bi bi-box-arrow-right"></i> Logout</a>
        </nav>
      </div>
    </aside>

    <div class="wy-mask" id="wyMask" onclick="document.getElementById('wySidebar').classList.remove('open'); this.classList.remove('active');"></div>

    <div class="wy-topbar">
      <button class="wy-toggle" onclick="document.getElementById('wySidebar').classList.toggle('open'); document.getElementById('wyMask').classList.toggle('active');" title="Toggle sidebar"><i class="bi bi-list"></i></button>
      <nav class="wy-breadcrumb">
        <a href="{{ url_for('home') }}">Home</a>
        <span style="margin: 0 6px;">/</span>
        <span class="active">{{ title }}</span>
      </nav>
      <div class="wy-right">
        {% if guild_options %}
        <form method="post" action="{{ url_for('select_guild') }}" class="wy-form" style="margin:0;">
          <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
          <input type="hidden" name="next_endpoint" value="{{ request.endpoint or 'home' }}">
          <select class="wy-form-control" name="guild_id" onchange="this.form.submit()" style="width: 180px; padding: 6px 8px;">
            {% for guild in guild_options %}<option value="{{ guild.id }}" {% if selected_guild_id == guild.id %}selected{% endif %}>{{ guild.name }}</option>{% endfor %}
          </select>
        </form>
        {% endif %}
        <div class="wy-theme-toggle">
          <button data-theme-choice="dark" class="active" type="button" onclick="setTheme('dark')">Dark</button>
          <button data-theme-choice="light" type="button" onclick="setTheme('light')">Light</button>
          <button data-theme-choice="black" type="button" onclick="setTheme('black')">Black</button>
        </div>
      </div>
    </div>

    <main class="wy-main">
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% for cat, msg in messages %}
          <div class="wy-flash wy-flash-{{ cat if cat in ['success','danger','warning'] else 'info' }}">{{ msg }}</div>
        {% endfor %}
      {% endwith %}

      {% if page == "home" %}
        <h1 class="wy-section-title">Welcome back, {{ session.get('user', 'Admin') }}</h1>
        <p class="wy-section-subtitle">Snapshot of bot status, server health, and quick admin actions.</p>

        <div class="wy-grid-3" style="margin-bottom: 22px;">
          <div class="wy-card">
            <div class="wy-stat">
              <div class="wy-stat-icon" style="background: var(--success);"><i class="bi bi-check2"></i></div>
              <div>
                <div class="wy-stat-label">Bot status</div>
                <div class="wy-stat-value">{% if snapshot.bot_ready %}Online{% else %}Starting{% endif %}</div>
              </div>
            </div>
          </div>
          <div class="wy-card">
            <div class="wy-stat">
              <div class="wy-stat-icon" style="background: var(--info);"><i class="bi bi-hdd-rack"></i></div>
              <div>
                <div class="wy-stat-label">Servers</div>
                <div class="wy-stat-value">{{ snapshot.guild_count or 0 }}</div>
              </div>
            </div>
          </div>
          <div class="wy-card">
            <div class="wy-stat">
              <div class="wy-stat-icon" style="background: var(--accent);"><i class="bi bi-terminal"></i></div>
              <div>
                <div class="wy-stat-label">Commands synced</div>
                <div class="wy-stat-value">{{ snapshot.commands_synced or 0 }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="wy-tile-group-title">Server Configuration</div>
        <div class="wy-grid-3">
          <a href="{{ url_for('guild_settings') }}" class="wy-tile"><i class="bi bi-gear wy-tile-icon"></i><div class="wy-tile-title">Guild Settings</div><div class="wy-tile-desc">Log channels, moderation toggles, spicy prompts.</div></a>
          <a href="{{ url_for('command_permissions') }}" class="wy-tile"><i class="bi bi-shield-check wy-tile-icon"></i><div class="wy-tile-title">Command Permissions</div><div class="wy-tile-desc">Public, moderator, or per-role command access.</div></a>
          <a href="{{ url_for('role_access') }}" class="wy-tile"><i class="bi bi-person-badge wy-tile-icon"></i><div class="wy-tile-title">Role Access</div><div class="wy-tile-desc">Map roles to permissions for moderation.</div></a>
        </div>

        <div class="wy-tile-group-title">Feeds</div>
        <div class="wy-grid-4">
          <a href="{{ url_for('youtube_subscriptions') }}" class="wy-tile"><i class="bi bi-youtube wy-tile-icon"></i><div class="wy-tile-title">YouTube</div><div class="wy-tile-desc">Community posts & uploads.</div></a>
          <a href="{{ url_for('reddit_feeds') }}" class="wy-tile"><i class="bi bi-reddit wy-tile-icon"></i><div class="wy-tile-title">Reddit</div><div class="wy-tile-desc">Subreddit monitoring.</div></a>
          <a href="{{ url_for('wordpress_feeds') }}" class="wy-tile"><i class="bi bi-wordpress wy-tile-icon"></i><div class="wy-tile-title">WordPress</div><div class="wy-tile-desc">Blog post subscriptions.</div></a>
          <a href="{{ url_for('linkedin_feeds') }}" class="wy-tile"><i class="bi bi-linkedin wy-tile-icon"></i><div class="wy-tile-title">LinkedIn</div><div class="wy-tile-desc">Page post feeds.</div></a>
        </div>

        <div class="wy-tile-group-title">Tools</div>
        <div class="wy-grid-3">
          <a href="{{ url_for('uptime_monitors_page') }}" class="wy-tile"><i class="bi bi-heart-pulse wy-tile-icon"></i><div class="wy-tile-title">Uptime Monitors</div><div class="wy-tile-desc">HTTP/TCP/DNS/Docker health.</div></a>
          <a href="{{ url_for('uptime_kuma_page') }}" class="wy-tile"><i class="bi bi-bar-chart wy-tile-icon"></i><div class="wy-tile-title">Uptime Kuma</div><div class="wy-tile-desc">Manage Kuma monitors.</div></a>
          <a href="{{ url_for('translation_page') }}" class="wy-tile"><i class="bi bi-translate wy-tile-icon"></i><div class="wy-tile-title">Auto-Translation</div><div class="wy-tile-desc">Flag reactions, live channels, context menu.</div></a>
        </div>

        <div class="wy-tile-group-title">Admin</div>
        <div class="wy-grid-3">
          <a href="{{ url_for('users') }}" class="wy-tile"><i class="bi bi-people-fill wy-tile-icon"></i><div class="wy-tile-title">Users</div><div class="wy-tile-desc">Web admin accounts.</div></a>
          <a href="{{ url_for('logs') }}" class="wy-tile"><i class="bi bi-file-text wy-tile-icon"></i><div class="wy-tile-title">Logs</div><div class="wy-tile-desc">Container & web audit logs.</div></a>
          <a href="{{ url_for('account') }}" class="wy-tile"><i class="bi bi-person wy-tile-icon"></i><div class="wy-tile-title">My Account</div><div class="wy-tile-desc">Email, password, sessions.</div></a>
        </div>
      {% else %}
        <h1 class="wy-section-title">{{ title }}</h1>
        <div class="wy-card">
          {{ wy_page_body | safe if wy_page_body else "" }}
        </div>
      {% endif %}
    </main>
  {% endif %}

  <script>
    function setTheme(name) {
      document.body.dataset.theme = name;
      try { localStorage.setItem('wy-theme', name); } catch (e) {}
      document.querySelectorAll('.wy-theme-toggle button').forEach(b => { b.classList.toggle('active', b.dataset.themeChoice === name); });
    }
    (function() {
      try { const t = localStorage.getItem('wy-theme'); if (t) setTheme(t); } catch (e) {}
    })();
  </script>
</body>
</html>
"""
