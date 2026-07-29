# Wicked Yoda's Little Helper Wiki

Last Updated: 2026-07-28

This wiki documents the bot's commands, web admin interface, integrations, security, and deployment workflow.

## Pages

* [Command Reference](Command-Reference.md) - slash commands, parameters, and permissions.
* [Feed Integrations](Feed-Integrations.md) - Reddit, WordPress, LinkedIn, and YouTube automation.
* [Multi-Guild and Env Setup](Multi-Guild-and-Env.md) - env vars and multi-guild startup patterns.
* [Web Admin Interface](Web-Admin-Interface.md) - web GUI auth, pages, routes, and operational notes.
* [Security Hardening](Security-Hardening.md) - runtime, auth, storage, and verification controls.

## Quickstart

### 1. Clone and configure

```bash
git clone https://github.com/wickedyoda/WickedYodaDiscordBot.git
cd WickedYodaDiscordBot
cp .env.example env.env
```

Edit `env.env` with your Discord token and desired settings.

### 2. Run with Docker Compose

```bash
docker compose up -d
```

### 3. Verify health

```bash
curl http://localhost:8080/health
```

Expected: `200 OK` when the bot is ready.

### 4. Open the web admin GUI

* HTTP: `http://localhost:8080`
* HTTPS: `https://localhost:8081`

Login with `WEB_ADMIN_DEFAULT_USERNAME` and `WEB_ADMIN_DEFAULT_PASSWORD`.

## Maintenance Rule

* When you change a command in `bot.py`, update `wiki/Command-Reference.md` in the same commit/PR.
* When you change web automation or admin behavior, update the relevant wiki page:
  * Feed automation changes → `wiki/Feed-Integrations.md`
  * GUI/auth changes → `wiki/Web-Admin-Interface.md`
  * New env vars or guild behavior → `wiki/Multi-Guild-and-Env.md`
  * Security-relevant changes → `wiki/Security-Hardening.md`

## Source Of Truth

* Runtime behavior: `bot.py`, `app/*`, `dnd/*`, `core/*`, `webui/*`
* Documentation: this `wiki/` folder
