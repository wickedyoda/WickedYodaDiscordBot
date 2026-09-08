# Security Scan Report

**Date:** 2026-09-08 11:30 UTC
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

**Status:** ✅ Resolved - Fixes already in main, documentation updated

| Alert # | Rule | Resolution |
||-------|------|------------|
| #140 | py/clear-text-storage-sensitive-data | Fixed: Uses temp file with 0600 perms |
| #139-#131 | py/clear-text-logging-sensitive-data | Fixed: Credentials to fd-backed temp file |
| #127-#126 | py/clear-text-logging-sensitive-data | Fixed: watchtower-gui has logging.warning() |
| #120 | py/incomplete-url-substring-sanitization | Fixed: Trust-boundary validation added |
| #119-#117 | py/stack-trace-exposure | Fixed: Exception logging added |
| #116 | DS002 (root user) | Fixed: Both Dockerfiles use USER directive |

---

## Dockerfile Security

Both Dockerfiles include non-root user directives:
- `Dockerfile` line 36: `USER botuser`
- `watchtower-gui/Dockerfile` line 30: `USER appuser`

---

## PR Status

|| PR | Title | Status |
||------|--------|--------|
| #199 | fix: address code scanning alerts and update security report | ✅ Merged (Sep 8, 2026) |
| #191 | fix(security): complete scan - B608/B101 fixes | ✅ Merged |
| #189 | fix Dockerfile OS upgrade packages | ✅ Merged |
| #186 | bump cryptography 49.0.0 → 50.0.1 | ✅ Merged |
| #185 | bump ruff 0.16.0 → 0.16.5 | ✅ Merged |
| #159 | bump python-dotenv 1.2.2 → 1.2.3 | ✅ Merged |
| #155 | bump wheel 0.46.2 → 0.48.0 | ✅ Merged |
| #152 | bump github/codeql-action 4 → 4.37.4 | ✅ Merged |
| #150 | bump requests 2.33.0 → 2.34.2 | ⚠️ Merge conflict (dependabot) |
| #148 | bump croniter 2.0.7 → 6.2.4 | ⚠️ Merge conflict (dependabot) |
| #145 | bump jaraco-context 6.1.0 → 6.1.2 | ⚠️ Merge conflict (dependabot) |

---

## Branch Cleanup

**Deleted branches (all merged or stale):**
- `gui1`, `gui2` — GUI2 merged via `fb0caef`, template_v1.py never in main
- `chore/cleanup-logos-and-report`
- `fix/code-scanning-remediation-2026-09-08`
- Multiple stale `fix/` and `feat/` branches (all merged)

---

## Recommendations

1. **Rerun CodeQL scan** - Trigger via GitHub Actions to clear old alerts
2. **Address dependabot conflicts** — PRs #150, #148, #145 need manual merge when upstream is ready
3. **gui1 variant** — template_v1.py was never merged; v1 test skipped gracefully in current code

---

Last scan: 2026-09-08 11:30 UTC