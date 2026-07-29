PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="csrf-token" content="{{ csrf_token }}">
  <title>{{ title }}</title>
  <link rel="icon" href="{{ url_for('static', filename='wicked-yoda-favicon.png') }}">
  <link rel="apple-touch-icon" sizes="180x180" href="{{ url_for('static', filename='wicked-yoda-avatar.png') }}">
  <meta property="og:image" content="{{ url_for('static', filename='wicked-yoda-avatar.png') }}">
  <meta name="twitter:image" content="{{ url_for('static', filename='wicked-yoda-avatar.png') }}">
  {% if page == "status_public" and status_refresh_seconds and status_refresh_seconds > 0 %}
  <meta http-equiv="refresh" content="{{ status_refresh_seconds }}">
  {% endif %}
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    * { box-sizing: border-box; }
    html { -webkit-text-size-adjust: 100%; }
    :root {
      --bg: #0a0a0a;
      --bg-grad-a: #101010;
      --bg-grad-b: #141923;
      --fg: #e7edf7;
      --muted: #94a3b8;
      --card: #12161d;
      --border: #243047;
      --header: #06070a;
      --link: #7cc4ff;
      --btn-bg: #2563eb;
      --btn-secondary: #374151;
      --btn-danger: #dc2626;
      --flash-err-bg: #3b1318;
      --flash-err-fg: #fecaca;
      --flash-ok-bg: #102c1c;
      --flash-ok-fg: #bbf7d0;
      --input-bg: #0f141d;
      --input-fg: #e7edf7;
    }
    body[data-theme="light"] {
      --bg: #eef3fb;
      --bg-grad-a: #eef3fb;
      --bg-grad-b: #f8fbff;
      --fg: #1e293b;
      --muted: #64748b;
      --card: #ffffff;
      --border: #d6dee9;
      --header: #ffffff;
      --link: #1d4ed8;
      --btn-bg: #2563eb;
      --btn-secondary: #475569;
      --btn-danger: #dc2626;
      --flash-err-bg: #fee2e2;
      --flash-err-fg: #991b1b;
      --flash-ok-bg: #dcfce7;
      --flash-ok-fg: #166534;
      --input-bg: #ffffff;
      --input-fg: #1e293b;
    }
    body[data-theme="forest"] {
      --bg: #0b1511;
      --bg-grad-a: #102018;
      --bg-grad-b: #183329;
      --fg: #ecfdf5;
      --muted: #9ec7b2;
      --card: #11211a;
      --border: #24503d;
      --header: #09110d;
      --link: #86efac;
      --btn-bg: #15803d;
      --btn-secondary: #365346;
      --btn-danger: #b91c1c;
      --flash-err-bg: #3f1717;
      --flash-err-fg: #fecaca;
      --flash-ok-bg: #103522;
      --flash-ok-fg: #bbf7d0;
      --input-bg: #0f1a15;
      --input-fg: #ecfdf5;
    }
    body[data-theme="ember"] {
      --bg: #1a1010;
      --bg-grad-a: #241414;
      --bg-grad-b: #48221a;
      --fg: #fff4ec;
      --muted: #e4b8a0;
      --card: #241616;
      --border: #5c342b;
      --header: #140b0b;
      --link: #fdba74;
      --btn-bg: #ea580c;
      --btn-secondary: #6b463f;
      --btn-danger: #dc2626;
      --flash-err-bg: #491b1b;
      --flash-err-fg: #fecaca;
      --flash-ok-bg: #3a2411;
      --flash-ok-fg: #fde68a;
      --input-bg: #1d1111;
      --input-fg: #fff4ec;
    }
    body[data-theme="ice"] {
      --bg: #eef6fb;
      --bg-grad-a: #eef6fb;
      --bg-grad-b: #dbeafe;
      --fg: #102132;
      --muted: #4b6b84;
      --card: #f9fcff;
      --border: #bfd5e8;
      --header: #e9f4fb;
      --link: #0369a1;
      --btn-bg: #0284c7;
      --btn-secondary: #5b7a90;
      --btn-danger: #dc2626;
      --flash-err-bg: #fee2e2;
      --flash-err-fg: #991b1b;
      --flash-ok-bg: #d1fae5;
      --flash-ok-fg: #065f46;
      --input-bg: #ffffff;
      --input-fg: #102132;
    }
    body {
      font-family: "Trebuchet MS", "Lucida Sans", "Segoe UI", sans-serif;
      margin: 0;
      color: var(--fg);
      background:
        radial-gradient(1100px 450px at 20% -20%, var(--bg-grad-b), transparent 55%),
        radial-gradient(900px 360px at 100% 0%, #10213d, transparent 50%),
        var(--bg);
      min-height: 100vh;
      overflow-x: hidden;
    }
    a { color: var(--link); }
    header {
      background: var(--header);
      border-bottom: 1px solid var(--border);
      color: var(--fg);
      padding: 12px 18px;
      display: flex;
      flex-direction: column;
      align-items: stretch;
      gap: 14px;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .header-toprow { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
    .header-brand { min-width: 170px; }
    .header-brand strong { display: block; }
    .header-version {
      display: inline-block;
      margin-top: 4px;
      font-size: 0.82rem;
      color: var(--muted);
      letter-spacing: 0.02em;
    }
    .header-tools { display: flex; align-items: center; gap: 12px; margin-left: auto; }
    .header-right { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; justify-content: center; }
    .desktop-nav { display: flex; }
    .mobile-quickbar { display: none; }
    .nav-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: center; }
    .nav-controls a { text-decoration: none; }
    .current-user { color: var(--muted); font-size: 0.95rem; }
    .current-user-email { color: var(--muted); font-size: 0.85rem; }
    .header-chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 36px;
      padding: 7px 12px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.03);
      color: var(--fg);
      font-size: 0.88rem;
      line-height: 1.2;
    }
    .header-chip strong {
      font-size: 0.78rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .wrap { max-width: 1200px; margin: 22px auto; padding: 0 16px; }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px;
      margin-bottom: 16px;
    }
    .card-soft {
      border: 1px solid var(--border);
      background: var(--card);
      border-radius: 14px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
    }
    .flash { padding: 10px 12px; border-radius: 8px; margin-bottom: 10px; border: 1px solid var(--border); }
    .flash.error { background: var(--flash-err-bg); color: var(--flash-err-fg); }
    .flash.success { background: var(--flash-ok-bg); color: var(--flash-ok-fg); }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid var(--border); padding: 10px; text-align: left; vertical-align: top; }
    input[type=text], input[type=email], input[type=password], textarea, select, .form-control, .form-select {
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px;
      min-height: 44px;
      font-size: 16px;
      background: var(--input-bg);
      color: var(--input-fg);
    }
    textarea { min-height: 220px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .btn {
      background: var(--btn-bg);
      border: 0;
      color: #fff;
      padding: 9px 14px;
      border-radius: 8px;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
    }
    .btn.secondary { background: var(--btn-secondary); }
    .btn.danger { background: var(--btn-danger); }
    .btn-primary { background: var(--btn-bg); border-color: var(--btn-bg); }
    .btn-outline-secondary { border-color: var(--border); color: var(--fg); }
    .btn-outline-secondary:hover { background: var(--btn-secondary); border-color: var(--btn-secondary); color: #fff; }
    .inline-form { display: inline-flex; margin-left: 0; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .muted { color: var(--muted); font-size: 0.9rem; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .theme-switch { display: inline-flex; border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
    .theme-btn {
      border: 0;
      background: transparent;
      color: var(--fg);
      padding: 7px 11px;
      cursor: pointer;
      font-weight: 700;
      letter-spacing: 0.02em;
    }
    .theme-btn.active { background: var(--btn-bg); color: #fff; }
    .nav-select {
      width: 280px;
      max-width: 70vw;
      min-width: 190px;
      padding: 7px 9px;
    }
    .mobile-nav { display: none; position: relative; }
    .mobile-nav summary {
      list-style: none;
      cursor: pointer;
      user-select: none;
      min-height: 44px;
      padding: 10px 14px;
      border-radius: 10px;
      background: var(--btn-bg);
      color: #fff;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border: 0;
    }
    .mobile-nav summary::-webkit-details-marker { display: none; }
    .mobile-nav-panel {
      margin-top: 10px;
      padding: 14px;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: var(--card);
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.2);
      display: grid;
      gap: 12px;
    }
    .mobile-user-block {
      display: grid;
      gap: 4px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }
    .mobile-link-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .mobile-panel-section { display: grid; gap: 8px; }
    .mobile-panel-title {
      margin: 0;
      color: var(--muted);
      font-size: 0.76rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .mobile-link-grid .btn,
    .mobile-nav-panel .btn,
    .mobile-nav-panel .inline-form,
    .mobile-nav-panel .inline-form .btn,
    .mobile-nav-panel .nav-select {
      width: 100%;
    }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    .dash-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
    .dashboard-shell { display: grid; gap: 18px; }
    .dashboard-hero {
      display: grid;
      grid-template-columns: minmax(0, 1.7fr) minmax(280px, 1fr);
      gap: 16px;
      align-items: stretch;
    }
    .dashboard-hero-main,
    .dashboard-hero-side,
    .dashboard-section,
    .dash-card {
      position: relative;
      overflow: hidden;
    }
    .dashboard-hero-main::before,
    .dashboard-hero-side::before,
    .dash-card::before {
      content: "";
      position: absolute;
      inset: 0 auto auto 0;
      width: 100%;
      height: 3px;
      background: linear-gradient(90deg, var(--btn-bg), transparent 78%);
      opacity: 0.75;
      pointer-events: none;
    }
    .dashboard-hero-main h2,
    .dashboard-hero-side h3,
    .dashboard-section-head h3,
    .dash-card h3 {
      margin-top: 0;
    }
    .dashboard-hero-main p,
    .dashboard-hero-side p,
    .dash-card p {
      margin-top: 0;
    }
    .dashboard-hero-main {
      display: grid;
      gap: 14px;
      align-content: start;
      padding-top: 20px;
    }
    .dashboard-hero-lead {
      font-size: 1.02rem;
      line-height: 1.55;
      max-width: 58ch;
    }
    .dashboard-pill-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .dashboard-pill {
      display: grid;
      gap: 2px;
      min-width: 132px;
      padding: 11px 13px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.03);
    }
    .dashboard-pill strong {
      font-size: 0.74rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .dashboard-pill span {
      font-size: 0.96rem;
      font-weight: 700;
      line-height: 1.3;
    }
    .dashboard-hero-side {
      display: grid;
      gap: 14px;
      align-content: start;
      padding-top: 20px;
    }
    .dashboard-list {
      display: grid;
      gap: 10px;
    }
    .dashboard-list-item {
      display: grid;
      gap: 4px;
      padding: 11px 12px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.03);
    }
    .dashboard-list-item strong { font-size: 0.9rem; }
    .dashboard-section {
      display: grid;
      gap: 12px;
      padding-top: 18px;
    }
    .dashboard-section-head {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 12px;
    }
    .dashboard-section-head p {
      margin: 0;
      max-width: 70ch;
    }
    .dashboard-section-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 14px;
    }
    .dash-card {
      display: grid;
      gap: 12px;
      align-content: start;
      min-height: 100%;
      padding-top: 20px;
    }
    .dash-card h3 { margin-bottom: 2px; }
    .dash-card p { min-height: 0; line-height: 1.5; }
    .dash-card.primary {
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.03), transparent 48%), var(--card);
    }
    .dash-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: auto; }
    .dash-actions .btn { min-width: 0; }
    .dashboard-note {
      margin: 0;
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.45;
    }
    .table-wrap {
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      border-radius: 12px;
      border: 1px solid var(--border);
    }
    .table-wrap table { min-width: 640px; }
    .status-pill { text-transform: capitalize; }
    .go-page-select { min-width: 180px; max-width: 40vw; }
    .mobile-pre {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      word-break: break-word;
      max-height: 60vh;
      overflow: auto;
    }
    .documentation-sidebar {
      max-height: 56vh;
      overflow: auto;
    }
    .documentation-link {
      background: transparent;
      color: var(--fg);
      border-color: var(--border);
    }
    .documentation-link:hover {
      background: rgba(37, 99, 235, .08);
      color: var(--fg);
    }
    .documentation-link.active {
      background: var(--btn-bg);
      border-color: var(--btn-bg);
      color: #fff;
    }
    .documentation-link.active .text-secondary,
    .documentation-link.active .small {
      color: rgba(255, 255, 255, 0.78) !important;
    }
    .guild-context-card {
      display: flex;
      flex-direction: column;
      gap: 14px;
      margin-bottom: 16px;
    }
    .guild-context-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      flex-wrap: wrap;
    }
    .guild-context-meta {
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.5;
    }
    .guild-context-actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .guild-context-switch {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: end;
    }
    .collapsible-card {
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--card);
      overflow: hidden;
    }
    .collapsible-card > summary {
      list-style: none;
      cursor: pointer;
      padding: 14px 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      font-weight: 600;
    }
    .collapsible-card > summary::-webkit-details-marker { display: none; }
    .collapsible-card > summary::after {
      content: "+";
      color: var(--muted);
      font-size: 1.1rem;
      line-height: 1;
    }
    .collapsible-card[open] > summary::after { content: "−"; }
    .collapsible-card-body {
      border-top: 1px solid var(--border);
      padding: 16px;
    }
    .password-toggle-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-top: 8px;
    }
    @media (max-width: 1180px) {
      .dashboard-hero { grid-template-columns: 1fr; }
    }
    @media (max-width: 1024px) {
      .wrap { max-width: 960px; }
      .dashboard-section-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .dashboard-pill-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .dashboard-hero-main,
      .dashboard-hero-side,
      .dash-card { padding-top: 16px; }
      .nav-controls { gap: 8px; }
      .nav-select { width: 240px; }
    }
    @media (max-width: 1080px) { .dash-grid { grid-template-columns: 1fr 1fr; } }
    @media (max-width: 900px) {
      .grid { grid-template-columns: 1fr; }
      .dash-grid { grid-template-columns: 1fr; }
      .dashboard-section-head { align-items: start; flex-direction: column; }
      .dashboard-section-grid { grid-template-columns: 1fr 1fr; }
      .dashboard-pill-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
      header { padding: 10px 12px; align-items: center; }
      .wrap { margin: 14px auto; padding: 0 10px; }
      .card { padding: 14px; }
      .header-toprow { width: 100%; align-items: flex-start; }
      .header-tools { margin-left: 0; width: auto; flex-shrink: 0; }
      .header-right.desktop-nav { display: none; }
      .mobile-quickbar { display: grid; grid-template-columns: 1fr; gap: 10px; width: 100%; }
      .mobile-nav { display: block; width: 100%; }
      .nav-select { width: 100%; max-width: 100%; min-width: 0; }
      .theme-switch { width: 100%; }
      .header-tools .theme-switch { display: none; }
      .theme-btn { flex: 1; min-height: 42px; }
      .current-user-email { display: block; }
      .dash-actions .btn { width: 100%; }
      .dashboard-pill { min-width: 0; flex: 1 1 180px; }
      th, td { padding: 8px; }
      .guild-context-switch { grid-template-columns: 1fr; }
      .table-wrap > table { min-width: 600px; }
      .table-wrap table { min-width: 520px; }
      .mobile-pre { max-height: 48vh; font-size: .875rem; }
      .documentation-sidebar { max-height: none; }
    }
    @media (max-width: 600px) {
      .card { border-radius: 10px; }
      .table-wrap > table { min-width: 520px; }
      .header-toprow { flex-direction: column; align-items: stretch; }
      .header-tools { width: 100%; flex-direction: column; align-items: stretch; }
      .dashboard-section-grid { grid-template-columns: 1fr; }
      .dashboard-pill-row { display: grid; grid-template-columns: 1fr; }
      .dashboard-pill { min-width: 0; }
      .dashboard-pill span { font-size: 0.92rem; }
      .header-version { font-size: 0.74rem; }
      .mobile-link-grid { grid-template-columns: 1fr; }
      main.container { padding-top: 1rem !important; padding-bottom: 1.25rem !important; }
    }
  </style>
</head>
<body data-theme="black">
  <header>
    <div class="header-toprow">
      <div class="header-brand">
        <strong>Wicked Yoda Bot Admin</strong>
        <span class="header-version">{{ snapshot.server_time if snapshot and snapshot.server_time else "n/a" }}</span>
      </div>
      <div class="header-tools">
        {% if snapshot and snapshot.invite_url %}
        <a class="btn" href="{{ snapshot.invite_url }}" target="_blank" rel="noreferrer">Invite Bot</a>
        {% endif %}
        {% if session.get("user") %}
        <details class="mobile-nav">
          <summary>Menu</summary>
          <div class="mobile-nav-panel">
            <div class="mobile-user-block">
              <span class="current-user">{{ session.get("display_name") or session.get("user") }}{% if session.get("is_admin") %} (Admin){% elif session.get("is_guild_admin") %} (Guild Admin){% else %} (Read Only){% endif %}</span>
              {% if selected_guild_name %}<span class="current-user">Server: {{ selected_guild_name }}</span>{% endif %}
            </div>
            <div class="mobile-panel-section">
              <p class="mobile-panel-title">Quick Jump</p>
              <label class="sr-only" for="mobile-nav-page-select">Open page</label>
              <select id="mobile-nav-page-select" class="nav-select nav-page-select">
                <option value="">Go to page...</option>
                <option value="{{ url_for('dashboard') }}">Dashboard (Home)</option>
                <option value="{{ url_for('account') }}">Account</option>
                <option value="{{ url_for('overview') }}">Overview</option>
                <option value="{{ url_for('guilds_page') }}">Servers</option>
                <option value="{{ url_for('guild_settings') }}">Guild Settings</option>
                <option value="{{ url_for('moderation') }}">Moderation</option>
                <option value="{{ url_for('command_permissions') }}">Command Permissions</option>
                <option value="{{ url_for('bot_profile') }}">Bot Profile</option>
                <option value="{{ url_for('random_user_page') }}">Random User</option>
                <option value="{{ url_for('member_activity_page') }}">Member Activity</option>
                <option value="{{ url_for('actions') }}">Actions</option>
                <option value="{{ url_for('tag_responses') }}">Tag Responses</option>
                <option value="{{ url_for('spicy_prompts') }}">Spicy Prompts</option>
                <option value="{{ url_for('youtube_subscriptions') }}">YouTube</option>
                <option value="{{ url_for('reddit_feeds') }}">Reddit</option>
                <option value="{{ url_for('wordpress_feeds') }}">WordPress</option>
                <option value="{{ url_for('linkedin_feeds') }}">LinkedIn</option>
                <option value="{{ url_for('uptime_monitors_page') }}">Uptime Monitors</option>
                <option value="{{ url_for('status_page') }}">Status</option>
                <option value="{{ url_for('honeypot') }}">Honeypot</option>
                <option value="{{ url_for('role_access') }}">Role Access</option>
                <option value="{{ url_for('reaction_roles') }}">Reaction Roles</option>
                <option value="{{ url_for('discourse') }}">Discourse</option>
                {% if session.get("is_admin") %}
                <option value="{{ url_for('users') }}">Users</option>
                <option value="{{ url_for('guild_access') }}">Guild Access</option>
                <option value="{{ url_for('settings') }}">Settings (Global)</option>
                <option value="{{ url_for('observability') }}">Observability (Global)</option>
                <option value="{{ url_for('logs') }}">Logs (Global)</option>
                <option value="{{ url_for('documentation') }}">Documentation (Global)</option>
                {% endif %}
                <option value="{{ url_for('logout') }}">Logout</option>
              </select>
            </div>
            <div class="mobile-panel-section">
              <p class="mobile-panel-title">Primary Actions</p>
              <div class="mobile-link-grid">
                {% if snapshot and snapshot.invite_url %}
                <a class="btn" href="{{ snapshot.invite_url }}" target="_blank" rel="noreferrer">Invite Bot</a>
                {% endif %}
                <a class="btn secondary" href="{{ url_for('guilds_page') }}">Servers</a>
                <a class="btn secondary" href="{{ url_for('account') }}">My Account</a>
                <a class="btn secondary" href="{{ url_for('member_activity_page') }}">Member Activity</a>
                <a class="btn secondary" href="{{ url_for('dashboard') }}">Dashboard</a>
                <a class="btn secondary" href="{{ url_for('command_permissions') }}">Permissions</a>
                <a class="btn secondary" href="{{ url_for('guild_settings') }}">Settings</a>
                <a class="btn secondary" href="{{ url_for('logs') }}">Logs</a>
                <a class="btn secondary" href="{{ url_for('logout') }}">Logout</a>
              </div>
            </div>
            <div class="mobile-panel-section">
              <p class="mobile-panel-title">Theme</p>
              <div class="theme-switch" aria-label="Theme selector">
                <button type="button" class="theme-btn" data-theme-choice="light">Light</button>
                <button type="button" class="theme-btn" data-theme-choice="black">Black</button>
                <button type="button" class="theme-btn" data-theme-choice="forest">Forest</button>
                <button type="button" class="theme-btn" data-theme-choice="ember">Ember</button>
                <button type="button" class="theme-btn" data-theme-choice="ice">Ice</button>
              </div>
            </div>
          </div>
        </details>
        {% endif %}
        <div class="theme-switch" aria-label="Theme selector">
          <button type="button" class="theme-btn" data-theme-choice="light">Light</button>
          <button type="button" class="theme-btn" data-theme-choice="black">Black</button>
          <button type="button" class="theme-btn" data-theme-choice="forest">Forest</button>
          <button type="button" class="theme-btn" data-theme-choice="ember">Ember</button>
          <button type="button" class="theme-btn" data-theme-choice="ice">Ice</button>
        </div>
      </div>
    </div>
    {% if session.get("user") %}
    <div class="mobile-quickbar">
      <div class="header-chip">
        <strong>Server</strong>
        <span>{{ selected_guild_name or "No server selected" }}</span>
      </div>
      <div class="mobile-link-grid">
        {% if snapshot and snapshot.invite_url %}
        <a class="btn" href="{{ snapshot.invite_url }}" target="_blank" rel="noreferrer">Invite Bot</a>
        {% endif %}
        <a class="btn secondary" href="{{ url_for('guilds_page') }}">Servers</a>
        <a class="btn secondary" href="{{ url_for('account') }}">My Account</a>
        <a class="btn secondary" href="{{ url_for('member_activity_page') }}">Member Activity</a>
        <a class="btn secondary" href="{{ url_for('logout') }}">Logout</a>
        <a class="btn secondary" href="{{ url_for('dashboard') }}">Dashboard</a>
      </div>
    </div>
    {% endif %}
    <div class="header-right desktop-nav">
      {% if session.get("user") %}
        <nav class="nav-controls">
          <span class="current-user">{{ session.get("display_name") or session.get("user") }}{% if session.get("is_admin") %} (Admin){% elif session.get("is_guild_admin") %} (Guild Admin){% else %} (Read Only){% endif %}</span>
          {% if selected_guild_name %}<span class="current-user">Server: {{ selected_guild_name }}</span>{% endif %}
          {% if snapshot and snapshot.invite_url %}
          <a class="btn" href="{{ snapshot.invite_url }}" target="_blank" rel="noreferrer">Invite Bot</a>
          {% endif %}
          <a class="btn secondary" href="{{ url_for('guilds_page') }}">Servers</a>
          <a class="btn secondary" href="{{ url_for('dashboard') }}">Dashboard</a>
          <a class="btn secondary" href="{{ url_for('logout') }}">Logout</a>
          <label class="sr-only" for="desktop-nav-page-select">Open page</label>
          <select id="desktop-nav-page-select" class="nav-select nav-page-select">
            <option value="">Go to page...</option>
            <option value="{{ url_for('dashboard') }}">Dashboard (Home)</option>
            <option value="{{ url_for('account') }}">Account</option>
            <option value="{{ url_for('overview') }}">Overview</option>
            <option value="{{ url_for('guilds_page') }}">Servers</option>
            <option value="{{ url_for('guild_settings') }}">Guild Settings</option>
            <option value="{{ url_for('moderation') }}">Moderation</option>
            <option value="{{ url_for('command_permissions') }}">Command Permissions</option>
            <option value="{{ url_for('bot_profile') }}">Bot Profile</option>
            <option value="{{ url_for('random_user_page') }}">Random User</option>
            <option value="{{ url_for('member_activity_page') }}">Member Activity</option>
            <option value="{{ url_for('actions') }}">Actions</option>
            <option value="{{ url_for('tag_responses') }}">Tag Responses</option>
            <option value="{{ url_for('spicy_prompts') }}">Spicy Prompts</option>
            <option value="{{ url_for('youtube_subscriptions') }}">YouTube</option>
            <option value="{{ url_for('reddit_feeds') }}">Reddit</option>
            <option value="{{ url_for('wordpress_feeds') }}">WordPress</option>
            <option value="{{ url_for('linkedin_feeds') }}">LinkedIn</option>
            <option value="{{ url_for('uptime_monitors_page') }}">Uptime Monitors</option>
            <option value="{{ url_for('status_page') }}">Status</option>
            <option value="{{ url_for('honeypot') }}">Honeypot</option>
            <option value="{{ url_for('role_access') }}">Role Access</option>
            <option value="{{ url_for('reaction_roles') }}">Reaction Roles</option>
            <option value="{{ url_for('discourse') }}">Discourse</option>
            {% if session.get("is_admin") %}
            <option value="{{ url_for('users') }}">Users</option>
            <option value="{{ url_for('guild_access') }}">Guild Access</option>
            <option value="{{ url_for('settings') }}">Settings (Global)</option>
            <option value="{{ url_for('observability') }}">Observability (Global)</option>
            <option value="{{ url_for('logs') }}">Logs (Global)</option>
            <option value="{{ url_for('documentation') }}">Documentation (Global)</option>
            {% endif %}
            <option value="{{ url_for('logout') }}">Logout</option>
          </select>
          {% if guild_options %}
          <form method="post" action="{{ url_for('select_guild') }}" class="inline-form">
            <input type="hidden" name="next_endpoint" value="{{ 'documentation' if request.endpoint == 'documentation_page' else (request.endpoint or 'home') }}">
            <select class="nav-select" name="guild_id" onchange="this.form.submit()">
              {% for guild in guild_options %}
              <option value="{{ guild.id }}" {% if selected_guild_id == guild.id %}selected{% endif %}>{{ guild.name }}</option>
              {% endfor %}
            </select>
          </form>
          {% endif %}
        </nav>
      {% endif %}
    </div>
  </header>

  <main class="container wrap">
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

    {% if session.get("user") and guild_options %}
    <div class="card card-soft guild-context-card">
      <div class="guild-context-top">
        <div>
          <h1 class="h5 mb-1">{{ selected_guild_name or "No server selected" }}</h1>
          <div class="guild-context-meta">
            {% if selected_guild_id %}
            Guild ID: <code>{{ selected_guild_id }}</code><br>
            All guild-scoped options and actions on this page apply only to the selected guild.
            {% else %}
            Select a guild to manage per-server settings and moderation actions.
            {% endif %}
          </div>
        </div>
        {% if selected_guild_id %}
        <div class="guild-context-actions">
          <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('guilds_page') }}">Servers</a>
          <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('moderation') }}">Moderation</a>
          <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('guild_settings') }}">Guild Settings</a>
        </div>
        {% endif %}
      </div>
      <form method="post" action="{{ url_for('select_guild') }}" class="guild-context-switch">
        <div>
          <label class="form-label small mb-1" for="persistent-guild-switch">Switch Guild</label>
          <select id="persistent-guild-switch" name="guild_id" class="form-select form-select-sm">
            {% for guild in guild_options %}
            <option value="{{ guild.id }}" {% if selected_guild_id == guild.id %}selected{% endif %}>{{ guild.name }}</option>
            {% endfor %}
          </select>
        </div>
        <div>
          <input type="hidden" name="next_endpoint" value="{{ request.endpoint or 'dashboard' }}">
          <button class="btn btn-primary btn-sm" type="submit">Switch</button>
        </div>
      </form>
    </div>
    {% endif %}
    {% if session.get("user") and not session.get("is_admin") and not session.get("is_guild_admin") %}
    <div class="alert alert-info">Read-only account: you can view pages, but admin changes are restricted.</div>
    {% endif %}

    {% if page == "login" %}
      <div class="row justify-content-center mt-4">
        <div class="col-12 col-sm-10 col-md-7 col-lg-5">
          <div class="card card-soft p-4">
            <h1 class="h4 mb-3">Admin Login</h1>
            <form method="post">
              <div class="mb-3">
                <label class="form-label" for="username">Email</label>
                <input class="form-control" id="username" name="username" required autocomplete="username" autocapitalize="none" spellcheck="false">
              </div>
              <div class="mb-3">
                <label class="form-label" for="password">Password</label>
                <input class="form-control" id="password" name="password" type="password" required autocomplete="current-password">
                <div class="password-toggle-row">
                  <div class="form-check mb-0">
                    <input class="form-check-input" type="checkbox" id="show_login_password" data-password-toggle="password">
                    <label class="form-check-label" for="show_login_password">Show password</label>
                  </div>
                </div>
              </div>
              <div class="form-check mb-3">
                <input class="form-check-input" type="checkbox" id="remember_login" name="remember_login" value="1">
                <label class="form-check-label" for="remember_login">Keep me signed in for 5 days on this device</label>
              </div>
              <button class="btn btn-primary w-100" type="submit">Sign in</button>
            </form>
            {% if password_reset_enabled %}
            <div class="mt-3 text-center">
              <a href="{{ url_for('forgot_password') }}">Forgot your password?</a>
            </div>
            {% endif %}
          </div>
        </div>
      </div>
    {% elif page == "forgot_password" %}
      <div class="row justify-content-center mt-4">
        <div class="col-12 col-sm-10 col-md-7 col-lg-5">
          <div class="card card-soft p-4">
            <h1 class="h4 mb-2">Reset Password</h1>
            <p class="text-secondary">Enter your account email and we will send a one-time reset link if the account exists.</p>
            <form method="post" action="{{ url_for('forgot_password') }}">
              <div class="mb-3">
                <label class="form-label" for="forgot_email">Email</label>
                <input class="form-control" id="forgot_email" name="email" type="email" required autocomplete="email" autocapitalize="none" spellcheck="false">
              </div>
              <button class="btn btn-primary w-100" type="submit">Send Reset Link</button>
            </form>
            <div class="mt-3 text-center">
              <a href="{{ url_for('login') }}">Back to login</a>
            </div>
          </div>
        </div>
      </div>
    {% elif page == "reset_password" %}
      <div class="row justify-content-center mt-4">
        <div class="col-12 col-sm-10 col-md-7 col-lg-5">
          <div class="card card-soft p-4">
            <h1 class="h4 mb-2">Choose a New Password</h1>
            <p class="text-secondary">Resetting password for <strong>{{ reset_email }}</strong>.</p>
            <form method="post" action="{{ url_for('password_reset_confirm', token=request.view_args.token) }}">
              <div class="mb-3">
                <label class="form-label" for="reset_new_password">New Password</label>
                <input class="form-control" id="reset_new_password" name="new_password" type="password" required autocomplete="new-password">
              </div>
              <div class="mb-3">
                <label class="form-label" for="reset_confirm_new_password">Confirm New Password</label>
                <input class="form-control" id="reset_confirm_new_password" name="confirm_new_password" type="password" required autocomplete="new-password">
              </div>
              <button class="btn btn-primary w-100" type="submit">Reset Password</button>
            </form>
          </div>
        </div>
      </div>
    {% elif page == "status_public" %}
      <div class="row g-3 mb-3">
        <div class="col-12 col-md-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Bot</p>
            <p class="mb-0 fw-semibold">{{ snapshot.bot_name }}</p>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Guilds</p>
            <p class="mb-0 fs-5 fw-bold">{{ snapshot.guild_count or 1 }}</p>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Commands Synced</p>
            <p class="mb-0 fs-5 fw-bold">{{ snapshot.commands_synced }}</p>
          </div>
        </div>
        <div class="col-12 col-md-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Latency</p>
            <p class="mb-0 fs-5 fw-bold">{{ snapshot.latency_ms }} ms</p>
          </div>
        </div>
      </div>
      <div class="row g-3 mb-3">
        <div class="col-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Total Actions</p>
            <p class="mb-0 fs-5 fw-bold">{{ counts.total }}</p>
          </div>
        </div>
        <div class="col-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Success</p>
            <p class="mb-0 fs-5 fw-bold text-success">{{ counts.success }}</p>
          </div>
        </div>
        <div class="col-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Failed</p>
            <p class="mb-0 fs-5 fw-bold text-danger">{{ counts.failed }}</p>
          </div>
        </div>
      </div>
      <div class="card card-soft p-3">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <h2 class="h6 mb-0">Recent Activity</h2>
          <div class="d-flex align-items-center gap-2">
            <form method="get" class="d-flex align-items-center gap-2">
              <label class="small text-secondary mb-0" for="status_refresh">Auto refresh</label>
              <select class="form-select form-select-sm" id="status_refresh" name="refresh" onchange="this.form.submit()">
                {% for option in refresh_options %}
                <option value="{{ option }}" {% if option == status_refresh_seconds %}selected{% endif %}>
                  {% if option == 0 %}Off{% else %}{{ option }}s{% endif %}
                </option>
                {% endfor %}
              </select>
            </form>
            <span class="small text-secondary">UTC</span>
          </div>
        </div>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Time</th><th>Action</th><th>Status</th><th>Moderator</th><th>Target</th></tr></thead>
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
    {% elif page == "home" %}
      <div class="dashboard-shell">
        <section class="dashboard-hero">
          <div class="card card-soft dashboard-hero-main">
            <div>
              <h2>Control Center</h2>
              <p class="dashboard-hero-lead">Operational control for <strong>{{ selected_guild_name or snapshot.guild_id }}</strong>. The sections below keep guild controls, community tools, feeds, and runtime actions grouped so the most-used pages stay easy to reach on desktop, tablet, and mobile.</p>
            </div>
            <div class="dashboard-pill-row">
              <div class="dashboard-pill">
                <strong>Bot</strong>
                <span>{{ snapshot.bot_name }}</span>
              </div>
              <div class="dashboard-pill">
                <strong>Server</strong>
                <span>{{ selected_guild_name or snapshot.guild_id }}</span>
              </div>
              <div class="dashboard-pill">
                <strong>Access</strong>
                <span>{{ "Admin" if session.get("is_admin") else ("Guild Admin" if session.get("is_guild_admin") else "Read-only") }}</span>
              </div>
              <div class="dashboard-pill">
                <strong>Latency</strong>
                <span>{{ snapshot.latency_ms }} ms</span>
              </div>
            </div>
            <p class="dashboard-note">Actions: {{ counts.total }} total ({{ counts.success }} success, {{ counts.failed }} failed) | Commands synced: {{ snapshot.commands_synced }}</p>
          </div>
          <div class="card card-soft dashboard-hero-side">
            <div>
              <h3>Quick Notes</h3>
              <p class="text-secondary">This layout follows the newer GL.iNet-style grouping: fewer dead ends, faster jumps, cleaner mobile navigation.</p>
            </div>
            <div class="dashboard-list">
              <div class="dashboard-list-item">
                <strong>Spicy Prompts</strong>
                <div class="text-secondary">
                  {% if spicy_status and spicy_status.ok %}
                  {{ "Enabled" if spicy_status.enabled else "Disabled" }}
                  {% else %}
                  Status unavailable
                  {% endif %}
                </div>
              </div>
              <div class="dashboard-list-item">
                <strong>Command Coverage</strong>
                <div class="text-secondary">{{ command_statuses | selectattr("enabled") | list | length }}/{{ command_statuses | length }} enabled</div>
              </div>
              <div class="dashboard-list-item">
                <strong>Invite</strong>
                <div class="text-secondary">{% if snapshot.invite_url %}<a href="{{ snapshot.invite_url }}" target="_blank" rel="noreferrer">Add the bot to another server</a>{% else %}Invite link unavailable{% endif %}</div>
              </div>
            </div>
          </div>
        </section>

        <section class="card card-soft dashboard-section">
          <div class="dashboard-section-head">
            <div>
              <h3>Core Controls</h3>
              <p>Primary configuration pages for the selected guild.</p>
            </div>
          </div>
          <div class="dashboard-section-grid">
            <div class="card dash-card primary">
              <h3>Guild Settings</h3>
              <p class="text-secondary">Configure guild-specific bot log channels and runtime options.</p>
              <div class="dash-actions"><a class="btn btn-outline-secondary btn-sm" href="{{ url_for('guild_settings') }}">Open Guild Settings</a></div>
            </div>
            <div class="card dash-card">
              <h3>Command Permissions</h3>
              <p class="text-secondary">Control which commands are enabled and who can use them.</p>
              <div class="dash-actions"><a class="btn btn-outline-secondary btn-sm" href="{{ url_for('command_permissions') }}">Open Permissions</a></div>
            </div>
            <div class="card dash-card">
              <h3>Bot Profile</h3>
              <p class="text-secondary">Update the bot display name, nickname, and avatar.</p>
              <div class="dash-actions"><a class="btn btn-outline-secondary btn-sm" href="{{ url_for('bot_profile') }}">Open Bot Profile</a></div>
            </div>
            <div class="card dash-card">
              <h3>Servers</h3>
              <p class="text-secondary">Switch guild context and review managed server status.</p>
              <div class="dash-actions"><a class="btn btn-outline-secondary btn-sm" href="{{ url_for('guilds_page') }}">Open Servers</a></div>
            </div>
          </div>
        </section>

        <section class="card card-soft dashboard-section">
          <div class="dashboard-section-head">
            <div>
              <h3>Community Tools</h3>
              <p>Moderation, activity, and member-facing utilities.</p>
            </div>
          </div>
          <div class="dashboard-section-grid">
            <div class="card dash-card">
              <h3>Moderation</h3>
              <p class="text-secondary">Warnings, bad-word controls, actions, and member management.</p>
              <div class="dash-actions"><a class="btn btn-outline-secondary btn-sm" href="{{ url_for('moderation') }}">Open Moderation</a></div>
            </div>
            <div class="card dash-card">
              <h3>Member Activity</h3>
              <p class="text-secondary">Track active members and review guild engagement.</p>
              <div class="dash-actions"><a class="btn btn-outline-secondary btn-sm" href="{{ url_for('member_activity_page') }}">Open Activity</a></div>
            </div>
            <div class="card dash-card">
              <h3>Random User</h3>
              <p class="text-secondary">Manage and trigger fair random member selection flows.</p>
              <div class="dash-actions"><a class="btn btn-outline-secondary btn-sm" href="{{ url_for('random_user_page') }}">Open Random User</a></div>
            </div>
            <div class="card dash-card">
              <h3>Tag Responses</h3>
              <p class="text-secondary">Maintain guild response shortcuts and canned answers.</p>
              <div class="dash-actions"><a class="btn btn-outline-secondary btn-sm" href="{{ url_for('tag_responses') }}">Manage Tags</a></div>
            </div>
          </div>
        </section>

        <section class="card card-soft dashboard-section">
          <div class="dashboard-section-head">
            <div>
              <h3>Feeds And Monitoring</h3>
              <p>External feeds, uptime checks, and automation pages.</p>
            </div>
          </div>
          <div class="dashboard-section-grid">
            <div class="card dash-card">
              <h3>YouTube</h3>
              <p class="text-secondary">Video and community-post monitoring.</p>
              <div class="dash-actions"><a class="btn btn-outline-secondary btn-sm" href="{{ url_for('youtube_subscriptions') }}">Open YouTube</a></div>
            </div>
            <div class="card dash-card">
              <h3>Reddit</h3>
              <p class="text-secondary">Subreddit watchlists and notifications.</p>
              <div class="dash-actions"><a class="btn btn-outline-secondary btn-sm" href="{{ url_for('reddit_feeds') }}">Open Reddit</a></div>
            </div>
            <div class="card dash-card">
              <h3>WordPress</h3>
              <p class="text-secondary">Blog and site-post monitoring.</p>
              <div class="dash-actions"><a class="btn btn-outline-secondary btn-sm" href="{{ url_for('wordpress_feeds') }}">Open WordPress</a></div>
            </div>
            <div class="card dash-card">
              <h3>Uptime Monitors</h3>
              <p class="text-secondary">Per-guild service and site monitoring.</p>
              <div class="dash-actions"><a class="btn btn-outline-secondary btn-sm" href="{{ url_for('uptime_monitors_page') }}">Open Monitors</a></div>
            </div>
          </div>
        </section>
      </div>
    {% elif page == "overview" %}
      <div class="dashboard-shell">
        <section class="dashboard-hero">
          <div class="card card-soft dashboard-hero-main">
            <div>
              <h2>Dashboard</h2>
              <p class="dashboard-hero-lead">Operational control for <strong>{{ selected_guild_name or snapshot.guild_id }}</strong>. Use the sections below to manage core configuration, community tools, and notification feeds.</p>
            </div>
            <div class="dashboard-pill-row">
              <div class="dashboard-pill">
                <strong>Server</strong>
                <span>{{ selected_guild_name or snapshot.guild_id }}</span>
              </div>
              <div class="dashboard-pill">
                <strong>Access</strong>
                <span>{{ "Admin" if session.get("is_admin") else ("Guild Admin" if session.get("is_guild_admin") else "Read-only") }}</span>
              </div>
              <div class="dashboard-pill">
                <strong>Commands Enabled</strong>
                <span>{{ command_statuses | selectattr("enabled") | list | length }}/{{ command_statuses | length }}</span>
              </div>
              <div class="dashboard-pill">
                <strong>Spicy Prompts</strong>
                <span>
                  {% if spicy_status and spicy_status.ok %}
                  {{ "Enabled" if spicy_status.enabled else "Disabled" }}
                  {% else %}
                  Unknown
                  {% endif %}
                </span>
              </div>
            </div>
            <p class="dashboard-note">Latency: {{ snapshot.latency_ms }} ms | Actions: {{ counts.total }} total ({{ counts.success }} success, {{ counts.failed }} failed)</p>
          </div>
          <div class="card card-soft dashboard-hero-side">
            <div>
              <h3>Quick Notes</h3>
              <p class="text-secondary">Key status details for the selected guild.</p>
            </div>
            <div class="dashboard-list">
              <div class="dashboard-list-item">
                <strong>Bot</strong>
                <div class="text-secondary">{{ snapshot.bot_name }}</div>
              </div>
              <div class="dashboard-list-item">
                <strong>Spicy Channel</strong>
                <div class="text-secondary">
                  {% if spicy_status and spicy_status.ok and spicy_status.channel_id %}
                  Channel ID: {{ spicy_status.channel_id }}
                  {% else %}
                  Not configured
                  {% endif %}
                </div>
              </div>
              <div class="dashboard-list-item">
                <strong>Log Channel</strong>
                <div class="text-secondary">Set per guild in Guild Settings.</div>
              </div>
            </div>
          </div>
        </section>

        <section class="card card-soft dashboard-section">
          <div class="dashboard-section-head">
            <div>
              <h3>Core Controls</h3>
              <p>Primary configuration pages for this guild.</p>
            </div>
          </div>
          <div class="dashboard-section-grid">
            <div class="card dash-card primary">
              <h3>Guild Settings</h3>
              <p class="text-secondary">Configure bot log channels and guild-specific settings.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('guild_settings') }}">Open Guild Settings</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Command Permissions</h3>
              <p class="text-secondary">Enable, disable, and restrict commands by role.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('command_permissions') }}">Open Permissions</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Bot Profile</h3>
              <p class="text-secondary">Update bot display name and avatar.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('bot_profile') }}">Open Bot Profile</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Settings</h3>
              <p class="text-secondary">Runtime env values and system configuration.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('settings') }}">Open Settings</a>
              </div>
            </div>
          </div>
        </section>

        <section class="card card-soft dashboard-section">
          <div class="dashboard-section-head">
            <div>
              <h3>Community Tools</h3>
              <p>Member activity, moderation history, and tag responses.</p>
            </div>
          </div>
          <div class="dashboard-section-grid">
            <div class="card dash-card">
              <h3>Member Activity</h3>
              <p class="text-secondary">Top 20 members across rolling time windows.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('member_activity_page') }}">Open Activity</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Moderation Actions</h3>
              <p class="text-secondary">Recent moderation events and audits.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('actions') }}">View Actions</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Moderation</h3>
              <p class="text-secondary">Bad word filters, warnings, and auto-timeout rules.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('moderation') }}">Open Moderation</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Tag Responses</h3>
              <p class="text-secondary">Maintain command shortcut responses.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('tag_responses') }}">Manage Tags</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Users</h3>
              <p class="text-secondary">Manage web GUI users and roles.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('users') }}">Manage Users</a>
              </div>
            </div>
          </div>
        </section>

        <section class="card card-soft dashboard-section">
          <div class="dashboard-section-head">
            <div>
              <h3>Notification Feeds</h3>
              <p>External monitors and feed routing.</p>
            </div>
          </div>
          <div class="dashboard-section-grid">
            <div class="card dash-card">
              <h3>YouTube</h3>
              <p class="text-secondary">Video and community post alerts.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('youtube_subscriptions') }}">Open YouTube</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Reddit</h3>
              <p class="text-secondary">Scheduled subreddit updates.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('reddit_feeds') }}">Open Reddit</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>WordPress</h3>
              <p class="text-secondary">New blog post alerts.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('wordpress_feeds') }}">Open WordPress</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>LinkedIn</h3>
              <p class="text-secondary">Profile post notifications.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('linkedin_feeds') }}">Open LinkedIn</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Spicy Prompts</h3>
              <p class="text-secondary">Repo refresh and status.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('spicy_prompts') }}">Open Spicy Prompts</a>
              </div>
            </div>
          </div>
        </section>

        <section class="card card-soft dashboard-section">
          <div class="dashboard-section-head">
            <div>
              <h3>Runtime and Admin</h3>
              <p>Logs, observability, and docs.</p>
            </div>
          </div>
          <div class="dashboard-section-grid">
            <div class="card dash-card">
              <h3>Logs</h3>
              <p class="text-secondary">Container and bot logs.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('logs') }}">Open Logs</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Observability</h3>
              <p class="text-secondary">Status summaries and metrics.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('observability') }}">Open Observability</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Status</h3>
              <p class="text-secondary">Internal status view.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('status_page') }}">Open Status</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Documentation</h3>
              <p class="text-secondary">Bot help and wiki pages.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('documentation') }}">Open Docs</a>
              </div>
            </div>
          </div>
        </section>

        <section class="card card-soft dashboard-section">
          <div class="dashboard-section-head">
            <div>
              <h3>Latest Actions</h3>
              <p>Most recent moderation events.</p>
            </div>
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
        </section>
      </div>
    {% elif page == "dashboard" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-2">Dashboard</h1>
        <p class="text-secondary mb-3">Every category is listed here for quick access.</p>
        <div class="row g-3">
          <div class="col-12 col-lg-4">
            <div class="card card-soft p-3 h-100">
              <h3 class="h6 mb-2">Core</h3>
              <div class="d-grid gap-2">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('home') }}">Landing Page</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('overview') }}">Overview</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('guilds_page') }}">Servers</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('guild_settings') }}">Guild Settings</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('moderation') }}">Moderation</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('command_permissions') }}">Command Permissions</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('bot_profile') }}">Bot Profile</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('random_user_page') }}">Random User</a>
              </div>
            </div>
          </div>
          <div class="col-12 col-lg-4">
            <div class="card card-soft p-3 h-100">
              <h3 class="h6 mb-2">Community</h3>
              <div class="d-grid gap-2">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('member_activity_page') }}">Member Activity</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('actions') }}">Moderation Actions</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('tag_responses') }}">Tag Responses</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('spicy_prompts') }}">Spicy Prompts</a>
              </div>
            </div>
          </div>
          <div class="col-12 col-lg-4">
            <div class="card card-soft p-3 h-100">
              <h3 class="h6 mb-2">Feeds</h3>
              <div class="d-grid gap-2">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('youtube_subscriptions') }}">YouTube</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('reddit_feeds') }}">Reddit</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('wordpress_feeds') }}">WordPress</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('linkedin_feeds') }}">LinkedIn</a>
              </div>
            </div>
          </div>
          <div class="col-12 col-lg-4">
            <div class="card card-soft p-3 h-100">
              <h3 class="h6 mb-2">Uptime</h3>
              <div class="d-grid gap-2">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('uptime_monitors_page') }}">Uptime Monitors</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('status_page') }}">Status</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('observability') }}">Observability</a>
              </div>
            </div>
          </div>
          <div class="col-12 col-lg-4">
            <div class="card card-soft p-3 h-100">
              <h3 class="h6 mb-2">Admin</h3>
              <div class="d-grid gap-2">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('users') }}">Users</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('guild_access') }}">Guild Access</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('settings') }}">Settings (Global)</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('logs') }}">Logs (Global)</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('documentation') }}">Documentation (Global)</a>
              </div>
            </div>
          </div>
          <div class="col-12 col-lg-4">
            <div class="card card-soft p-3 h-100">
              <h3 class="h6 mb-2">Account</h3>
              <div class="d-grid gap-2">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('account') }}">My Account</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('logout') }}">Logout</a>
              </div>
            </div>
          </div>
        </div>
        <div class="mt-4">
          <h3 class="h6 mb-2">Latest Actions</h3>
          <div class="table-wrap">
            <table class="table table-sm align-middle">
              <thead><tr><th>Time (UTC)</th><th>Action</th><th>Status</th></tr></thead>
              <tbody>
                {% for row in actions %}
                <tr>
                  <td class="small">{{ row.created_at }}</td>
                  <td>{{ row.action }}</td>
                  <td><span class="badge text-bg-{{ 'success' if row.status == 'success' else 'danger' }} status-pill">{{ row.status }}</span></td>
                </tr>
                {% else %}
                <tr><td colspan="3" class="text-secondary">No actions logged yet.</td></tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    {% elif page == "uptime_monitors" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">Uptime Monitors</h1>
        <form method="post" action="{{ url_for('uptime_monitor_add') }}">
          <div class="row g-2">
            <div class="col-12 col-xl-3">
              <label class="form-label" for="monitor_name">Name</label>
              <input class="form-control" id="monitor_name" name="monitor_name" placeholder="API - prod" required {% if not can_manage_guild %}disabled{% endif %}>
            </div>
            <div class="col-12 col-md-6 col-xl-2">
              <label class="form-label" for="monitor_type">Type</label>
              <select class="form-select" id="monitor_type" name="monitor_type" {% if not can_manage_guild %}disabled{% endif %}>
                <option value="http">HTTP (Website/API)</option>
                <option value="statuspage">Status Page</option>
                <option value="tcp">TCP</option>
              </select>
            </div>
            <div class="col-12 col-xl-4">
              <label class="form-label" for="monitor_target">Target</label>
              <input class="form-control" id="monitor_target" name="monitor_target" placeholder="https://example.com or host:port" required {% if not can_manage_guild %}disabled{% endif %}>
            </div>
            <div class="col-12 col-xl-3">
              <label class="form-label" for="monitor_preset">Preset</label>
              <select class="form-select" id="monitor_preset" {% if not can_manage_guild %}disabled{% endif %}>
                <option value="">Choose a preset...</option>
                <option value="discord">Discord Status</option>
                <option value="tailscale">Tailscale Status</option>
              </select>
              <div class="form-text">Presets use Statuspage endpoints.</div>
            </div>
            <div class="col-6 col-md-3 col-xl-1">
              <label class="form-label" for="monitor_interval">Interval</label>
              <select class="form-select" id="monitor_interval" name="interval_seconds" {% if not can_manage_guild %}disabled{% endif %}>
                {% for option in monitor_interval_options %}
                <option value="{{ option.value }}">{{ option.label }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-6 col-md-3 col-xl-1">
              <label class="form-label" for="monitor_timeout">Timeout</label>
              <select class="form-select" id="monitor_timeout" name="timeout_seconds" {% if not can_manage_guild %}disabled{% endif %}>
                {% for option in monitor_timeout_options %}
                <option value="{{ option }}">{{ option }}s</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-md-6 col-xl-4">
              <label class="form-label" for="monitor_channel">Alert Channel</label>
              <select class="form-select" id="monitor_channel" name="alert_channel_id" {% if not can_manage_guild %}disabled{% endif %}>
                <option value="">Default (Bot Log / Guild Setting)</option>
                {% for channel in notification_channels %}
                <option value="{{ channel.id }}">{{ channel.name }} ({{ channel.id }})</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-xl-1 d-flex align-items-end">
              <button class="btn btn-primary w-100" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Add</button>
            </div>
          </div>
        </form>
        <script>
          (function () {
            const preset = document.getElementById("monitor_preset");
            const type = document.getElementById("monitor_type");
            const target = document.getElementById("monitor_target");
            if (!preset || !type || !target) return;
            preset.addEventListener("change", () => {
              if (preset.value === "discord") {
                type.value = "statuspage";
                target.value = "https://discordstatus.com";
              } else if (preset.value === "tailscale") {
                type.value = "statuspage";
                target.value = "https://status.tailscale.com";
              }
            });
          })();
        </script>
        {% if not notification_channels %}
        <p class="small text-danger mt-2 mb-0">No text channels found. Verify bot guild/channel permissions and refresh.</p>
        {% endif %}
      </div>
      <div class="card card-soft p-3">
        <h2 class="h6 mb-3">Configured Monitors</h2>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Name</th><th>Target</th><th>Status</th><th>Interval</th><th>Last Check</th><th>Alert Channel</th><th>Action</th></tr></thead>
            <tbody>
              {% for row in uptime_monitors %}
              <tr>
                <td class="small">
                  <div class="fw-semibold">{{ row.name }}</div>
                  <div class="text-secondary small">{{ row.monitor_type|upper }}</div>
                </td>
                <td class="small">{{ row.target }}</td>
                <td class="small">
                  {% set status = (row.last_status or 'unknown') %}
                  <span class="badge text-bg-{{ 'success' if status == 'up' else ('danger' if status == 'down' else 'secondary') }}">{{ status }}</span>
                  {% if row.last_error %}
                  <div class="text-secondary small">{{ row.last_error }}</div>
                  {% endif %}
                </td>
                <td class="small">{{ row.interval_label }}</td>
                <td class="small">{{ row.last_checked_at or '-' }}</td>
                <td class="small">
                  {% if row.alert_channel_name %}
                  {{ row.alert_channel_name }} ({{ row.alert_channel_id }})
                  {% else %}
                  Default
                  {% endif %}
                </td>
                <td class="small d-flex gap-2">
                  <form method="post" action="{{ url_for('uptime_monitor_toggle', monitor_id=row.id) }}">
                    <input type="hidden" name="enabled" value="{{ 0 if row.enabled else 1 }}">
                    <button class="btn btn-sm btn-outline-secondary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>
                      {{ "Disable" if row.enabled else "Enable" }}
                    </button>
                  </form>
                  <form method="post" action="{{ url_for('uptime_monitor_delete', monitor_id=row.id) }}">
                    <button class="btn btn-sm btn-outline-danger" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Delete</button>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="7" class="text-secondary">No monitors configured yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "status_admin" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-2">Service Status</h1>
        <p class="text-secondary mb-0">Focused service health view for the selected guild, separate from dashboard analytics.</p>
      </div>
      <div class="row g-3 mb-3">
        {% for check in status_checks %}
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">{{ check.component }}</p>
            <p class="mb-1 fw-semibold">{{ check.state }}</p>
            <p class="small mb-0 text-secondary">{{ check.detail }}</p>
          </div>
        </div>
        {% endfor %}
      </div>
      <div class="card card-soft p-3 mb-3">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <h2 class="h6 mb-0">Latest Action Events</h2>
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
      <div class="card card-soft p-3">
        <h2 class="h6 mb-2">Status Log Tail ({{ status_log_name }})</h2>
        <p class="small text-secondary mb-2">Source directory: {{ status_log_dir }}</p>
        <pre class="small mb-0" style="white-space: pre-wrap; max-height: 35vh; overflow-y: auto;">{{ status_log_tail }}</pre>
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
    {% elif page == "member_activity" %}
      <div class="card card-soft p-3 mb-3">
        <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3">
          <div>
            <h1 class="h5 mb-2">Member Activity</h1>
            <p class="text-secondary mb-0">Top {{ member_activity.top_limit }} eligible members by message activity for the selected guild across rolling time windows.</p>
          </div>
          <div class="d-flex flex-column flex-sm-row gap-2">
            <form method="get" action="{{ url_for('member_activity_page') }}" class="d-flex flex-column flex-sm-row gap-2">
              <select class="form-select" name="role_id" onchange="this.form.submit()">
                {% for option in member_activity_role_options %}
                <option value="{{ option.value }}" {% if option.value == member_activity.selected_role_id %}selected{% endif %}>{{ option.label }}</option>
                {% endfor %}
              </select>
            </form>
            {% if member_activity_export_enabled %}
            <a class="btn btn-outline-primary" href="{{ url_for('member_activity_export', role_id=member_activity.selected_role_id) if member_activity.selected_role_id else url_for('member_activity_export') }}">Download ZIP Export</a>
            {% endif %}
          </div>
        </div>
        {% if member_activity.error %}
        <p class="small text-danger mt-3 mb-0">{{ member_activity.error }}</p>
        {% else %}
        <p class="small text-secondary mt-3 mb-0">Current filter: <strong>{{ member_activity.selected_role_label }}</strong>. Moderator-style accounts are excluded from rankings.</p>
        {% endif %}
            <div class="card card-soft p-3 mb-3">
        <div class="d-flex align-items-center justify-content-between mb-2">
          <h2 class="h6 mb-0">Command Status</h2>
          <a class="small" href="{{ url_for('command_permissions') }}">Manage</a>
        </div>
        {% if command_statuses %}
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead>
              <tr>
                <th>Command</th>
                <th>Access</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {% for command in command_statuses %}
              <tr>
                <td>
                  <div class="fw-semibold">{{ command.label }}</div>
                  {% if command.description %}
                  <div class="text-secondary small">{{ command.description }}</div>
                  {% endif %}
                </td>
                <td class="small">{{ command.access }}</td>
                <td>
                  {% if command.enabled %}
                  <span class="badge text-bg-success">Enabled</span>
                  {% else %}
                  <span class="badge text-bg-secondary">Disabled</span>
                  {% endif %}
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        {% else %}
        <p class="text-secondary small mb-0">Command status is unavailable.</p>
        {% endif %}
      </div>
</div>
      <div class="row g-3">
        {% for window in member_activity.windows %}
        <div class="col-12 col-xl-6">
          <div class="card card-soft p-3 h-100">
            <h2 class="h6 mb-3">{{ window.label }}</h2>
            <div class="table-wrap">
              <table class="table table-sm align-middle">
                <thead><tr><th>Rank</th><th>Member</th><th>Messages</th><th>Active Days</th><th>Last Seen</th></tr></thead>
                <tbody>
                  {% for member in window.members %}
                  <tr>
                    <td>{{ member.rank }}</td>
                    <td class="small">
                      <div class="fw-semibold">{{ member.display_name or member.username or member.user_id }}</div>
                      {% if member.username and member.username != member.display_name %}
                      <div class="text-secondary">{{ member.username }}</div>
                      {% endif %}
                    </td>
                    <td>{{ member.message_count }}</td>
                    <td>{{ member.active_days }}</td>
                    <td class="small">{{ member.last_message_at or "n/a" }}</td>
                  </tr>
                  {% else %}
                  <tr><td colspan="5" class="text-secondary">No member activity recorded in this window yet.</td></tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
          </div>
        </div>
        {% endfor %}
      </div>
    {% elif page == "random_user" %}
      <div class="card card-soft p-3">
        <div class="d-flex flex-column flex-lg-row justify-content-between align-items-start gap-3 mb-3">
          <div>
            <h1 class="h5 mb-2">Random User Picker</h1>
            <p class="text-secondary mb-0">Select a random member. Users picked in the last 30 days are excluded.</p>
          </div>
        </div>
        <form method="post" action="{{ url_for('random_user_page') }}" class="d-flex flex-column flex-lg-row gap-2 align-items-end mb-3">
          <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
          <div class="flex-grow-1">
            <label class="form-label" for="random_role_id">Filter by role</label>
            <select class="form-select" id="random_role_id" name="role_id">
              {% for option in random_user_role_options %}
              <option value="{{ option.value }}" {% if option.value == random_user_selected_role_id %}selected{% endif %}>{{ option.label }}</option>
              {% endfor %}
            </select>
          </div>
          <div>
            <button class="btn btn-primary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Pick Random User</button>
          </div>
        </form>
        {% if random_user_result %}
          {% if random_user_result.ok %}
            <div class="alert alert-success">
              Selected: <strong>{{ random_user_result.display_name }}</strong>
            </div>
            <p class="text-secondary mb-0">Eligible: {{ random_user_result.eligible_count }} | Excluded last 30 days: {{ random_user_result.recent_count }}</p>
          {% else %}
            <div class="alert alert-danger">{{ random_user_result.error }}</div>
          {% endif %}
        {% endif %}
      </div>
    {% elif page == "youtube" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">YouTube Notifications</h1>
        <form method="post" action="{{ url_for('youtube_add') }}">
          <div class="row g-2">
            <div class="col-12 col-xl-4">
              <label class="form-label" for="youtube_url">YouTube Channel URL</label>
              <input class="form-control" id="youtube_url" name="youtube_url" placeholder="https://www.youtube.com/@channelname" required {% if not can_manage_guild %}disabled{% endif %}>
            </div>
            <div class="col-12 col-md-6 col-xl-3">
              <label class="form-label" for="notify_channel_id">Discord Notify Channel</label>
              <select class="form-select" id="notify_channel_id" name="notify_channel_id" required {% if not can_manage_guild %}disabled{% endif %}>
                <option value="">Select channel...</option>
                {% for channel in notification_channels %}
                <option value="{{ channel.id }}">{{ channel.name }} ({{ channel.id }})</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-md-6 col-xl-2">
              <label class="form-label" for="youtube_interval">Schedule</label>
              <select class="form-select" id="youtube_interval" name="poll_interval_seconds" {% if not can_manage_guild %}disabled{% endif %}>
                {% for option in feed_interval_options %}
                <option value="{{ option.value }}">{{ option.label }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-xl-2">
              <label class="form-label d-block">Notify On</label>
              <div class="form-check">
                <input class="form-check-input" type="checkbox" id="youtube_include_uploads" name="include_uploads" value="1" checked {% if not can_manage_guild %}disabled{% endif %}>
                <label class="form-check-label" for="youtube_include_uploads">Uploads / Shorts</label>
              </div>
              <div class="form-check">
                <input class="form-check-input" type="checkbox" id="youtube_include_posts" name="include_community_posts" value="1" {% if not can_manage_guild %}disabled{% endif %}>
                <label class="form-check-label" for="youtube_include_posts">Community Posts</label>
              </div>
            </div>
            <div class="col-12 col-xl-1 d-flex align-items-end">
              <button class="btn btn-primary w-100" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Add</button>
            </div>
          </div>
        </form>
        {% if not notification_channels %}
        <p class="small text-danger mt-2 mb-0">No text channels found. Verify bot guild/channel permissions and refresh.</p>
        {% endif %}
      </div>
      <div class="card card-soft p-3">
        <h2 class="h6 mb-3">Current Subscriptions</h2>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Created (UTC)</th><th>YouTube Channel</th><th>Notify Channel</th><th>Schedule</th><th>Notify On</th><th>Last Update</th><th>Action</th></tr></thead>
            <tbody>
              {% for row in subscriptions %}
              <tr>
                <td class="small">{{ row.created_at }}</td>
                <td class="small">
                  <div class="fw-semibold">{{ row.channel_title }}</div>
                  <div><a href="{{ row.source_url }}" target="_blank" rel="noreferrer">{{ row.source_url }}</a></div>
                </td>
                <td class="small">{{ row.target_channel_name }} ({{ row.target_channel_id }})</td>
                <td class="small">
                  {{ row.interval_label }}
                </td>
                <td class="small">
                  {% if row.include_uploads %}Uploads{% endif %}{% if row.include_uploads and row.include_community_posts %} + {% endif %}{% if row.include_community_posts %}Posts{% endif %}
                </td>
                <td class="small">
                  {% if row.last_video_id %}
                    {{ row.last_video_title or row.last_video_id }}<br>
                    <span class="text-secondary">{{ row.last_published_at or '-' }}</span>
                  {% elif row.last_community_post_id %}
                    {{ row.last_community_post_title or row.last_community_post_id }}<br>
                    <span class="text-secondary">{{ row.last_community_published_at or '-' }}</span>
                  {% else %}
                    -
                  {% endif %}
                </td>
                <td>
                  <form method="post" action="{{ url_for('youtube_delete', subscription_id=row.id) }}">
                    <button class="btn btn-sm btn-outline-danger" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Delete</button>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="7" class="text-secondary">No YouTube subscriptions yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "reddit" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">Reddit Feeds</h1>
        <form method="post" action="{{ url_for('reddit_add') }}">
          <div class="row g-2">
            <div class="col-12 col-xl-4">
              <label class="form-label" for="reddit_source">Reddit Forum</label>
              <input class="form-control" id="reddit_source" name="reddit_source" placeholder="r/python or https://www.reddit.com/r/python" required {% if not can_manage_guild %}disabled{% endif %}>
            </div>
            <div class="col-12 col-md-6 col-xl-4">
              <label class="form-label" for="reddit_channel_id">Discord Notify Channel</label>
              <select class="form-select" id="reddit_channel_id" name="notify_channel_id" required {% if not can_manage_guild %}disabled{% endif %}>
                <option value="">Select channel...</option>
                {% for channel in notification_channels %}
                <option value="{{ channel.id }}">{{ channel.name }} ({{ channel.id }})</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-md-6 col-xl-3">
              <label class="form-label" for="reddit_interval">Schedule</label>
              <select class="form-select" id="reddit_interval" name="poll_interval_seconds" {% if not can_manage_guild %}disabled{% endif %}>
                {% for option in feed_interval_options %}
                <option value="{{ option.value }}">{{ option.label }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-xl-1 d-flex align-items-end">
              <button class="btn btn-primary w-100" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Add</button>
            </div>
          </div>
        </form>
        {% if not notification_channels %}
        <p class="small text-danger mt-2 mb-0">No text channels found. Verify bot guild/channel permissions and refresh.</p>
        {% endif %}
      </div>
      <div class="card card-soft p-3">
        <h2 class="h6 mb-3">Current Reddit Feeds</h2>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Created (UTC)</th><th>Subreddit</th><th>Notify Channel</th><th>Schedule</th><th>Last Post</th><th>Action</th></tr></thead>
            <tbody>
              {% for row in reddit_feeds %}
              <tr>
                <td class="small">{{ row.created_at }}</td>
                <td class="small">
                  <div class="fw-semibold">r/{{ row.subreddit_name }}</div>
                  <div><a href="{{ row.source_url }}" target="_blank" rel="noreferrer">{{ row.source_url }}</a></div>
                </td>
                <td class="small">{{ row.target_channel_name }} ({{ row.target_channel_id }})</td>
                <td class="small">{{ row.interval_label }}</td>
                <td class="small">
                  {% if row.last_post_id %}
                    <a href="{{ row.last_post_url }}" target="_blank" rel="noreferrer">{{ row.last_post_title or row.last_post_id }}</a><br>
                    <span class="text-secondary">{{ row.last_published_at or '-' }}</span>
                  {% else %}
                    -
                  {% endif %}
                </td>
                <td>
                  <form method="post" action="{{ url_for('reddit_delete', feed_id=row.id) }}">
                    <button class="btn btn-sm btn-outline-danger" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Delete</button>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="6" class="text-secondary">No Reddit feeds yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "wordpress" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">WordPress Notifications</h1>
        <form method="post" action="{{ url_for('wordpress_add') }}">
          <div class="row g-2">
            <div class="col-12 col-xl-4">
              <label class="form-label" for="wordpress_site_url">WordPress Site URL</label>
              <input class="form-control" id="wordpress_site_url" name="wordpress_site_url" placeholder="https://wickedyoda.com" required {% if not can_manage_guild %}disabled{% endif %}>
            </div>
            <div class="col-12 col-md-6 col-xl-4">
              <label class="form-label" for="wordpress_channel_id">Discord Notify Channel</label>
              <select class="form-select" id="wordpress_channel_id" name="notify_channel_id" required {% if not can_manage_guild %}disabled{% endif %}>
                <option value="">Select channel...</option>
                {% for channel in notification_channels %}
                <option value="{{ channel.id }}">{{ channel.name }} ({{ channel.id }})</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-md-6 col-xl-3">
              <label class="form-label" for="wordpress_interval">Schedule</label>
              <select class="form-select" id="wordpress_interval" name="poll_interval_seconds" {% if not can_manage_guild %}disabled{% endif %}>
                {% for option in feed_interval_options %}
                <option value="{{ option.value }}">{{ option.label }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-xl-1 d-flex align-items-end">
              <button class="btn btn-primary w-100" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Add</button>
            </div>
          </div>
        </form>
        {% if not notification_channels %}
        <p class="small text-danger mt-2 mb-0">No text channels found. Verify bot guild/channel permissions and refresh.</p>
        {% endif %}
      </div>
      <div class="card card-soft p-3">
        <h2 class="h6 mb-3">Current WordPress Feeds</h2>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Created (UTC)</th><th>Site</th><th>Notify Channel</th><th>Schedule</th><th>Last Post</th><th>Action</th></tr></thead>
            <tbody>
              {% for row in wordpress_feeds %}
              <tr>
                <td class="small">{{ row.created_at }}</td>
                <td class="small">
                  <div class="fw-semibold">{{ row.site_title }}</div>
                  <div><a href="{{ row.site_url }}" target="_blank" rel="noreferrer">{{ row.site_url }}</a></div>
                  <div class="text-secondary">{{ row.feed_url }}</div>
                </td>
                <td class="small">{{ row.target_channel_name }} ({{ row.target_channel_id }})</td>
                <td class="small">{{ row.interval_label }}</td>
                <td class="small">
                  {% if row.last_post_id %}
                    <a href="{{ row.last_post_url }}" target="_blank" rel="noreferrer">{{ row.last_post_title or row.last_post_id }}</a><br>
                    <span class="text-secondary">{{ row.last_published_at or '-' }}</span>
                  {% else %}
                    -
                  {% endif %}
                </td>
                <td>
                  <form method="post" action="{{ url_for('wordpress_delete', feed_id=row.id) }}">
                    <button class="btn btn-sm btn-outline-danger" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Delete</button>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="6" class="text-secondary">No WordPress feeds yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "linkedin" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-2">LinkedIn Notifications</h1>
        <p class="small text-secondary mb-3">Experimental. Works only for public LinkedIn profiles/pages where recent activity is accessible without login.</p>
        <form method="post" action="{{ url_for('linkedin_add') }}">
          <div class="row g-2">
            <div class="col-12 col-xl-4">
              <label class="form-label" for="linkedin_profile_url">LinkedIn Profile/Page URL</label>
              <input class="form-control" id="linkedin_profile_url" name="linkedin_profile_url" placeholder="https://www.linkedin.com/in/example" required {% if not can_manage_guild %}disabled{% endif %}>
            </div>
            <div class="col-12 col-md-6 col-xl-4">
              <label class="form-label" for="linkedin_channel_id">Discord Notify Channel</label>
              <select class="form-select" id="linkedin_channel_id" name="notify_channel_id" required {% if not can_manage_guild %}disabled{% endif %}>
                <option value="">Select channel...</option>
                {% for channel in notification_channels %}
                <option value="{{ channel.id }}">{{ channel.name }} ({{ channel.id }})</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-md-6 col-xl-3">
              <label class="form-label" for="linkedin_interval">Schedule</label>
              <select class="form-select" id="linkedin_interval" name="poll_interval_seconds" {% if not can_manage_guild %}disabled{% endif %}>
                {% for option in feed_interval_options %}
                <option value="{{ option.value }}">{{ option.label }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-xl-1 d-flex align-items-end">
              <button class="btn btn-primary w-100" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Add</button>
            </div>
          </div>
        </form>
        {% if not notification_channels %}
        <p class="small text-danger mt-2 mb-0">No text channels found. Verify bot guild/channel permissions and refresh.</p>
        {% endif %}
      </div>
      <div class="card card-soft p-3">
        <h2 class="h6 mb-3">Current LinkedIn Feeds</h2>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Created (UTC)</th><th>Profile</th><th>Notify Channel</th><th>Schedule</th><th>Last Post</th><th>Action</th></tr></thead>
            <tbody>
              {% for row in linkedin_feeds %}
              <tr>
                <td class="small">{{ row.created_at }}</td>
                <td class="small">
                  <div class="fw-semibold">{{ row.profile_label }}</div>
                  <div><a href="{{ row.profile_url }}" target="_blank" rel="noreferrer">{{ row.profile_url }}</a></div>
                  <div class="text-secondary">{{ row.activity_url }}</div>
                </td>
                <td class="small">{{ row.target_channel_name }} ({{ row.target_channel_id }})</td>
                <td class="small">{{ row.interval_label }}</td>
                <td class="small">
                  {% if row.last_post_id %}
                    <a href="{{ row.last_post_url }}" target="_blank" rel="noreferrer">{{ row.last_post_title or row.last_post_id }}</a><br>
                    <span class="text-secondary">{{ row.last_published_at or '-' }}</span>
                  {% else %}
                    -
                  {% endif %}
                </td>
                <td>
                  <form method="post" action="{{ url_for('linkedin_delete', feed_id=row.id) }}">
                    <button class="btn btn-sm btn-outline-danger" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Delete</button>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="6" class="text-secondary">No LinkedIn feeds yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "spicy_prompts" %}
      <div class="card card-soft p-3 mb-3">
        <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-center gap-3">
          <div>
            <h1 class="h5 mb-1">Spicy Prompts</h1>
            <p class="small text-secondary mb-0">Refresh prompt packs from the configured GitHub repo without restarting the bot. This only updates cached prompt data.</p>
          </div>
          <form method="post" action="{{ url_for('spicy_prompts_refresh') }}">
            <button class="btn btn-primary" type="submit" {% if not session.get("is_admin") %}disabled{% endif %}>Refresh From Repo</button>
          </form>
        </div>
      </div>
      <div class="card card-soft p-3 mb-3">
        <h2 class="h6 mb-3">Guild Access Control</h2>
        <form method="post" action="{{ url_for('spicy_prompts_settings_save') }}">
          <div class="row g-3">
            <div class="col-12 col-lg-4">
              <div class="form-check mt-4">
                <input class="form-check-input" type="checkbox" id="spicy_prompts_enabled" name="spicy_prompts_enabled" value="1" {% if spicy_settings.spicy_prompts_enabled %}checked{% endif %} {% if not can_manage_guild %}disabled{% endif %}>
                <label class="form-check-label" for="spicy_prompts_enabled">Enable `/spicy` for this guild</label>
              </div>
            </div>
            <div class="col-12 col-lg-8">
              <label class="form-label" for="spicy_prompts_channel_id">Allowed Channel</label>
              <select class="form-select" id="spicy_prompts_channel_id" name="spicy_prompts_channel_id" {% if not can_manage_guild %}disabled{% endif %}>
                <option value="">Select age-restricted channel...</option>
                {% for channel in notification_channels %}
                <option value="{{ channel.id }}" {% if selected_spicy_channel_id == channel.id|string %}selected{% endif %}>
                  {{ channel.name }}{% if channel.nsfw %} [18+]{% endif %} ({{ channel.id }})
                </option>
                {% endfor %}
              </select>
              <div class="form-text">`/spicy` only works in the configured age-restricted channel. Non-NSFW channels are rejected.</div>
            </div>
            <div class="col-12">
              <button class="btn btn-primary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Save Spicy Prompt Settings</button>
            </div>
          </div>
        </form>
      </div>
      <div class="row g-3 mb-3">
        <div class="col-12 col-md-6 col-xl-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Feature Enabled</p>
            <p class="mb-0 fw-semibold">{{ "Yes" if spicy_prompts.enabled else "No" }}</p>
          </div>
        </div>
        <div class="col-12 col-md-6 col-xl-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Cached Packs</p>
            <p class="mb-0 fw-semibold">{{ spicy_prompts.pack_count }}</p>
          </div>
        </div>
        <div class="col-12 col-md-6 col-xl-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Cached Prompts</p>
            <p class="mb-0 fw-semibold">{{ spicy_prompts.prompt_count }}</p>
          </div>
        </div>
        <div class="col-12 col-md-6 col-xl-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Last Success</p>
            <p class="mb-0 fw-semibold">{{ spicy_prompts.last_success_at or "-" }}</p>
          </div>
        </div>
      </div>
      <div class="card card-soft p-3 mb-3">
        <h2 class="h6 mb-3">Repository</h2>
        <div class="row g-2">
          <div class="col-12">
            <div class="small text-secondary">Repo URL</div>
            <div class="fw-semibold">{{ spicy_prompts.repo_url or "-" }}</div>
          </div>
          <div class="col-12 col-lg-4">
            <div class="small text-secondary">Branch</div>
            <div class="fw-semibold">{{ spicy_prompts.repo_branch or "-" }}</div>
          </div>
          <div class="col-12 col-lg-8">
            <div class="small text-secondary">Manifest Path</div>
            <div class="fw-semibold">{{ spicy_prompts.manifest_path or "-" }}</div>
          </div>
          <div class="col-12">
            <div class="small text-secondary">Resolved Manifest URL</div>
            <div class="small">{{ spicy_prompts.manifest_url or "-" }}</div>
          </div>
          {% if spicy_prompts.last_error %}
          <div class="col-12">
            <div class="alert alert-warning mb-0">
              <strong>Last refresh error:</strong> {{ spicy_prompts.last_error }}
            </div>
          </div>
          {% endif %}
        </div>
      </div>
      <div class="card card-soft p-3 mb-3">
        <h2 class="h6 mb-3">Prompt Packs</h2>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Pack</th><th>Source Path</th><th>Prompts</th><th>Updated</th></tr></thead>
            <tbody>
              {% for row in spicy_prompts.packs %}
              <tr>
                <td class="small">
                  <div class="fw-semibold">{{ row.pack_name }}</div>
                  <div class="text-secondary">{{ row.pack_id }}</div>
                </td>
                <td class="small">{{ row.source_path }}</td>
                <td class="small">{{ row.prompt_count }}</td>
                <td class="small">{{ row.updated_at or "-" }}</td>
              </tr>
              {% else %}
              <tr><td colspan="4" class="text-secondary">No cached prompt packs yet. Use Refresh From Repo after populating the content repo.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
      <div class="card card-soft p-3">
        <h2 class="h6 mb-3">Prompt Preview</h2>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Pack</th><th>Type</th><th>Category</th><th>Prompt</th><th>Tags</th></tr></thead>
            <tbody>
              {% for row in spicy_prompts.preview %}
              <tr>
                <td class="small">{{ row.pack_id }}</td>
                <td class="small">{{ row.prompt_type }}</td>
                <td class="small">{{ row.category }}</td>
                <td class="small">{{ row.text }}</td>
                <td class="small">{{ row.tags|join(", ") if row.tags else "-" }}</td>
              </tr>
              {% else %}
              <tr><td colspan="5" class="text-secondary">No cached prompts yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "logs" %}
      <div class="card card-soft p-3 mb-3">
        <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-2 mb-3">
          <div>
            <h1 class="h5 mb-1">Logs</h1>
            <p class="text-secondary small mb-0">Download or preview the latest log files.</p>
          </div>
          <a class="btn btn-outline-primary btn-sm" href="{{ url_for('logs_download') }}">Export all logs (ZIP)</a>
        </div>
        <form method="get" class="row g-2">
          <input type="hidden" name="_" value="1">
          <div class="col-12 col-lg-4">
            <label class="form-label" for="log">Log File</label>
            <select class="form-select" id="log" name="log" onchange="this.form.submit()">
              {% for option in log_options %}
              <option value="{{ option }}" {% if option == selected_log %}selected{% endif %}>{{ option }}</option>
              {% endfor %}
            </select>
          </div>
          <div class="col-12 col-lg-3">
            <label class="form-label" for="refresh_interval">Auto Refresh</label>
            <select class="form-select" id="refresh_interval" name="refresh" onchange="this.form.submit()">
              {% for interval in refresh_interval_options %}
              <option value="{{ interval }}" {% if interval == selected_refresh_interval %}selected{% endif %}>
                {% if interval == 0 %}Off{% else %}{{ interval }}s{% endif %}
              </option>
              {% endfor %}
            </select>
          </div>
        </form>
      </div>
      <div class="card card-soft p-3">
        <pre class="small mb-0 mobile-pre">{{ log_preview }}</pre>
      </div>
    {% elif page == "guilds" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-2">Discord Servers</h1>
        <p class="text-secondary mb-0">Choose which server the web GUI is currently managing. Guild-scoped pages use the selected server context.</p>
      </div>
      {% if selected_guild_card %}
      <div class="card card-soft p-3 mb-3">
        <div class="d-flex flex-column flex-md-row justify-content-between align-items-md-center gap-3">
          <div>
            <h2 class="h6 mb-1">Selected Guild Summary</h2>
            <p class="mb-1">{{ selected_guild_card.name }}</p>
            <p class="text-secondary small mb-0">
              ID: <code>{{ selected_guild_card.id }}</code>
              {% if selected_guild_card.member_count is not none %} | Members: {{ selected_guild_card.member_count }}{% endif %}
            </p>
          </div>
          <div class="d-flex flex-wrap gap-2">
            <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('moderation') }}">Open Moderation</a>
            <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('guild_settings') }}">Guild Settings</a>
            <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('command_permissions') }}">Command Permissions</a>
          </div>
        </div>
      </div>
      {% endif %}
      <div class="row g-3">
        {% for guild in guild_cards %}
        <div class="col-12 col-lg-6">
          <div class="card card-soft p-3 h-100">
            <div class="d-flex justify-content-between align-items-start gap-3 mb-2">
              <div>
                <h2 class="h6 mb-1">{{ guild.name }}</h2>
                <p class="small text-secondary mb-1">{{ guild.id }}</p>
                {% if guild.member_count is not none %}
                <p class="small text-secondary mb-0">Members: {{ guild.member_count }}</p>
                {% endif %}
              </div>
              {% if guild.selected %}
              <span class="badge text-bg-primary">Selected</span>
              {% endif %}
            </div>
            <form method="post" action="{{ url_for('select_guild') }}">
              <input type="hidden" name="guild_id" value="{{ guild.id }}">
              <input type="hidden" name="next_endpoint" value="dashboard">
              <button class="btn btn-primary btn-sm guild-card-action" type="submit" {% if guild.selected %}disabled{% endif %}>
                {% if guild.selected %}Currently Selected{% else %}Manage This Server{% endif %}
              </button>
            </form>
            {% if session.get("is_admin") %}
            <form method="post" action="{{ url_for('leave_guild_route') }}" class="mt-2" onsubmit="return confirm('Leave {{ guild.name|escape }}? The bot will immediately leave this server.');">
              <input type="hidden" name="guild_id" value="{{ guild.id }}">
              <button class="btn btn-outline-danger btn-sm guild-card-action" type="submit">Leave Guild</button>
            </form>
            {% endif %}
          </div>
        </div>
        {% else %}
        <div class="col-12">
          <div class="card card-soft p-3">
            <p class="text-secondary mb-0">No Discord servers are currently available to this bot.</p>
          </div>
        </div>
        {% endfor %}
      </div>
    {% elif page == "documentation" %}
      <div class="card card-soft p-3 mb-3">
        <div class="d-flex justify-content-between align-items-center gap-2">
          <div>
            <h1 class="h5 mb-1">Documentation</h1>
            <p class="text-secondary mb-0">Browse wiki pages packaged with this bot image.</p>
          </div>
          {% if github_wiki_url %}
          <a class="btn btn-outline-primary btn-sm" href="{{ github_wiki_url }}" target="_blank" rel="noreferrer">Open GitHub Wiki</a>
          {% endif %}
        </div>
            <div class="card card-soft p-3 mb-3">
        <div class="d-flex align-items-center justify-content-between mb-2">
          <h2 class="h6 mb-0">Command Status</h2>
          <a class="small" href="{{ url_for('command_permissions') }}">Manage</a>
        </div>
        {% if command_statuses %}
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead>
              <tr>
                <th>Command</th>
                <th>Access</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {% for command in command_statuses %}
              <tr>
                <td>
                  <div class="fw-semibold">{{ command.label }}</div>
                  {% if command.description %}
                  <div class="text-secondary small">{{ command.description }}</div>
                  {% endif %}
                </td>
                <td class="small">{{ command.access }}</td>
                <td>
                  {% if command.enabled %}
                  <span class="badge text-bg-success">Enabled</span>
                  {% else %}
                  <span class="badge text-bg-secondary">Disabled</span>
                  {% endif %}
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        {% else %}
        <p class="text-secondary small mb-0">Command status is unavailable.</p>
        {% endif %}
      </div>
</div>
      <div class="row g-3">
        <div class="col-12 col-lg-4">
          <div class="card card-soft p-3 h-100">
            <h2 class="h6 mb-3">Pages</h2>
            <div class="list-group list-group-flush documentation-sidebar">
              {% for item in documentation_pages %}
              <a class="list-group-item list-group-item-action documentation-link {% if item.slug == selected_doc_slug %}active{% endif %}" href="{{ url_for('documentation_page', page_slug=item.slug) }}">
                <div class="fw-semibold">{{ item.label }}</div>
                <div class="small {% if item.slug == selected_doc_slug %}text-white-50{% else %}text-secondary{% endif %}">{{ item.filename }}</div>
              </a>
              {% endfor %}
            </div>
          </div>
        </div>
        <div class="col-12 col-lg-8">
          <div class="card card-soft p-3">
            <h2 class="h6 mb-3">{{ documentation_title }}</h2>
            <pre class="small mb-0 mobile-pre">{{ documentation_content }}</pre>
          </div>
        </div>
      </div>
    {% elif page == "wiki" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">Wiki</h1>
        <form method="get" class="row g-2">
          <div class="col-12 col-lg-5">
            <label class="form-label" for="doc">Document</label>
            <select class="form-select" id="doc" name="doc" onchange="this.form.submit()">
              {% for option in wiki_files %}
              <option value="{{ option }}" {% if option == selected_wiki %}selected{% endif %}>{{ option }}</option>
              {% endfor %}
            </select>
          </div>
          <div class="col-12 col-lg-7 d-flex align-items-end">
            {% if github_wiki_url %}
            <a class="btn btn-outline-primary ms-lg-auto" href="{{ github_wiki_url }}" target="_blank" rel="noreferrer">Open GitHub Wiki</a>
            {% endif %}
          </div>
        </form>
      </div>
      <div class="card card-soft p-3">
        <pre class="small mb-0" style="white-space: pre-wrap;">{{ wiki_content }}</pre>
      </div>
    {% elif page == "command_permissions" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Command Permissions</h1>
        <p class="small text-secondary">Set command access mode, disable commands, and optionally restrict access to selected roles.</p>
        <form method="post" action="{{ url_for('command_permissions') }}">
          <div class="table-wrap">
            <table class="table table-sm align-middle">
              <thead><tr><th>Command</th><th>Default</th><th>Mode</th><th>Custom Role IDs</th></tr></thead>
              <tbody>
                {% for item in command_permissions.commands %}
                <tr data-command-row="{{ item.key }}">
                  <td class="small">
                    <div class="fw-semibold">{{ item.label }}</div>
                    <div class="text-secondary">{{ item.description }}</div>
                    <input type="hidden" name="command_key" value="{{ item.key }}">
                  </td>
                  <td class="small">{{ item.default_policy_label }}</td>
                  <td>
                    <select class="form-select" name="mode__{{ item.key }}" data-mode-select="{{ item.key }}" {% if not can_manage_guild %}disabled{% endif %}>
                      <option value="default" {% if item.mode == "default" %}selected{% endif %}>Default</option>
                      <option value="disabled" {% if item.mode == "disabled" %}selected{% endif %}>Disabled</option>
                      <option value="public" {% if item.mode == "public" %}selected{% endif %}>Public</option>
                      <option value="custom_roles" {% if item.mode == "custom_roles" %}selected{% endif %}>Custom roles</option>
                    </select>
                  </td>
                  <td>
                    <div class="command-roles" data-role-container="{{ item.key }}">
                      {% if role_options %}
                      <select class="form-select mb-2" name="role_ids__{{ item.key }}" multiple size="5" {% if not can_manage_guild %}disabled{% endif %}>
                        {% for role in role_options %}
                        <option value="{{ role.id }}" {% if role.id|string in item.role_id_strings %}selected{% endif %}>{{ role.name }} ({{ role.id }})</option>
                        {% endfor %}
                      </select>
                      {% endif %}
                      <input class="form-control" name="role_ids_text__{{ item.key }}" value="{{ item.role_ids_csv }}" placeholder="Comma-separated role IDs" {% if not can_manage_guild %}disabled{% endif %}>
                    </div>
                  </td>
                </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
                    <script>
            function toggleRoleInputs() {
              document.querySelectorAll('[data-mode-select]').forEach((select) => {
                const key = select.getAttribute('data-mode-select');
                const container = document.querySelector(`[data-role-container="${key}"]`);
                if (!container) {
                  return;
                }
                const isCustom = select.value === 'custom_roles';
                container.style.display = isCustom ? '' : 'none';
                container.querySelectorAll('select, input').forEach((el) => {
                  if (select.disabled) {
                    el.disabled = true;
                  } else {
                    el.disabled = !isCustom;
                  }
                });
              });
            }
            document.addEventListener('DOMContentLoaded', toggleRoleInputs);
            document.addEventListener('change', (event) => {
              if (event.target && event.target.matches('[data-mode-select]')) {
                toggleRoleInputs();
              }
            });
          </script>
          <button class="btn btn-primary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Save Command Permissions</button>
        </form>
      </div>
    {% elif page == "tag_responses" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Tag Responses</h1>
        <p class="small text-secondary">Edit JSON mapping used by `/tag`, `/tags`, and `!tag` message shortcuts.</p>
        <form method="post" action="{{ url_for('tag_responses') }}">
          <div class="mb-3">
            <textarea class="form-control font-monospace" rows="18" name="tag_json" {% if not can_manage_guild %}disabled{% endif %}>{{ tag_json }}</textarea>
          </div>
          <button class="btn btn-primary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Save Tag Responses</button>
        </form>
      </div>
    {% elif page == "users" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">Users</h1>
        <form method="post" action="{{ url_for('users_add') }}">
          <div class="row g-2">
            <div class="col-12 col-lg-2">
              <label class="form-label" for="new_display_name">Display Name</label>
              <input class="form-control" id="new_display_name" name="display_name" {% if not session.get("is_admin") %}disabled{% endif %}>
            </div>
            <div class="col-12 col-lg-2">
              <label class="form-label" for="new_first_name">First Name</label>
              <input class="form-control" id="new_first_name" name="first_name" {% if not session.get("is_admin") %}disabled{% endif %}>
            </div>
            <div class="col-12 col-lg-2">
              <label class="form-label" for="new_last_name">Last Name</label>
              <input class="form-control" id="new_last_name" name="last_name" {% if not session.get("is_admin") %}disabled{% endif %}>
            </div>
            <div class="col-12 col-lg-3">
              <label class="form-label" for="new_email">Email</label>
              <input class="form-control" id="new_email" name="email" type="email" required {% if not session.get("is_admin") %}disabled{% endif %}>
            </div>
            <div class="col-12 col-lg-3">
              <label class="form-label" for="new_password">Password</label>
              <input class="form-control" id="new_password" name="password" type="password" required {% if not session.get("is_admin") %}disabled{% endif %}>
            </div>
            <div class="col-12 col-lg-3">
              <label class="form-label" for="new_password_confirm">Confirm Password</label>
              <input class="form-control" id="new_password_confirm" name="confirm_password" type="password" required {% if not session.get("is_admin") %}disabled{% endif %}>
            </div>
            <div class="col-12 col-lg-2">
              <label class="form-label" for="new_role">Role</label>
              <select class="form-select" id="new_role" name="role" {% if not session.get("is_admin") %}disabled{% endif %}>
                <option value="read-only">Read-only</option>
                <option value="guild-admin">Guild Admin</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <div class="col-12 col-lg-1 d-flex align-items-end">
              <button class="btn btn-primary w-100" type="submit" {% if not session.get("is_admin") %}disabled{% endif %}>Add User</button>
            </div>
          </div>
        </form>
      </div>
      <div class="card card-soft p-3">
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Created</th><th>Manage</th></tr></thead>
            <tbody>
              {% for row in users %}
              <tr>
                <td>
                  <form method="post" action="{{ url_for('users_update') }}" class="row g-2">
                    <input type="hidden" name="current_email" value="{{ row.email }}">
                    <div class="col-12">
                      <input class="form-control form-control-sm" name="display_name" value="{{ row.display_name or '' }}" placeholder="Display name" {% if not session.get("is_admin") %}disabled{% endif %}>
                    </div>
                    <div class="col-12 col-md-6">
                      <input class="form-control form-control-sm" name="first_name" value="{{ row.first_name or '' }}" placeholder="First name" {% if not session.get("is_admin") %}disabled{% endif %}>
                    </div>
                    <div class="col-12 col-md-6">
                      <input class="form-control form-control-sm" name="last_name" value="{{ row.last_name or '' }}" placeholder="Last name" {% if not session.get("is_admin") %}disabled{% endif %}>
                    </div>
                    <div class="col-12">
                      <input class="form-control form-control-sm" name="email" type="email" value="{{ row.email }}" {% if not session.get("is_admin") %}disabled{% endif %}>
                    </div>
                </td>
                <td class="small">{{ row.email }}</td>
                <td>
                    <select class="form-select form-select-sm" name="role" {% if not session.get("is_admin") %}disabled{% endif %}>
                      <option value="read-only" {% if not row.is_admin and not row.is_guild_admin %}selected{% endif %}>Read-only</option>
                      <option value="guild-admin" {% if row.is_guild_admin %}selected{% endif %}>Guild Admin</option>
                      <option value="admin" {% if row.is_admin %}selected{% endif %}>Admin</option>
                    </select>
                </td>
                <td class="small">{{ row.created_at }}</td>
                <td>
                    <input class="form-control form-control-sm mb-2" name="new_password" type="password" placeholder="Reset password" {% if not session.get("is_admin") %}disabled{% endif %}>
                    <input class="form-control form-control-sm mb-2" name="confirm_new_password" type="password" placeholder="Confirm new password" {% if not session.get("is_admin") %}disabled{% endif %}>
                    <input class="form-control form-control-sm mb-2" name="admin_current_password" type="password" placeholder="Your current password" {% if not session.get("is_admin") %}disabled{% endif %}>
                    <button class="btn btn-sm btn-primary me-2" type="submit" {% if not session.get("is_admin") %}disabled{% endif %}>Save</button>
                  </form>
                  {% if row.email != session.get("user") %}
                  <form method="post" action="{{ url_for('users_delete') }}" class="mt-2">
                    <input type="hidden" name="email" value="{{ row.email }}">
                    <button class="btn btn-sm btn-outline-danger" type="submit" {% if not session.get("is_admin") %}disabled{% endif %}>Delete</button>
                  </form>
                  {% else %}
                  <span class="small text-secondary">Current user</span>
                  {% endif %}
                </td>
              </tr>
              {% else %}
              <tr><td colspan="5" class="text-secondary">No users available.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "guild_access" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">Guild Access</h1>
        <p class="text-secondary small mb-3">Create groups of guilds and assign users who can manage them.</p>
        <form method="post" action="{{ url_for('guild_access_create') }}">
          <div class="row g-2 align-items-end">
            <div class="col-12 col-lg-6">
              <label class="form-label" for="group_name">Group Name</label>
              <input class="form-control" id="group_name" name="group_name" placeholder="Community Moderators" required>
            </div>
            <div class="col-12 col-lg-2">
              <button class="btn btn-primary w-100" type="submit">Create Group</button>
            </div>
          </div>
        </form>
      </div>
      <div class="card card-soft p-3">
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Group</th><th>Guilds</th><th>Users</th><th>Actions</th></tr></thead>
            <tbody>
              {% for group in guild_access_groups %}
              <tr>
                <td class="fw-semibold">{{ group.name }}</td>
                <td>
                  <form method="post" action="{{ url_for('guild_access_update') }}" class="d-grid gap-2">
                    <input type="hidden" name="group_id" value="{{ group.id }}">
                    <select class="form-select" name="guild_ids" multiple size="6">
                      {% for guild in guild_access_guilds %}
                      <option value="{{ guild.id }}" {% if guild.id in group.guild_ids %}selected{% endif %}>{{ guild.name }}</option>
                      {% endfor %}
                    </select>
                </td>
                <td>
                    <select class="form-select" name="user_emails" multiple size="6">
                      {% for user in guild_access_users %}
                      <option value="{{ user.email }}" {% if user.email in group.user_emails %}selected{% endif %}>{{ user.display_name or user.email }}</option>
                      {% endfor %}
                    </select>
                </td>
                <td>
                    <button class="btn btn-sm btn-primary w-100" type="submit">Save</button>
                  </form>
                  <form method="post" action="{{ url_for('guild_access_delete') }}" class="mt-2" onsubmit="return confirm('Delete this guild access group?');">
                    <input type="hidden" name="group_id" value="{{ group.id }}">
                    <button class="btn btn-sm btn-outline-danger w-100" type="submit">Delete</button>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="4" class="text-secondary">No guild access groups defined.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "honeypot" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Honeypot &amp; Join Guard</h1>
        <p class="small text-secondary">Group monitoring, join-guard rules, and enforcement settings.</p>
      </div>
    {% elif page == "role_access" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Role Access</h1>
        <p class="small text-secondary">Map roles, required roles, and access rules.</p>
      </div>
    {% elif page == "reaction_roles" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Reaction Roles</h1>
        <p class="small text-secondary">Message reaction role assignments.</p>
      </div>
    {% elif page == "discourse" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Discourse</h1>
        <p class="small text-secondary">Forum integration and sync settings.</p>
      </div>
    {% elif page == "observability" %}
      <div class="row g-3 mb-3">
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Process Uptime</p>
            <p class="mb-0 fs-5 fw-bold">{{ observability.uptime }}</p>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Process CPU</p>
            <p class="mb-0 fs-5 fw-bold">{{ observability.process_cpu }}</p>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">RSS Memory</p>
            <p class="mb-0 fs-5 fw-bold">{{ observability.rss }}</p>
          </div>
        </div>
      </div>
      <div class="row g-3 mb-3">
        <div class="col-12 col-md-6">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Read I/O Rate</p>
            <p class="mb-0 fs-5 fw-bold">{{ observability.io_read }}</p>
          </div>
        </div>
        <div class="col-12 col-md-6">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Write I/O Rate</p>
            <p class="mb-0 fs-5 fw-bold">{{ observability.io_write }}</p>
          </div>
        </div>
      </div>
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Observability</h1>
        <p class="small text-secondary mb-2">Sampled at {{ observability.sampled_at }} UTC.</p>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Metric</th><th>Current</th><th>Min</th><th>Avg</th><th>Max</th></tr></thead>
            <tbody>
              {% for row in observability_rows %}
              <tr>
                <td>{{ row.label }}</td>
                <td>{{ row.current }}</td>
                <td>{{ row.min }}</td>
                <td>{{ row.avg }}</td>
                <td>{{ row.max }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "bot_profile" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">Bot Profile</h1>
        {% if bot_profile.ok %}
        <div class="row g-3">
          <div class="col-12 col-lg-4">
            {% if bot_profile.avatar_url %}
            <img src="{{ bot_profile.avatar_url }}" alt="Bot Avatar" class="img-fluid rounded border">
            {% else %}
            <div class="small text-secondary">No avatar available.</div>
            {% endif %}
          </div>
          <div class="col-12 col-lg-8">
            <p class="mb-1"><strong>Username:</strong> {{ bot_profile.name }}</p>
            <p class="mb-1"><strong>Global Name:</strong> {{ bot_profile.global_name or "-" }}</p>
            <p class="mb-1"><strong>Server Nickname:</strong> {{ bot_profile.server_nickname or "-" }}</p>
            <p class="mb-1"><strong>Guild:</strong> {{ bot_profile.guild_name or "-" }}</p>
            <p class="mb-0"><strong>Bot ID:</strong> {{ bot_profile.id }}</p>
          </div>
        </div>
        {% else %}
        <p class="text-danger mb-0">{{ bot_profile.error or "Bot profile is unavailable." }}</p>
        {% endif %}
            <div class="card card-soft p-3 mb-3">
        <div class="d-flex align-items-center justify-content-between mb-2">
          <h2 class="h6 mb-0">Command Status</h2>
          <a class="small" href="{{ url_for('command_permissions') }}">Manage</a>
        </div>
        {% if command_statuses %}
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead>
              <tr>
                <th>Command</th>
                <th>Access</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {% for command in command_statuses %}
              <tr>
                <td>
                  <div class="fw-semibold">{{ command.label }}</div>
                  {% if command.description %}
                  <div class="text-secondary small">{{ command.description }}</div>
                  {% endif %}
                </td>
                <td class="small">{{ command.access }}</td>
                <td>
                  {% if command.enabled %}
                  <span class="badge text-bg-success">Enabled</span>
                  {% else %}
                  <span class="badge text-bg-secondary">Disabled</span>
                  {% endif %}
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        {% else %}
        <p class="text-secondary small mb-0">Command status is unavailable.</p>
        {% endif %}
      </div>
</div>
      <div class="row g-3">
        <div class="col-12 col-lg-6">
          <div class="card card-soft p-3 h-100">
            <h2 class="h6 mb-3">Update Identity</h2>
            <form method="post" action="{{ url_for('bot_profile') }}">
              <input type="hidden" name="action" value="identity">
              <div class="mb-3">
                <label class="form-label" for="bot_name">Bot Username (optional)</label>
                <input class="form-control" id="bot_name" name="bot_name" placeholder="WickedYodaBot" {% if not can_manage_guild %}disabled{% endif %}>
                <div class="form-text">Leave blank to keep current username.</div>
              </div>
              <div class="mb-3">
                <label class="form-label" for="server_nickname">Server Nickname (optional)</label>
                <input class="form-control" id="server_nickname" name="server_nickname" placeholder="Wicked Yoda's Little Helper" {% if not can_manage_guild %}disabled{% endif %}>
                <div class="form-text">Nickname applies only to selected guild.</div>
              </div>
              <div class="form-check mb-3">
                <input class="form-check-input" type="checkbox" id="clear_server_nickname" name="clear_server_nickname" value="1" {% if not can_manage_guild %}disabled{% endif %}>
                <label class="form-check-label" for="clear_server_nickname">Clear server nickname</label>
              </div>
              <button class="btn btn-primary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Update Bot Profile</button>
            </form>
          </div>
        </div>
        <div class="col-12 col-lg-6">
          <div class="card card-soft p-3 h-100">
            <h2 class="h6 mb-3">Update Avatar</h2>
            <p class="small text-secondary">Upload PNG/JPG/JPEG/WEBP/GIF image (max {{ max_avatar_upload_bytes }} bytes).</p>
            <form method="post" action="{{ url_for('bot_profile') }}" enctype="multipart/form-data">
              <input type="hidden" name="action" value="avatar">
              <div class="mb-3">
                <label class="form-label" for="avatar_file">Avatar Image</label>
                <input class="form-control" id="avatar_file" name="avatar_file" type="file" accept=".png,.jpg,.jpeg,.webp,.gif,image/*" required {% if not can_manage_guild %}disabled{% endif %}>
              </div>
              <button class="btn btn-primary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Upload Avatar</button>
            </form>
          </div>
        </div>
      </div>
    {% elif page == "account" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Account</h1>
        {% if session.get("password_rotation_required") %}
        <div class="alert alert-warning">Password rotation is required. Update your password before continuing.</div>
        {% endif %}
        <div class="row g-3">
          <div class="col-12 col-xl-7">
            <form method="post" action="{{ url_for('account') }}">
              <input type="hidden" name="action" value="profile">
              <div class="row g-2">
                <div class="col-12">
                  <label class="form-label" for="account_display_name">Display Name</label>
                  <input class="form-control" id="account_display_name" name="display_name" value="{{ account_user.display_name or '' }}">
                </div>
                <div class="col-12 col-md-6">
                  <label class="form-label" for="account_first_name">First Name</label>
                  <input class="form-control" id="account_first_name" name="first_name" value="{{ account_user.first_name or '' }}">
                </div>
                <div class="col-12 col-md-6">
                  <label class="form-label" for="account_last_name">Last Name</label>
                  <input class="form-control" id="account_last_name" name="last_name" value="{{ account_user.last_name or '' }}">
                </div>
              </div>
              <div class="mt-3">
                <label class="form-label" for="account_email">Email</label>
                <input class="form-control" id="account_email" name="email" type="email" value="{{ account_user.email or '' }}" required>
              </div>
              <div class="mt-3">
                <label class="form-label" for="account_discord_user_id">Discord User ID (optional)</label>
                <input class="form-control" id="account_discord_user_id" name="discord_user_id" type="number" placeholder="123456789012345678" value="{{ account_user.discord_user_id or '' }}">
                <div class="form-text">Optional public Discord account link for your web profile.</div>
              </div>
              <div class="mt-3">
                <label class="form-label" for="account_profile_password">Current Password</label>
                <input class="form-control" id="account_profile_password" name="current_password" type="password" required>
                <div class="form-text">Required to change your email or name.</div>
              </div>
              <button class="btn btn-primary mt-3" type="submit">Update Profile</button>
            </form>
          </div>
          <div class="col-12 col-xl-5">
            <form method="post" action="{{ url_for('account') }}">
              <input type="hidden" name="action" value="password">
              <div class="mb-3">
                <label class="form-label" for="current_password">Current Password</label>
                <input class="form-control" id="current_password" name="current_password" type="password" required>
              </div>
              <div class="mb-3">
                <label class="form-label" for="new_password">New Password</label>
                <input class="form-control" id="new_password" name="new_password" type="password" {% if session.get("password_rotation_required") %}required{% endif %}>
              </div>
              <div class="mb-3">
                <label class="form-label" for="confirm_new_password">Confirm New Password</label>
                <input class="form-control" id="confirm_new_password" name="confirm_new_password" type="password" {% if session.get("password_rotation_required") %}required{% endif %}>
              </div>
              <button class="btn btn-primary" type="submit">Update Password</button>
            </form>
          </div>
        </div>
      </div>
    {% elif page == "guild_settings" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Guild Settings</h1>
        <form method="post" action="{{ url_for('guild_settings') }}">
          <div class="mb-3">
            <label class="form-label" for="bot_log_channel_id">Bot Log Channel</label>
            <select class="form-select" id="bot_log_channel_id" name="bot_log_channel_id" {% if not can_manage_guild %}disabled{% endif %}>
              <option value="">Use global default (env Bot_Log_Channel)</option>
              {% for channel in notification_channels %}
              <option value="{{ channel.id }}" {% if selected_log_channel_id == channel.id|string %}selected{% endif %}>
                {{ channel.name }} ({{ channel.id }})
              </option>
              {% endfor %}
            </select>
            <div class="form-text">This guild-specific channel receives bot action logs and overrides the global env value.</div>
          </div>
          <div class="mb-3">
            <label class="form-label" for="uptime_alert_channel_id">Uptime Alert Channel</label>
            <select class="form-select" id="uptime_alert_channel_id" name="uptime_alert_channel_id" {% if not can_manage_guild %}disabled{% endif %}>
              <option value="">Use bot log channel</option>
              {% for channel in notification_channels %}
              <option value="{{ channel.id }}" {% if selected_uptime_channel_id == channel.id|string %}selected{% endif %}>
                {{ channel.name }} ({{ channel.id }})
              </option>
              {% endfor %}
            </select>
            <div class="form-text">Optional override for uptime monitor alerts; falls back to the bot log channel when unset.</div>
          </div>
          <div class="mb-3">
            <label class="form-label" for="dnd_category_id">DND Allowed Category</label>
            <select class="form-select" id="dnd_category_id" name="dnd_category_id" {% if not can_manage_guild %}disabled{% endif %}>
              <option value="">All categories allowed</option>
              {% for channel in notification_channels %}
              {% if channel.type == 'category' %}
              <option value="{{ channel.id }}" {% if selected_dnd_category_id == channel.id|string %}selected{% endif %}>
                {{ channel.name }} ({{ channel.id }})
              </option>
              {% endif %}
              {% endfor %}
            </select>
            <div class="form-text">When set, D&D commands only respond inside this category, its sub-channels, and sub-threads.</div>
          </div>
          <button class="btn btn-primary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Save Guild Settings</button>
        </form>
      </div>
    {% elif page == "moderation" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-1">Moderation</h1>
        <p class="text-secondary small mb-0">All moderation controls below apply only to the currently selected guild.</p>
      </div>
      <details class="collapsible-card mb-3" open>
        <summary>
          <span>Filter Settings</span>
          <span class="text-secondary small">Warnings, banned words, and automatic actions</span>
        </summary>
        <div class="collapsible-card-body">
          <form method="post" action="{{ url_for('moderation') }}">
            <div class="mb-3">
              <label class="form-label" for="moderation_enabled">Moderation Filter</label>
              <select class="form-select" id="moderation_enabled" name="moderation_enabled" {% if not can_manage_guild %}disabled{% endif %}>
                <option value="0" {% if not moderation_settings.moderation_enabled %}selected{% endif %}>Disabled</option>
                <option value="1" {% if moderation_settings.moderation_enabled %}selected{% endif %}>Enabled</option>
              </select>
              <div class="form-text">When enabled, messages containing banned words trigger warnings.</div>
            </div>
            <div class="mb-3">
              <label class="form-label" for="moderation_words">Banned Words (one per line)</label>
              <textarea class="form-control" id="moderation_words" name="moderation_words" rows="6" {% if not can_manage_guild %}disabled{% endif %}>{{ moderation_words_text }}</textarea>
              <div class="form-text">Use single words or short phrases. Matching is case-insensitive.</div>
            </div>
            <div class="row g-3">
              <div class="col-12 col-md-4">
                <label class="form-label" for="moderation_warning_window_hours">Warning Window</label>
                <select class="form-select" id="moderation_warning_window_hours" name="moderation_warning_window_hours" {% if not can_manage_guild %}disabled{% endif %}>
                  {% for value in moderation_window_options %}
                  <option value="{{ value }}" {% if moderation_settings.moderation_warning_window_hours == value %}selected{% endif %}>{{ value }} hours</option>
                  {% endfor %}
                </select>
              </div>
              <div class="col-12 col-md-4">
                <label class="form-label" for="moderation_warning_threshold">Max Warnings</label>
                <select class="form-select" id="moderation_warning_threshold" name="moderation_warning_threshold" {% if not can_manage_guild %}disabled{% endif %}>
                  {% for value in moderation_threshold_options %}
                  <option value="{{ value }}" {% if moderation_settings.moderation_warning_threshold == value %}selected{% endif %}>{{ value }} warnings</option>
                  {% endfor %}
                </select>
              </div>
              <div class="col-12 col-md-4">
                <label class="form-label" for="moderation_action">Action</label>
                <select class="form-select" id="moderation_action" name="moderation_action" {% if not can_manage_guild %}disabled{% endif %}>
                  <option value="timeout" {% if moderation_settings.moderation_action == "timeout" %}selected{% endif %}>Timeout / Mute</option>
                  <option value="warn_only" {% if moderation_settings.moderation_action == "warn_only" %}selected{% endif %}>Warn Only</option>
                </select>
              </div>
            </div>
            <div class="row g-3 mt-1">
              <div class="col-12 col-md-4">
                <label class="form-label" for="moderation_timeout_minutes">Timeout Duration</label>
                <select class="form-select" id="moderation_timeout_minutes" name="moderation_timeout_minutes" {% if not can_manage_guild %}disabled{% endif %}>
                  {% for value in moderation_timeout_options %}
                  <option value="{{ value }}" {% if moderation_settings.moderation_timeout_minutes == value %}selected{% endif %}>{{ value }} minutes</option>
                  {% endfor %}
                </select>
                <div class="form-text">Only used when action is Timeout.</div>
              </div>
            </div>
            <button class="btn btn-primary mt-3" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Save Moderation Settings</button>
          </form>
        </div>
      </details>
      <details class="collapsible-card mb-3">
        <summary>
          <span>Member Actions</span>
          <span class="text-secondary small">Kick, ban, timeout, and remove timeout</span>
        </summary>
        <div class="collapsible-card-body">
          {% if guild_member_options %}
          <div class="row g-3">
            <div class="col-12 col-xl-6">
              <form method="post" action="{{ url_for('kick_guild_member_route') }}" class="card card-soft p-3 h-100" data-member-confirm="kick" data-confirm-guild="{{ selected_guild_name|escape }}">
                <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">
                <h4 class="h6 mb-2">Kick</h4>
                <div class="mb-2">
                  <label class="form-label small" for="moderation-kick-member">Member</label>
                  <select class="form-select form-select-sm" id="moderation-kick-member" name="member_id" required>
                    <option value="">Select a member</option>
                    {% for option in guild_member_options %}
                    <option value="{{ option.value }}">{{ option.label }}</option>
                    {% endfor %}
                  </select>
                </div>
                <div class="mb-2">
                  <label class="form-label small" for="moderation-kick-reason">Reason</label>
                  <input class="form-control form-control-sm" id="moderation-kick-reason" type="text" name="reason" maxlength="256" placeholder="Web admin kick request">
                </div>
                <button class="btn btn-outline-danger btn-sm guild-card-action" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Kick Member</button>
              </form>
            </div>
            <div class="col-12 col-xl-6">
              <form method="post" action="{{ url_for('ban_guild_member_route') }}" class="card card-soft p-3 h-100" data-member-confirm="ban" data-confirm-guild="{{ selected_guild_name|escape }}">
                <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">
                <h4 class="h6 mb-2">Ban</h4>
                <div class="mb-2">
                  <label class="form-label small" for="moderation-ban-member">Member</label>
                  <select class="form-select form-select-sm" id="moderation-ban-member" name="member_id" required>
                    <option value="">Select a member</option>
                    {% for option in guild_member_options %}
                    <option value="{{ option.value }}">{{ option.label }}</option>
                    {% endfor %}
                  </select>
                </div>
                <div class="mb-2">
                  <label class="form-label small" for="moderation-ban-delete-days">Delete Message History</label>
                  <select class="form-select form-select-sm" id="moderation-ban-delete-days" name="delete_days">
                    {% for day in range(0, 8) %}
                    <option value="{{ day }}">{{ day }} day{% if day != 1 %}s{% endif %}</option>
                    {% endfor %}
                  </select>
                </div>
                <div class="mb-2">
                  <label class="form-label small" for="moderation-ban-reason">Reason</label>
                  <input class="form-control form-control-sm" id="moderation-ban-reason" type="text" name="reason" maxlength="256" placeholder="Web admin ban request">
                </div>
                <button class="btn btn-outline-danger btn-sm guild-card-action" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Ban Member</button>
              </form>
            </div>
            <div class="col-12 col-xl-6">
              <form method="post" action="{{ url_for('timeout_guild_member_route') }}" class="card card-soft p-3 h-100" onsubmit="return confirm('Timeout the selected member in {{ selected_guild_name|escape }}?');">
                <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">
                <h4 class="h6 mb-2">Timeout</h4>
                <div class="mb-2">
                  <label class="form-label small" for="moderation-timeout-member">Member</label>
                  <select class="form-select form-select-sm" id="moderation-timeout-member" name="member_id" required>
                    <option value="">Select a member</option>
                    {% for option in guild_member_options %}
                    <option value="{{ option.value }}">{{ option.label }}</option>
                    {% endfor %}
                  </select>
                </div>
                <div class="mb-2">
                  <label class="form-label small" for="moderation-timeout-minutes">Minutes</label>
                  <select class="form-select form-select-sm" id="moderation-timeout-minutes" name="minutes">
                    <option value="5">5 minutes</option>
                    <option value="10">10 minutes</option>
                    <option value="30">30 minutes</option>
                    <option value="60">1 hour</option>
                    <option value="360">6 hours</option>
                    <option value="1440">24 hours</option>
                    <option value="10080">7 days</option>
                  </select>
                </div>
                <div class="mb-2">
                  <label class="form-label small" for="moderation-timeout-reason">Reason</label>
                  <input class="form-control form-control-sm" id="moderation-timeout-reason" type="text" name="reason" maxlength="256" placeholder="Web admin timeout request">
                </div>
                <button class="btn btn-outline-warning btn-sm guild-card-action" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Timeout Member</button>
              </form>
            </div>
            <div class="col-12 col-xl-6">
              <form method="post" action="{{ url_for('untimeout_guild_member_route') }}" class="card card-soft p-3 h-100" onsubmit="return confirm('Remove timeout for the selected member in {{ selected_guild_name|escape }}?');">
                <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">
                <h4 class="h6 mb-2">Remove Timeout</h4>
                <div class="mb-2">
                  <label class="form-label small" for="moderation-untimeout-member">Member</label>
                  <select class="form-select form-select-sm" id="moderation-untimeout-member" name="member_id" required>
                    <option value="">Select a member</option>
                    {% for option in guild_member_options %}
                    <option value="{{ option.value }}">{{ option.label }}</option>
                    {% endfor %}
                  </select>
                </div>
                <div class="mb-2">
                  <label class="form-label small" for="moderation-untimeout-reason">Reason</label>
                  <input class="form-control form-control-sm" id="moderation-untimeout-reason" type="text" name="reason" maxlength="256" placeholder="Web admin untimeout request">
                </div>
                <button class="btn btn-outline-primary btn-sm guild-card-action" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Remove Timeout</button>
              </form>
            </div>
          </div>
          {% elif not members_intent_enabled %}
          <p class="text-secondary small mb-0">Member picker is limited because `ENABLE_MEMBERS_INTENT` is disabled. Enable it to manage the full guild roster from the web GUI.</p>
          {% else %}
          <p class="text-secondary small mb-0">No kickable members are currently available in this guild.</p>
          {% endif %}
        </div>
      </details>
      <details class="collapsible-card mb-3">
        <summary>
          <span>Visible Members</span>
          <span class="text-secondary small">Search and browse members visible to this guild context</span>
        </summary>
        <div class="collapsible-card-body">
          {% if guild_members %}
          <div class="row g-2 align-items-end mb-2">
            <div class="col-12 col-md-8">
              <label class="form-label small" for="guild-member-search-{{ selected_guild_id }}">Search Members</label>
              <input
                class="form-control form-control-sm"
                id="guild-member-search-{{ selected_guild_id }}"
                type="search"
                placeholder="Filter by display name, username, or ID"
                data-member-search
                data-member-search-target="guild-member-table-{{ selected_guild_id }}"
                data-member-count-target="guild-member-count-{{ selected_guild_id }}"
                data-member-page-target="guild-member-pagination-{{ selected_guild_id }}"
              >
            </div>
            <div class="col-12 col-md-4">
              <label class="form-label small" for="guild-member-page-size-{{ selected_guild_id }}">Rows Per Page</label>
              <select
                class="form-select form-select-sm"
                id="guild-member-page-size-{{ selected_guild_id }}"
                data-member-page-size
                data-member-search-target="guild-member-table-{{ selected_guild_id }}"
                data-member-count-target="guild-member-count-{{ selected_guild_id }}"
                data-member-page-target="guild-member-pagination-{{ selected_guild_id }}"
              >
                <option value="10">10</option>
                <option value="25" selected>25</option>
                <option value="50">50</option>
                <option value="100">100</option>
              </select>
            </div>
            <div class="col-12">
              <p class="text-secondary small mt-1 mb-0" id="guild-member-count-{{ selected_guild_id }}">Showing {{ [guild_members|length, 25]|min }} of {{ guild_members|length }} visible members.</p>
            </div>
          </div>
          <div class="table-responsive">
            <table class="table table-sm align-middle mb-0" id="guild-member-table-{{ selected_guild_id }}">
              <thead>
                <tr>
                  <th scope="col">Display Name</th>
                  <th scope="col">Discord User</th>
                  <th scope="col">ID</th>
                </tr>
              </thead>
              <tbody>
                {% for member in guild_members %}
                <tr data-member-row data-member-search-text="{{ (member.name ~ ' ' ~ member.username ~ ' ' ~ member.id)|lower }}">
                  <td>{{ member.name }}</td>
                  <td class="text-secondary small">{{ member.username }}</td>
                  <td class="text-secondary small">{{ member.id }}</td>
                </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
          <div class="d-flex flex-column flex-sm-row justify-content-between align-items-sm-center gap-2 mt-3" id="guild-member-pagination-{{ selected_guild_id }}">
            <p class="text-secondary small mb-0" data-member-page-status>Page 1</p>
            <div class="d-flex gap-2">
              <button class="btn btn-outline-secondary btn-sm" type="button" data-member-prev>Previous</button>
              <button class="btn btn-outline-secondary btn-sm" type="button" data-member-next>Next</button>
            </div>
          </div>
          {% elif not members_intent_enabled %}
          <p class="text-secondary small mb-0">Member list visibility is limited because `ENABLE_MEMBERS_INTENT` is disabled.</p>
          {% else %}
          <p class="text-secondary small mb-0">No members are currently visible for this guild.</p>
          {% endif %}
        </div>
      </details>
    {% elif page == "settings" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Runtime Settings</h1>
        <p class="text-secondary small mb-3">These settings apply globally to the bot runtime, not a single guild.</p>
        <form method="post" action="{{ url_for('settings_save') }}">
          <div class="row g-3">
            {% for item in settings %}
            <div class="col-12 col-lg-6">
              <label class="form-label" for="field_{{ item.key }}"><code>{{ item.key }}</code></label>
              {% if item.pending_restart %}
              <div class="badge bg-warning text-dark ms-2">Pending restart</div>
              {% endif %}
              {% if item.options %}
              <select class="form-select" id="field_{{ item.key }}" name="{{ item.key }}" {% if not session.get("is_admin") %}disabled{% endif %}>
                {% for option in item.options %}
                {% if option is mapping %}
                <option value="{{ option.value }}" {% if option.value == item.value %}selected{% endif %}>{{ option.label }}</option>
                {% else %}
                <option value="{{ option }}" {% if option == item.value %}selected{% endif %}>{{ option }}</option>
                {% endif %}
                {% endfor %}
              </select>
              {% elif item.is_sensitive %}
              <input class="form-control" id="field_{{ item.key }}" name="{{ item.key }}" value="{{ item.masked_value }}" autocomplete="off" {% if not session.get("is_admin") %}disabled{% endif %}>
              <div class="form-text">Leave as `********` to keep existing value.</div>
              {% else %}
              <input class="form-control" id="field_{{ item.key }}" name="{{ item.key }}" value="{{ item.value }}" {% if not session.get("is_admin") %}disabled{% endif %}>
              {% endif %}
            </div>
            {% endfor %}
          </div>
          <div class="mt-3 d-flex gap-2">
            <button class="btn btn-primary" type="submit" {% if not session.get("is_admin") %}disabled{% endif %}>Save Settings</button>
            <span class="small text-secondary align-self-center">Changes are written to env file; restart container to apply bot runtime changes.</span>
          </div>
        </form>
      </div>
    {% endif %}
  </main>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  <script>
    (function () {
      const storageKey = "web_theme_choice";
      const fallbackTheme = "black";
      const allowed = { light: true, black: true, forest: true, ember: true, ice: true };

      function setTheme(theme) {
        const selected = allowed[theme] ? theme : fallbackTheme;
        document.body.setAttribute("data-theme", selected);
        try { window.localStorage.setItem(storageKey, selected); } catch (error) {}
        document.querySelectorAll("[data-theme-choice]").forEach((btn) => {
          btn.classList.toggle("active", btn.getAttribute("data-theme-choice") === selected);
        });
      }

      let storedTheme = fallbackTheme;
      try { storedTheme = window.localStorage.getItem(storageKey) || fallbackTheme; } catch (error) {}
      setTheme(storedTheme);

      document.querySelectorAll("[data-theme-choice]").forEach((btn) => {
        btn.addEventListener("click", function () { setTheme(btn.getAttribute("data-theme-choice")); });
      });

      document.querySelectorAll(".nav-page-select").forEach((navSelect) => {
        navSelect.addEventListener("change", function () {
          const target = navSelect.value || "";
          if (!target) { return; }
          const selectedOption = navSelect.options[navSelect.selectedIndex];
          const isExternal = selectedOption && selectedOption.dataset && selectedOption.dataset.external === "1";
          if (isExternal) {
            window.open(target, "_blank", "noopener");
          } else {
            window.location.href = target;
          }
          navSelect.value = "";
        });
      });

      const refreshValue = Number("{{ selected_refresh_interval|default(0) }}");
      if (refreshValue && refreshValue > 0) {
        window.setTimeout(() => {
          const url = new URL(window.location.href);
          url.searchParams.set("refresh", String(refreshValue));
          window.location.href = url.toString();
        }, refreshValue * 1000);
      }

      const csrfToken = "{{ csrf_token }}";
      if (csrfToken) {
        document.querySelectorAll("form[method='post'], form[method='POST']").forEach((form) => {
          if (form.querySelector("input[name='csrf_token']")) { return; }
          const input = document.createElement("input");
          input.type = "hidden";
          input.name = "csrf_token";
          input.value = csrfToken;
          form.appendChild(input);
        });
      }

      document.querySelectorAll("[data-member-search]").forEach((input) => {
        const tableId = input.getAttribute("data-member-search-target");
        const countId = input.getAttribute("data-member-count-target");
        const pageId = input.getAttribute("data-member-page-target");
        const table = tableId ? document.getElementById(tableId) : null;
        const countNode = countId ? document.getElementById(countId) : null;
        const pageNode = pageId ? document.getElementById(pageId) : null;
        const pageStatusNode = pageNode ? pageNode.querySelector("[data-member-page-status]") : null;
        const prevButton = pageNode ? pageNode.querySelector("[data-member-prev]") : null;
        const nextButton = pageNode ? pageNode.querySelector("[data-member-next]") : null;
        const pageSizeSelect = document.querySelector(`[data-member-page-size][data-member-search-target="${tableId}"]`);
        if (!table) { return; }
        const rows = Array.from(table.querySelectorAll("[data-member-row]"));
        const total = rows.length;
        let currentPage = 1;
        const updateRows = () => {
          const query = String(input.value || "").trim().toLowerCase();
          const pageSize = Math.max(1, Number(pageSizeSelect && "value" in pageSizeSelect ? pageSizeSelect.value : 25) || 25);
          const filteredRows = [];
          rows.forEach((row) => {
            const haystack = String(row.getAttribute("data-member-search-text") || "");
            const matches = !query || haystack.includes(query);
            if (matches) {
              filteredRows.push(row);
            }
            row.style.display = "none";
          });
          const visible = filteredRows.length;
          const pageCount = Math.max(1, Math.ceil(visible / pageSize));
          currentPage = Math.min(currentPage, pageCount);
          const start = (currentPage - 1) * pageSize;
          const end = start + pageSize;
          filteredRows.forEach((row, index) => {
            row.style.display = index >= start && index < end ? "" : "none";
          });
          if (countNode) {
            const shown = filteredRows.slice(start, end).length;
            countNode.textContent = `Showing ${shown} of ${visible} filtered members (${total} total).`;
          }
          if (pageStatusNode) {
            pageStatusNode.textContent = `Page ${currentPage} of ${pageCount}`;
          }
          if (prevButton) {
            prevButton.disabled = currentPage <= 1 || visible === 0;
          }
          if (nextButton) {
            nextButton.disabled = currentPage >= pageCount || visible === 0;
          }
        };
        input.addEventListener("input", () => {
          currentPage = 1;
          updateRows();
        });
        if (pageSizeSelect) {
          pageSizeSelect.addEventListener("change", () => {
            currentPage = 1;
            updateRows();
          });
        }
        if (prevButton) {
          prevButton.addEventListener("click", () => {
            currentPage = Math.max(1, currentPage - 1);
            updateRows();
          });
        }
        if (nextButton) {
          nextButton.addEventListener("click", () => {
            currentPage += 1;
            updateRows();
          });
        }
        updateRows();
      });

      document.querySelectorAll("[data-password-toggle]").forEach((toggle) => {
        const targetId = toggle.getAttribute("data-password-toggle");
        const target = targetId ? document.getElementById(targetId) : null;
        if (!target) { return; }
        toggle.addEventListener("change", () => {
          target.type = toggle.checked ? "text" : "password";
        });
      });

      document.querySelectorAll("form[data-member-confirm]").forEach((form) => {
        form.addEventListener("submit", (event) => {
          const action = String(form.getAttribute("data-member-confirm") || "").trim().toLowerCase();
          const guild = String(form.getAttribute("data-confirm-guild") || "this guild");
          const memberSelect = form.querySelector("select[name='member_id']");
          const selectedOption = memberSelect && "selectedOptions" in memberSelect ? memberSelect.selectedOptions[0] : null;
          const memberLabel = selectedOption ? String(selectedOption.textContent || "").trim() : "the selected member";
          let message = "";
          if (action === "kick") {
            message = `Kick ${memberLabel} from ${guild}? This removes the member immediately.`;
          } else if (action === "ban") {
            const deleteDaysSelect = form.querySelector("select[name='delete_days']");
            const deleteDays = deleteDaysSelect ? String(deleteDaysSelect.value || "0").trim() : "0";
            message = `Ban ${memberLabel} from ${guild}? This removes the member immediately and deletes ${deleteDays} day(s) of message history.`;
          }
          if (message && !window.confirm(message)) {
            event.preventDefault();
          }
        });
      });
    })();
  </script>
</body>
</html>
"""
