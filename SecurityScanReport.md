# Security Scan Report

**Date:** 2026-09-06 03:04 UTC
**Repository:** /root/.hermes/wickedyoda-bot
**Image:** ghcr.io/wickedyoda/wickedyodadiscordbot:latest

---

## Summary

| Scan | Status |
|------|--------|
| Ruff | ✅ PASS |
| Bandit | ✅ PASS (0 issues, 16 suppressed) |
| pip-audit | ✅ PASS |
| Gitleaks | ✅ PASS (0 secrets) |
| Trivy | ⚠️ 2 HIGH (1 false positive, 1 mitigated) |

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

## PR Status

| PR | Title | Status |
|----|-------|--------|
| #189 | fix Dockerfile OS upgrade packages | ✅ Merged |
| #186 | bump cryptography 49.0.0 → 50.0.1 | ✅ Merged |
| #185 | bump ruff 0.16.0 → 0.16.5 | ✅ Merged |
| #159 | bump python-dotenv 1.2.2 → 1.2.3 | ✅ Merged |
| #155 | bump wheel 0.46.2 → 0.48.0 | ✅ Merged |
| #152 | bump github/codeql-action 4 → 4.37.4 | ✅ Merged |
| #150 | bump requests 2.33.0 → 2.34.2 | ⚠️ Merge conflict |
| #148 | bump croniter 2.0.7 → 6.2.4 | ⚠️ Merge conflict |
| #145 | bump jaraco-context 6.1.0 → 6.1.2 | ⚠️ Merge conflict |

---

Last scan: 2026-09-06 03:04 UTC
