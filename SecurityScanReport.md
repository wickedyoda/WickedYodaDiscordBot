# Security Scan Report

**Date:** 2026-09-04 18:07 UTC
**Repository:** /root/.hermes/wickedyoda-bot
**Image:** ghcr.io/wickedyoda/wickedyodadiscordbot:latest

---

## Summary

| Scan | Status |
|------|--------|
| Ruff | ✅ PASS |
| Bandit | ✅ PASS (0 issues, 16 nosec suppressed) |
| pip-audit | ✅ PASS (no vulnerabilities found) |
| Gitleaks | ✅ PASS (0 findings) |
| Trivy | ⚠️ 3 CRITICAL / 51 HIGH (unfixed OS-level CVEs) |

---

## Ruff
All checks passed.

---

## Bandit
Total issues: 0
Nosec suppressed: 16 (B608 SQL injection false positives, B110/B105 known patterns)
Scanned: 29,490 lines of code

---

## pip-audit
No known vulnerabilities found.

---

## Gitleaks
Findings: 0

---

## Trivy (ghcr.io/wickedyoda/wickedyodadiscordbot:latest)

**Debian OS-level vulnerabilities:** 173 total
- CRITICAL: 3
- HIGH: 51
- MEDIUM: 55
- LOW: 57

All OS-level CVEs have no upstream Debian fix available (Fixed: N/A).

**Python package vulnerabilities:**
- pip (25.0.1): CVE-2025-8869, CVE-2026-13346, CVE-2026-3219, CVE-2026-6357, CVE-2026-8643

**Key CRITICAL CVEs:**
- CVE-2026-13221: perl-base — incorrect regex processing (heap buffer overflow)
- CVE-2026-42496: perl-Archive-Tar — path traversal
- CVE-2026-8376: perl-base — heap buffer overflow in regex compilation

Dockerfile patched with `pip install --upgrade "pip>=26.1.2"` to close 5 pip CVEs on next rebuild.

---

Last scan: 2026-09-04 18:07 UTC
