import hmac
import os
import re

import docker
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

DOCKER_SOCK = os.environ.get("DOCKER_SOCK", "unix:///var/run/docker.sock")
GUI_PASSWORD = os.environ.get("GUI_PASSWORD", "ChangeMeNow123!")
CRON_FILE = "/etc/cron.d/watchtower-auto"


def get_docker_client():
    """Get Docker client with auth."""
    return docker.DockerClient(base_url=DOCKER_SOCK, timeout=30)


def parse_image(image_str):
    """Parse an image string into registry, repo, tag."""
    image_str = image_str.strip()
    # Handle images without explicit registry (e.g., nginx:alpine, mysql:8.0)
    if "/" not in image_str.split(":")[0]:
        parts = image_str.split(":")
        repo = parts[0]
        tag = parts[1] if len(parts) > 1 else "latest"
        registry = "docker.io"
        repo_path = f"library/{repo}"
    else:
        # Has registry or path
        colon_pos = image_str.rfind(":")
        last_slash = image_str.rfind("/")
        if colon_pos > last_slash and colon_pos != -1:
            repo = image_str[:colon_pos]
            tag = image_str[colon_pos + 1 :]
        else:
            repo = image_str
            tag = "latest"
        # Split registry from path
        first_slash = repo.find("/")
        if first_slash > -1 and ("." in repo[:first_slash] or repo[:first_slash] in ("localhost", "ghcr.io", "registry.gitlab.com")):
            registry = repo[:first_slash]
            repo_path = repo[first_slash + 1 :]
        else:
            registry = "docker.io"
            repo_path = repo

    return registry, repo_path, tag


def get_latest_tag(registry, repo, tag):
    """Get the latest available tag from the registry API."""
    # If tag is already a specific version (not 'latest'), check if a newer version exists
    try:
        if registry == "docker.io":
            if repo.startswith("library/"):
                image_name = repo
            else:
                image_name = repo
            url = f"https://hub.docker.com/v2/repositories/{image_name}/tags/?page_size=100&ordering=last_updated"
            import requests

            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                for r in results:
                    rtag = r.get("name", "")
                    if rtag and rtag != tag:
                        # Check if newer version exists
                        if _is_newer_version(tag, rtag):
                            return rtag
            elif resp.status_code == 404:
                # Private or doesn't exist
                return None
    except Exception:
        return None

    # For ghcr.io and other registries, try the registry v2 API
    try:
        if registry == "ghcr.io":
            # ghcr.io requires auth for some images; use anonymous token
            return _check_ghcr(repo, tag)
        elif "index.docker.io" in registry or registry == "docker.io":
            return _check_dockerhub(repo, tag)
        else:
            return _check_generic_registry(registry, repo, tag)
    except Exception:  # nosec B110 — intentional graceful fallback
        return None


def _is_newer_version(current, latest):
    """Compare two version tags to see if latest is newer than current."""
    if current == "latest" and latest != "latest":
        return True
    if latest == "latest":
        return False

    # Simple semver comparison
    def clean(v):
        return re.sub(r"[^0-9.]", "", v)

    try:
        parts_cur = [int(x) for x in clean(current).split(".") if x]
        parts_lat = [int(x) for x in clean(latest).split(".") if x]
        # Pad
        max_len = max(len(parts_cur), len(parts_lat))
        parts_cur += [0] * (max_len - len(parts_cur))
        parts_lat += [0] * (max_len - len(parts_lat))
        for c, lat in zip(parts_cur, parts_lat, strict=True):
            if lat > c:
                return True
            if c > lat:
                return False
    except Exception:  # nosec B110 — intentional graceful fallback, returns None on parse error
        pass
    return False


def _check_ghcr(repo, current_tag):
    """Check ghcr.io for latest tag."""
    import requests

    token_url = "https://ghcr.io/token?scope=repository:" + repo.replace("/", "%2F") + "&service=ghcr.io"
    try:
        resp = requests.get(token_url, timeout=10)
        if resp.status_code == 200:
            token = resp.json().get("token", "")
            headers = {"Authorization": f"Bearer {token}"}
            api_url = f"https://ghcr.io/v2/{repo}/tags/list"
            r = requests.get(api_url, headers=headers, timeout=10)
            if r.status_code == 200:
                tags = r.json().get("tags", [])
                # Remove digest-only tags
                version_tags = [t for t in tags if t and not t.startswith("sha256")]
                for t in sorted(version_tags, reverse=True):
                    if _is_newer_version(current_tag, t):
                        return t
    except Exception:  # nosec B110 — registry API may be unreachable
        pass
    return None


def _check_dockerhub(repo, current_tag):
    """Check Docker Hub for latest tag."""
    import requests

    parts = repo.split("/", 1)
    if len(parts) == 2:
        namespace, image = parts
    else:
        namespace = "library"
        image = parts[0]
    url = f"https://hub.docker.com/v2/repositories/{namespace}/{image}/tags/?page_size=100&ordering=last_updated"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            for r in results:
                t = r.get("name", "")
                if t and _is_newer_version(current_tag, t):
                    return t
    except Exception:  # nosec B110 — Docker Hub API may be unreachable
        pass
    return None


def _check_generic_registry(registry, repo, current_tag):
    """Check a generic registry via v2 API."""
    import requests

    url = f"https://{registry}/v2/{repo}/tags/list"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            tags = resp.json().get("tags", [])
            for t in sorted(tags, reverse=True):
                if t and _is_newer_version(current_tag, t):
                    return t
    except Exception:  # nosec B110 — registry API may be unreachable
        pass
    return None


def get_containers_with_updates():
    """Get all running containers with update availability info."""
    client = get_docker_client()
    containers = client.containers.list(all=True)
    results = []
    for c in containers:
        image_str = c.attrs["Config"]["Image"]
        registry, repo, tag = parse_image(image_str)
        latest_tag = get_latest_tag(registry, repo, tag)

        results.append(
            {
                "id": c.short_id,
                "name": c.name,
                "image": image_str,
                "registry": registry,
                "repo": repo,
                "current_tag": tag,
                "latest_tag": latest_tag or "N/A",
                "update_available": latest_tag is not None,
                "status": c.status,
                "state": c.attrs["State"]["Health"]["Status"] if c.attrs.get("State", {}).get("Health") else c.status,
                "ports": _parse_ports(c.attrs["NetworkSettings"]["Ports"]),
            }
        )
    return results


def _parse_ports(ports):
    """Extract port mappings."""
    result = []
    if not ports:
        return result
    for key, bindings in ports.items():
        if bindings:
            for b in bindings:
                result.append(f"{b['HostIp']}:{b['HostPort']}->{key}")
        else:
            result.append(key)
    return result


def check_password(password):
    """Check if the provided password matches."""
    return hmac.compare_digest(password, GUI_PASSWORD)


def _get_current_schedule():
    """Read the current cron schedule from the cron file or env."""
    try:
        if os.path.exists(CRON_FILE):
            with open(CRON_FILE) as f:
                content = f.read()
            lines = [line for line in content.split("\n") if not line.startswith(("SHELL", "PATH", "")) and line.strip()]
            if lines:
                return lines[0].split("root")[0].strip()
        return os.environ.get("WATCHTOWER_SCHEDULE", "0 */6 * * *")
    except Exception:
        return os.environ.get("WATCHTOWER_SCHEDULE", "0 */6 * * *")


@app.route("/")
def index():
    if "auth" not in session:
        return redirect(url_for("login"))
    try:
        containers = get_containers_with_updates()
        current_schedule = _get_current_schedule()
        return render_template(
            "dashboard.html",
            containers=containers,
            current_schedule=current_schedule,
        )
    except Exception as e:
        return render_template(
            "dashboard.html",
            containers=[],
            error=str(e),
            current_schedule="0 */6 * * *",
        )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if check_password(request.form.get("password", "")):
            session["auth"] = True
            return redirect(url_for("index"))
        flash("Invalid password", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("auth", None)
    return redirect(url_for("login"))


@app.route("/api/containers")
def api_containers():
    if "auth" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        containers = get_containers_with_updates()
        return jsonify({"containers": containers})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/update/<container_id>", methods=["POST"])
def update_container(container_id):
    if "auth" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        client = get_docker_client()
        # Pull latest image
        c = client.containers.get(container_id)
        image_str = c.attrs["Config"]["Image"]
        registry, repo, tag = parse_image(image_str)

        # Determine full image reference for pulling
        if registry == "docker.io":
            if repo.startswith("library/"):
                pull_image = f"{repo}:{tag}"
            else:
                pull_image = f"{repo}:{tag}"
        elif registry == "ghcr.io":
            pull_image = f"ghcr.io/{repo}:{tag}"
        else:
            pull_image = f"{registry}/{repo}:{tag}"

        # Pull the latest image
        client.images.pull(pull_image)
        # Restart the container
        c.restart()

        return jsonify({"status": "success", "message": f"Container {c.name} updated and restarted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/schedule", methods=["POST"])
def set_schedule():
    """Set the cron schedule for auto-updates."""
    if "auth" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    schedule = request.json.get("schedule", "")
    if not schedule:
        return jsonify({"error": "Schedule is required"}), 400

    try:
        # Write cron file
        cron_content = f"""SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

{schedule} root /app/update-containers.sh
"""
        with open(CRON_FILE, "w") as f:
            f.write(cron_content)
        os.chmod(CRON_FILE, 0o644)
        return jsonify({"status": "success", "schedule": schedule})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/schedule")
def get_schedule():
    """Get the current cron schedule."""
    if "auth" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"schedule": _get_current_schedule()})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    # Bind to localhost only — reverse proxy handles external access
    app.run(host="127.0.0.1", port=5000, debug=False)
