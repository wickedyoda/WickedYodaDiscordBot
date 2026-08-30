"""WickedYoda Web Admin - GUI Variant 2.

Theme: "Command Center"
- Top bar (no sidebar). Compact, dense, info-first.
- Top bar has: search box, quick-action palette (Ctrl+K), server selector, theme
- Home page is a single scrolling page with collapsible accordion sections grouped by
  domain (Bot, Servers, Feeds, Tools, Admin). Each section is a grid of clickable
  tiles with status indicators.
- Login page uses a centered card on a darker background.
- All non-home pages render their legacy body content inside a top-bar shell.
"""

from __future__ import annotations

PAGE_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="csrf-token" content="{{ csrf_token }}">
  <title>{{ title }} · WickedYoda</title>
  <link rel="icon" href="{{ url_for('static', filename='wicked-yoda-favicon.png') }}">
  <link rel="apple-touch-icon" sizes="180x180" href="{{ url_for('static', filename='wicked-yoda-avatar.png') }}">
  <link property="og:image" content="{{ url_for('static', filename='wicked-yoda-avatar.png') }}">
  <meta name="twitter:image" content="{{ url_for('static', filename='wicked-yoda-avatar.png') }}">
  {% if page == "status_public" and status_refresh_seconds and status_refresh_seconds > 0 %}
  <meta http-equiv="refresh" content="{{ status_refresh_seconds }}">
  {% endif %}
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet">
  <style>
    :root {
      --bg: #0a0d12; --bg-2: #11151c; --bg-3: #1a1f2a;
      --fg: #e7edf7; --muted: #93a3b8; --border: #2a3142;
      --accent: #38bdf8; --accent-2: #7dd3fc;
      --success: #4ade80; --warn: #fbbf24; --danger: #f87171; --info: #60a5fa;
    }
    body[data-theme="light"] {
      --bg: #f8fafc; --bg-2: #ffffff; --bg-3: #f1f5f9;
      --fg: #0f172a; --muted: #64748b; --border: #e2e8f0;
    }
    body[data-theme="black"] {
      --bg: #000000; --bg-2: #050505; --bg-3: #0a0a0a;
      --fg: #ffffff; --muted: #d1d5db; --border: #334155;
      --accent: #38bdf8; --accent-2: #7dd3fc;
      --success: #4ade80; --warn: #fbbf24; --danger: #f87171; --info: #60a5fa;
    }
    body[data-theme="black"] .cc-card,
    body[data-theme="black"] .cc-accordion,
    body[data-theme="black"] .cc-table,
    body[data-theme="black"] .cc-form-control {
      background: var(--bg-2);
      color: var(--fg);
      border-color: var(--border);
    }
    body[data-theme="black"] .cc-table th,
    body[data-theme="black"] .cc-table td {
      color: var(--fg);
      border-color: var(--border);
    }
    body[data-theme="black"] .text-body-secondary,
    body[data-theme="black"] .table-secondary,
    body[data-theme="black"] .table-active {
      color: #e2e8f0 !important;
      background-color: #1e293b !important;
    }
    body[data-theme="black"] input:disabled,
    body[data-theme="black"] textarea:disabled,
    body[data-theme="black"] select:disabled,
    body[data-theme="black"] option:disabled {
      color: #94a3b8 !important;
      background-color: #0f172a !important;
    }
    * { box-sizing: border-box; }
    html, body { background: var(--bg); color: var(--fg); margin: 0; }
    body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 14px; min-height: 100vh; }
    a { color: var(--accent-2); text-decoration: none; }
    a:hover { color: var(--accent); }

    .cc-topbar {
      position: sticky; top: 0; z-index: 100;
      background: var(--bg-2); border-bottom: 1px solid var(--border);
      padding: 10px 18px;
      display: flex; align-items: center; gap: 14px;
    }
    .cc-topbar .cc-brand { display: flex; align-items: center; gap: 8px; font-weight: 700; }
    .cc-topbar .cc-brand img { width: 26px; height: 26px; border-radius: 6px; }
    .cc-topbar .cc-brand a { color: var(--fg); }
    .cc-topbar .cc-search {
      flex: 1; max-width: 480px;
      display: flex; align-items: center; gap: 6px;
      background: var(--bg-3); border: 1px solid var(--border);
      border-radius: 8px; padding: 6px 10px;
    }
    .cc-topbar .cc-search i { color: var(--muted); }
    .cc-topbar .cc-search input {
      background: transparent; border: 0; color: var(--fg); outline: none;
      flex: 1; font-size: 13px;
    }
    .cc-topbar .cc-search kbd {
      background: var(--bg-2); border: 1px solid var(--border);
      padding: 1px 5px; border-radius: 4px; font-size: 11px; color: var(--muted);
    }
    .cc-topbar .cc-right { display: flex; align-items: center; gap: 10px; margin-left: auto; }

    .cc-palette-toggle {
      background: var(--bg-3); border: 1px solid var(--border); color: var(--fg);
      padding: 6px 10px; border-radius: 8px; cursor: pointer; font-size: 12px;
      display: flex; align-items: center; gap: 6px;
    }
    .cc-palette-toggle:hover { background: var(--accent); color: white; border-color: var(--accent); }

    .cc-main { padding: 24px; max-width: 1400px; margin: 0 auto; }
    .cc-section { background: var(--bg-2); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 18px; overflow: hidden; }
    .cc-section-header {
      display: flex; align-items: center; gap: 10px;
      padding: 14px 18px; cursor: pointer; user-select: none;
      background: var(--bg-2); border-bottom: 1px solid var(--border);
    }
    .cc-section-header:hover { background: var(--bg-3); }
    .cc-section-header h2 { margin: 0; font-size: 14px; font-weight: 700; letter-spacing: .3px; flex: 1; }
    .cc-section-header .cc-pill { font-size: 11px; color: var(--muted); }
    .cc-section-header .cc-chevron { transition: transform .2s; }
    .cc-section.collapsed .cc-chevron { transform: rotate(-90deg); }
    .cc-section.collapsed .cc-section-body { display: none; }
    .cc-section-body { padding: 14px 18px 18px; }

    .cc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
    .cc-tile {
      display: block; padding: 12px 14px;
      background: var(--bg-3); border: 1px solid var(--border); border-radius: 8px;
      color: var(--fg); transition: border-color .12s ease, transform .12s ease, background .12s ease;
      text-decoration: none;
    }
    .cc-tile:hover { border-color: var(--accent); transform: translateY(-1px); background: var(--bg-2); }
    .cc-tile-title { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 13px; }
    .cc-tile-title i { color: var(--accent-2); }
    .cc-tile-desc { font-size: 12px; color: var(--muted); margin-top: 4px; line-height: 1.4; }
    .cc-tile-status { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--success); margin-left: auto; }
    .cc-tile-status.warn { background: var(--warn); }
    .cc-tile-status.danger { background: var(--danger); }
    .cc-tile-status.muted { background: var(--muted); }

    .cc-form-control, .cc-main .form-control, .cc-main .form-select {
      background: var(--bg-2); color: var(--fg); border: 1px solid var(--border);
    }
    .cc-form-control:focus, .cc-main .form-control:focus, .cc-main .form-select:focus {
      background: var(--bg-2); color: var(--fg); border-color: var(--accent);
      box-shadow: 0 0 0 2px rgba(56, 189, 248, .15);
    }
    .cc-form-label, .cc-main .form-label { color: var(--fg); }
    .cc-main .table { color: var(--fg); }
    .cc-main .table > :not(caption) > * > * { background: transparent; color: var(--fg); border-bottom-color: var(--border); }
    .cc-main .modal-content { background: var(--bg-2); color: var(--fg); }

    .cc-btn, .cc-main .btn-primary { background: var(--accent); border-color: var(--accent); color: #001520; }
    .cc-btn:hover, .cc-main .btn-primary:hover { background: var(--accent-2); border-color: var(--accent-2); }
    .cc-btn-secondary, .cc-main .btn-secondary { background: var(--bg-3); color: var(--fg); border-color: var(--border); }
    .cc-btn-danger, .cc-main .btn-danger { background: var(--danger); border-color: var(--danger); }

    .cc-flash { padding: 10px 14px; border-radius: 8px; margin-bottom: 14px; border: 1px solid var(--border); }
    .cc-flash-success { background: rgba(74, 222, 128, .1); border-color: var(--success); color: #bbf7d0; }
    .cc-flash-danger { background: rgba(248, 113, 113, .1); border-color: var(--danger); color: #fecaca; }
    .cc-flash-warning { background: rgba(251, 191, 36, .1); border-color: var(--warn); color: #fde68a; }
    .cc-flash-info { background: rgba(96, 165, 250, .1); border-color: var(--info); color: #bfdbfe; }

    /* Command palette */
    .cc-palette {
      position: fixed; inset: 0; z-index: 200;
      background: rgba(0, 0, 0, .55); display: none;
      align-items: flex-start; justify-content: center; padding-top: 12vh;
    }
    .cc-palette.open { display: flex; }
    .cc-palette-inner {
      background: var(--bg-2); border: 1px solid var(--border);
      border-radius: 12px; width: 580px; max-width: 92vw; max-height: 60vh; overflow: hidden;
      box-shadow: 0 20px 60px rgba(0, 0, 0, .5);
      display: flex; flex-direction: column;
    }
    .cc-palette-input {
      width: 100%; padding: 14px 16px; background: transparent; border: 0; border-bottom: 1px solid var(--border);
      color: var(--fg); font-size: 16px; outline: none;
    }
    .cc-palette-list { overflow-y: auto; flex: 1; }
    .cc-palette-item {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 16px; cursor: pointer; color: var(--fg); text-decoration: none;
    }
    .cc-palette-item:hover, .cc-palette-item.active { background: var(--accent); color: #001520; }
    .cc-palette-item:hover i, .cc-palette-item.active i { color: #001520; }
    .cc-palette-item i { color: var(--accent-2); width: 18px; }
    .cc-palette-empty { padding: 24px; text-align: center; color: var(--muted); }

    .cc-stat-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }
    .cc-stat {
      flex: 1; min-width: 160px; background: var(--bg-2); border: 1px solid var(--border);
      border-radius: 10px; padding: 14px 18px;
    }
    .cc-stat-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }
    .cc-stat-value { font-size: 24px; font-weight: 700; margin-top: 4px; }

    .cc-section-title { font-size: 18px; font-weight: 700; margin: 0 0 12px; }
    .cc-section-desc { color: var(--muted); font-size: 13px; margin: 0 0 18px; }

    .cc-theme-toggle { display: flex; gap: 4px; background: var(--bg-3); border: 1px solid var(--border); border-radius: 7px; padding: 3px; }
    .cc-theme-toggle button { background: transparent; border: 0; color: var(--muted); padding: 4px 8px; border-radius: 5px; cursor: pointer; font-size: 12px; }
    .cc-theme-toggle button.active { background: var(--accent); color: #001520; }

    .cc-login-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: radial-gradient(ellipse at top, #1a2030 0%, #0a0d12 60%); }
    .cc-login-card { background: var(--bg-2); border: 1px solid var(--border); border-radius: 12px; padding: 32px; width: 100%; max-width: 380px; }
  </style>
</head>
<body data-theme="dark">
  {% set is_authed = session.get("user") %}
  {% set is_login_page = page in ["login", "forgot_password", "reset_password", "status_public", "public_status", "public_status_everything"] %}

  {% if is_login_page or not is_authed %}
    <div style="margin:0; padding:0;">
      {% if page == "login" %}
        <div class="cc-login-page">
          <div class="cc-login-card">
            <div style="text-align:center; margin-bottom: 24px;">
              <img src="{{ url_for('static', filename='wicked-yoda-avatar.png') }}" alt="logo" style="width:60px;height:60px;border-radius:12px;margin-bottom:10px;">
              <h1 style="margin:0; font-size: 20px;">WickedYoda</h1>
              <p style="color: var(--muted); margin: 4px 0 0; font-size: 12px;">Admin login</p>
            </div>
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% for cat, msg in messages %}
                <div class="cc-flash cc-flash-{{ cat if cat in ['success','danger','warning'] else 'info' }}">{{ msg }}</div>
              {% endfor %}
            {% endwith %}
            <form method="post">
              <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
              <div style="margin-bottom: 12px;">
                <label class="form-label" for="username" style="font-size: 12px;">Email</label>
                <input class="form-control" id="username" name="username" required autocomplete="username" autocapitalize="none" spellcheck="false" style="background: var(--bg-3); color: var(--fg); border-color: var(--border);">
              </div>
              <div style="margin-bottom: 12px;">
                <label class="form-label" for="password" style="font-size: 12px;">Password</label>
                <input class="form-control" id="password" name="password" type="password" required autocomplete="current-password" style="background: var(--bg-3); color: var(--fg); border-color: var(--border);">
              </div>
              <div style="margin-bottom: 12px; display: flex; align-items: center; gap: 6px;">
                <input type="checkbox" id="remember_login" name="remember_login" value="1">
                <label for="remember_login" style="font-size: 12px; color: var(--muted);">Keep me signed in for 5 days</label>
              </div>
              <button class="btn btn-primary w-100" type="submit">Sign in</button>
            </form>
            {% if password_reset_enabled %}
            <div style="text-align:center; margin-top: 16px;">
              <a href="{{ url_for('forgot_password') }}" style="font-size: 12px;">Forgot your password?</a>
            </div>
            {% endif %}
          </div>
        </div>
      {% elif page == "forgot_password" %}
        <div class="cc-login-page">
          <div class="cc-login-card">
            <h1 style="margin:0 0 8px; font-size: 20px;">Reset Password</h1>
            <p style="color: var(--muted); font-size: 12px; margin-bottom: 18px;">Enter your email to receive a one-time reset link.</p>
            <form method="post" action="{{ url_for('forgot_password') }}">
              <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
              <div style="margin-bottom: 12px;">
                <label class="form-label" for="forgot_email" style="font-size: 12px;">Email</label>
                <input class="form-control" id="forgot_email" name="email" type="email" required style="background: var(--bg-3); color: var(--fg); border-color: var(--border);">
              </div>
              <button class="btn btn-primary w-100" type="submit">Send Reset Link</button>
            </form>
            <div style="text-align:center; margin-top: 16px;">
              <a href="{{ url_for('login') }}" style="font-size: 12px;">Back to login</a>
            </div>
          </div>
        </div>
      {% elif page == "reset_password" %}
        <div class="cc-login-page">
          <div class="cc-login-card">
            <h1 style="margin:0 0 14px; font-size: 20px;">Set New Password</h1>
            <p style="color: var(--muted); font-size: 12px; margin-bottom: 18px;">Account: <strong>{{ reset_email }}</strong></p>
            <form method="post" action="{{ url_for('password_reset_confirm', token=request.view_args.token) }}">
              <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
              <div style="margin-bottom: 12px;">
                <label class="form-label" for="reset_new_password" style="font-size: 12px;">New Password</label>
                <input class="form-control" id="reset_new_password" name="new_password" type="password" required autocomplete="new-password" style="background: var(--bg-3); color: var(--fg); border-color: var(--border);">
              </div>
              <div style="margin-bottom: 12px;">
                <label class="form-label" for="reset_confirm_new_password" style="font-size: 12px;">Confirm</label>
                <input class="form-control" id="reset_confirm_new_password" name="confirm_new_password" type="password" required autocomplete="new-password" style="background: var(--bg-3); color: var(--fg); border-color: var(--border);">
              </div>
              <button class="btn btn-primary w-100" type="submit">Set New Password</button>
            </form>
          </div>
        </div>
      {% else %}
        <div class="cc-main">
          <h1 class="cc-section-title">{{ title }}</h1>
          <div class="cc-section">
            <div class="cc-section-body">
              {{ wy_page_body | safe if wy_page_body else "" }}
            </div>
          </div>
        </div>
      {% endif %}
    </div>
  {% else %}
    <div class="cc-topbar">
      <div class="cc-brand">
        <img src="{{ url_for('static', filename='wicked-yoda-avatar.png') }}" alt="logo">
        <a href="{{ url_for('home') }}">WickedYoda</a>
      </div>
      <div class="cc-search" onclick="document.getElementById('ccPaletteInput').focus()">
        <i class="bi bi-search"></i>
        <input id="ccPaletteInput" type="text" placeholder="Search or jump to..." readonly onclick="openPalette()" style="cursor:pointer;">
        <kbd>Ctrl+K</kbd>
      </div>
      {% if guild_options %}
      <form method="post" action="{{ url_for('select_guild') }}" style="margin:0;">
        <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
        <input type="hidden" name="next_endpoint" value="{{ request.endpoint or 'home' }}">
        <select class="form-select form-select-sm" name="guild_id" onchange="this.form.submit()" style="background: var(--bg-3); color: var(--fg); border-color: var(--border); min-width: 160px;">
          {% for guild in guild_options %}
          <option value="{{ guild.id }}" {% if selected_guild_id == guild.id %}selected{% endif %}>{{ guild.name }}</option>
          {% endfor %}
        </select>
      </form>
      {% endif %}
      <div class="cc-theme-toggle">
        <button data-theme-choice="dark" class="active" type="button" onclick="setTheme('dark')">Dark</button>
        <button data-theme-choice="light" type="button" onclick="setTheme('light')">Light</button>
        <button data-theme-choice="black" type="button" onclick="setTheme('black')">Black</button>
      </div>
      <div class="cc-right">
        <a href="{{ url_for('account') }}" style="color: var(--muted); font-size: 12px;"><i class="bi bi-person-circle"></i> {{ session.get('user', '') }}</a>
        <a href="{{ url_for('logout') }}" style="color: var(--muted); font-size: 12px;" title="Logout"><i class="bi bi-box-arrow-right"></i></a>
      </div>
    </div>

    <!-- Command palette -->
    <div class="cc-palette" id="ccPalette" onclick="if (event.target.id === 'ccPalette') closePalette();">
      <div class="cc-palette-inner">
        <input type="text" class="cc-palette-input" id="ccPaletteInput2" placeholder="Type a command or page name..." oninput="filterPalette(this.value)" autocomplete="off">
        <div class="cc-palette-list" id="ccPaletteList">
          <!-- populated by JS -->
        </div>
      </div>
    </div>

    <main class="cc-main">
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% for cat, msg in messages %}
          <div class="cc-flash cc-flash-{{ cat if cat in ['success','danger','warning'] else 'info' }}">{{ msg }}</div>
        {% endfor %}
      {% endwith %}

      {% if page == "home" %}
        <h1 class="cc-section-title">Command Center</h1>
        <p class="cc-section-desc">All admin areas for <strong>{{ selected_guild_name or "this server" }}</strong>. Click any section header to expand or collapse.</p>

        <div class="cc-stat-row">
          <div class="cc-stat">
            <div class="cc-stat-label">Bot status</div>
            <div class="cc-stat-value">{% if snapshot.bot_ready %}Online{% else %}Starting{% endif %}</div>
          </div>
          <div class="cc-stat">
            <div class="cc-stat-label">Servers</div>
            <div class="cc-stat-value">{{ snapshot.guild_count or 0 }}</div>
          </div>
          <div class="cc-stat">
            <div class="cc-stat-label">Commands synced</div>
            <div class="cc-stat-value">{{ snapshot.commands_synced or 0 }}</div>
          </div>
        </div>

        {% set sections = [
          ("Bot Operations", "bi-robot", "Bot Operations", [
            ("home", "Home", "bi-house", "Dashboard & status", "success"),
            ("status_page", "Status", "bi-activity", "Live health summary", "success"),
            ("observability", "Observability", "bi-graph-up", "Process metrics & IO", "muted"),
            ("bot_profile", "Bot Profile", "bi-person-badge", "Username, avatar, nickname", "muted"),
            ("logs", "Logs", "bi-file-text", "Container & web audit", "muted"),
          ]),
          ("Servers & Permissions", "bi-hdd-rack", "Servers & Permissions", [
            ("guilds_page", "Servers", "bi-hdd-rack", "Manage connected servers", "muted"),
            ("guild_settings", "Guild Settings", "bi-gear", "Log channels, moderation", "muted"),
            ("command_permissions", "Command Permissions", "bi-shield-check", "Public / mod / per-role", "muted"),
            ("role_access", "Role Access", "bi-person-badge", "Role-based gating", "muted"),
            ("guild_access", "Guild Access", "bi-shield-lock", "Web admin guild ACL", "muted"),
          ]),
          ("Feeds & Integrations", "bi-broadcast", "Feeds & Integrations", [
            ("youtube_subscriptions", "YouTube", "bi-youtube", "Community posts & uploads", "muted"),
            ("reddit_feeds", "Reddit", "bi-reddit", "Subreddit monitoring", "muted"),
            ("wordpress_feeds", "WordPress", "bi-wordpress", "Blog post feeds", "muted"),
            ("linkedin_feeds", "LinkedIn", "bi-linkedin", "Page post feeds", "muted"),
            ("spicy_prompts", "Spicy Prompts", "bi-fire", "Content packs & sync", "muted"),
          ]),
          ("Tools", "bi-tools", "Tools", [
            ("uptime_monitors_page", "Uptime Monitors", "bi-heart-pulse", "HTTP/TCP/DNS/Docker checks", "muted"),
            ("uptime_kuma_page", "Uptime Kuma", "bi-bar-chart", "Manage Kuma monitors", "muted"),
            ("translation_page", "Auto-Translation", "bi-translate", "Flag reactions, live channels", "muted"),
            ("honeypot", "Honeypot", "bi-bug", "Trap channels & join guard", "warn"),
            ("reaction_roles", "Reaction Roles", "bi-emoji-smile", "Reaction-to-role mapping", "muted"),
          ]),
          ("Community & Data", "bi-people", "Community & Data", [
            ("tag_responses", "Tag Responses", "bi-tags", "Tag → response mapping", "muted"),
            ("member_activity_page", "Member Activity", "bi-people", "Leaderboards & exports", "muted"),
            ("random_user_page", "Random User", "bi-shuffle", "Pick a random member", "muted"),
            ("actions", "Action Log", "bi-list-ul", "All bot actions", "muted"),
          ]),
        ] %}
        {% if session.get('is_admin') %}
          {% set _sys = [
            ("users", "Users", "bi-people-fill", "Web admin accounts", "muted"),
            ("settings", "Global Settings", "bi-sliders", "Env-file backed settings", "muted"),
          ] %}
          {% set _dummy = sections.append(("System", "bi-cpu", "System", _sys)) %}
        {% endif %}

        {% for section in sections %}
          <section class="cc-section" id="ccSection-{{ loop.index }}">
            <div class="cc-section-header" onclick="document.getElementById('ccSection-{{ loop.index }}').classList.toggle('collapsed')">
              <i class="bi {{ section[1] }}"></i>
              <h2>{{ section[2] }}</h2>
              <span class="cc-pill">{{ section[3] | length }} item{% if section[3] | length != 1 %}s{% endif %}</span>
              <i class="bi bi-chevron-down cc-chevron"></i>
            </div>
            <div class="cc-section-body">
              <div class="cc-grid">
                {% for ep, label, icon, desc, status in section[3] %}
                  <a href="{{ url_for(ep) }}" class="cc-tile">
                    <div class="cc-tile-title"><i class="bi {{ icon }}"></i> {{ label }}<span class="cc-tile-status {{ status }}"></span></div>
                    <div class="cc-tile-desc">{{ desc }}</div>
                  </a>
                {% endfor %}
              </div>
            </div>
          </section>
        {% endfor %}
      {% else %}
        <h1 class="cc-section-title">{{ title }}</h1>
        <div class="cc-section">
          <div class="cc-section-body">
            {{ wy_page_body | safe if wy_page_body else "" }}
          </div>
        </div>
      {% endif %}
    </main>
  {% endif %}

  <script>
    function setTheme(name) {
      document.body.dataset.theme = name;
      try { localStorage.setItem('cc-theme', name); } catch (e) {}
      document.querySelectorAll('.cc-theme-toggle button').forEach(b => { b.classList.toggle('active', b.dataset.themeChoice === name); });
    }
    (function() { try { const t = localStorage.getItem('cc-theme'); if (t) setTheme(t); } catch (e) {} })();

    // Command palette
    const PALETTE = [
      { name: "Home", url: "{{ url_for('home') }}", icon: "bi-house" },
      { name: "Dashboard", url: "{{ url_for('dashboard') }}", icon: "bi-speedometer2" },
      { name: "Status", url: "{{ url_for('status_page') }}", icon: "bi-activity" },
      { name: "Observability", url: "{{ url_for('observability') }}", icon: "bi-graph-up" },
      { name: "Servers", url: "{{ url_for('guilds_page') }}", icon: "bi-hdd-rack" },
      { name: "Guild Settings", url: "{{ url_for('guild_settings') }}", icon: "bi-gear" },
      { name: "Command Permissions", url: "{{ url_for('command_permissions') }}", icon: "bi-shield-check" },
      { name: "Role Access", url: "{{ url_for('role_access') }}", icon: "bi-person-badge" },
      { name: "YouTube", url: "{{ url_for('youtube_subscriptions') }}", icon: "bi-youtube" },
      { name: "Reddit", url: "{{ url_for('reddit_feeds') }}", icon: "bi-reddit" },
      { name: "WordPress", url: "{{ url_for('wordpress_feeds') }}", icon: "bi-wordpress" },
      { name: "LinkedIn", url: "{{ url_for('linkedin_feeds') }}", icon: "bi-linkedin" },
      { name: "Spicy Prompts", url: "{{ url_for('spicy_prompts') }}", icon: "bi-fire" },
      { name: "Uptime Monitors", url: "{{ url_for('uptime_monitors_page') }}", icon: "bi-heart-pulse" },
      { name: "Uptime Kuma", url: "{{ url_for('uptime_kuma_page') }}", icon: "bi-bar-chart" },
      { name: "Auto-Translation", url: "{{ url_for('translation_page') }}", icon: "bi-translate" },
      { name: "Honeypot", url: "{{ url_for('honeypot') }}", icon: "bi-bug" },
      { name: "Reaction Roles", url: "{{ url_for('reaction_roles') }}", icon: "bi-emoji-smile" },
      { name: "Tag Responses", url: "{{ url_for('tag_responses') }}", icon: "bi-tags" },
      { name: "Member Activity", url: "{{ url_for('member_activity_page') }}", icon: "bi-people" },
      { name: "Random User", url: "{{ url_for('random_user_page') }}", icon: "bi-shuffle" },
      { name: "Action Log", url: "{{ url_for('actions') }}", icon: "bi-list-ul" },
      { name: "Logs", url: "{{ url_for('logs') }}", icon: "bi-file-text" },
      { name: "My Account", url: "{{ url_for('account') }}", icon: "bi-person" },
      { name: "Docs", url: "{{ url_for('documentation') }}", icon: "bi-book" },
    ];
    function openPalette() {
      document.getElementById('ccPalette').classList.add('open');
      setTimeout(() => document.getElementById('ccPaletteInput2').focus(), 50);
    }
    function closePalette() {
      document.getElementById('ccPalette').classList.remove('open');
    }
    function filterPalette(q) {
      q = (q || '').toLowerCase();
      const filtered = PALETTE.filter(p => p.name.toLowerCase().includes(q));
      const list = document.getElementById('ccPaletteList');
      if (!filtered.length) {
        list.innerHTML = '<div class="cc-palette-empty">No matches</div>';
        return;
      }
      list.innerHTML = filtered.map(p =>
        '<a class="cc-palette-item" href="' + p.url + '"><i class="bi ' + p.icon + '"></i>' + p.name + '</a>'
      ).join('');
    }
    filterPalette('');
    document.addEventListener('keydown', function(e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (document.getElementById('ccPalette').classList.contains('open')) closePalette();
        else openPalette();
      } else if (e.key === 'Escape') {
        closePalette();
      }
    });
  </script>
</body>
</html>
"""
