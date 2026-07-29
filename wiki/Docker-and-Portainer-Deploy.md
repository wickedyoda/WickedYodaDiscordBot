# Docker and Portainer Deploy

Last Updated: 2026-07-28

This section explains how to run the bot with Docker or Portainer and how to verify the deployed stack.

## 1. Prepare environment values

Copy the example env file and edit it for your host:

```bash
cp .env.example env.env
```

Minimum required values:

```env
DISCORD_TOKEN=your-bot-token
WEB_ENABLED=true
WEB_BIND_HOST=0.0.0.0
WEB_PORT=8080
WEB_TLS_ENABLED=true
WEB_TLS_PORT=8081
WEB_ADMIN_DEFAULT_USERNAME=admin
WEB_ADMIN_DEFAULT_PASSWORD=change-me
WEB_SESSION_SECRET=random-secret
MANAGED_GUILD_IDS=111111111111111111,222222222222222222
```

Do not commit `env.env` to the repo.

## 2. Start with Docker Compose

```bash
docker compose --env-file env.env up -d
docker compose ps
docker compose logs -f bot
```

The default Compose file binds `${DATA_DIR:-/root/docker/wickedyodabot}` to `/app/data` in the container.

## 3. Common Portainer setup

If you use Portainer instead of CLI Compose:

1. Add a new stack.
2. Set the repository to your fork of this repo.
3. Set the compose path to `docker-compose.yml`.
4. Add env-file contents in Portainer's env editor.
5. Deploy the stack and view container logs from the Portainer UI.

## 4. Verify the bot is healthy

Health endpoint:

```bash
curl http://localhost:8080/health
```

Expected result: `200 OK` only after Discord bot ready state is reached.

Additional checks:

```bash
curl -I https://localhost:8081/health
docker exec <bot-container> python -c "import os; print('ok')"
```

## 5. Update the running stack

```bash
git pull
docker compose --env-file env.env up -d --build
docker compose ps
docker compose logs -f bot
```

## 6. Data and logs

* Persistent container data path: `/app/data`
* Persistent log path: `/logs`
* Host bind examples:
  * Data: `/root/docker/wickedyodabot`
  * Logs: `/root/docker/wickedyodabot/logs`

Ensure the host paths exist and are writable by the container runtime.

## 7. Troubleshooting

* If health stays unhealthy, check Discord token validity and guild IDs.
* If web GUI is unreachable, confirm port bindings and `WEB_BIND_HOST`.
* If logs show import errors, confirm container image is rebuilt after code changes.
* If D&D commands fail with `dnd` import errors, confirm `dnd/` exists in the checked-out code and the container image includes it.
