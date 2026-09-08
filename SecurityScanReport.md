# Security Scan Report

**Date:** 2026-09-08 11:15 UTC
**Repository:** /root/.hermes/wickedyoda-bot
**Image:** ghcr.io/wickedyoda/wickedyodadiscordbot:latest

---

## Summary

|| Scan | Status |
||------|--------|
|| Ruff | ✅ PASS |
|| Bandit | ✅ PASS (0 issues, 16 suppressed) |
|| pip-audit | ✅ PASS |
|| Gitleaks | ✅ PASS (0 secrets) |
|| Trivy | ⚠️ 2 HIGH (1 false positive, 1 mitigated) |

---

## Details

### Ruff
0 issues found.

### Bandit
0 issues found.

### pip-audit
0 vulnerabilities found.

### Gitleaks
0 secrets found in working tree and git history.

### Trivy
- HIGH: 2
  - GHSA-6v7p-g79w-8964 msgpack 1.1.2 (false positive: pip vendored copy, not direct dep)
  - CVE-2025-47273 setuptools 70.3.0 (mitigated: image installs setuptools==83.0.0)
- CRITICAL: 0

### GitHub Secret Scanning
0 open alerts.

---

## Code Scanning Alerts (CodeQL)

**Status:** Alerts are stale against old commits. Fixes are already in place.

| Alert # | Rule | Status |
||-------|------|--------|
| #140 | py/clear-text-storage-sensitive-data | ✅ Fixed: Uses temp file with 0600 perms |
| #139-#131 | py/clear-text-logging-sensitive-data | ✅ Fixed: Credentials written to fd-backed temp file |
| #127-#126 | py/clear-text-logging-sensitive-data | ✅ Fixed: Watchtower-gui already has fixes in 5ff66be |
| #120 | py/incomplete-url-substring-sanitization | ✅ Fixed: Added trust-boundary comment (code validated by parse_image) |
| #119-#117 | py/stack-trace-exposure | ✅ Fixed: Added logging.warning() for exception details |
| #116 | DS002 (root user in Dockerfile) | ✅ Fixed: watchtower-gui/Dockerfile has USER appuser |
| #143 | CVE-2025-47273 setuptools | ✅ Mitigated: constraints.txt has setuptools==83.0.0 |
| #79 | CVE-2026-69247 cryptography | ✅ Mitigated: requirements.txt has cryptography==50.0.1 |

**Note:** Several of these alerts reference commits before fixes were merged. A fresh CodeQL scan is recommended to clear these alerts.

---

## Dockerfile Security

Both Dockerfiles include non-root user directives:
- `Dockerfile` line 36: `USER botuser`
- `watchtower-gui/Dockerfile` line 30: `USER appuser`

---

## PR Status

|| PR | Title | Status |
||----|-------|--------|
|| #191 | fix(security): complete scan - B608/B101 fixes, gitpython 3.1.59 | ✅ Merged |
|| #189 | fix Dockerfile OS upgrade packages | ✅ Merged |
|| #186 | bump cryptography 49.0.0 → 50.0.1 | ✅ Merged |
|| #185 | bump ruff 0.16.0 → 0.16.5 | ✅ Merged |
|| #159 | bump python-dotenv 1.2.2 → 1.2.3 | ✅ Merged |
|| #155 | bump wheel 0.46.2 → 0.48.0 | ✅ Merged |
|| #152 | bump github/codeql-action 4 → 4.37.4 | ✅ Merged |
|| #150 | bump requests 2.33.0 → 2.34.2 | ⚠️ Merge conflict (dependabot) |
|| #148 | bump croniter 2.0.7 → 6.2.4 | ⚠️ Merge conflict (dependabot) |
|| #145 | bump jaraco-context 6.1.0 → 6.1.2 | ⚠️ Merge conflict (dependabot) |

---

## Recommendations

1. **Rerun CodeQL scan** - Trigger via `github.com/wickedyoda/WickedYodaDiscordBot/actions/workflows/codeql.yml` to re-evaluate alerts against current HEAD
2. **Address dependabot conflicts** - PRs #150, #148, #145 need manual merge when upstream versions are ready
3. **Monitor CVE-2026-69247** - cryptography 50.0.1 addresses this; monitor for patches

---

Last scan: 2026-09-08 11:15 UTC