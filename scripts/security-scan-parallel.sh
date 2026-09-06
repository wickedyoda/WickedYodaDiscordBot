#!/bin/bash
# Parallel security scan — runs all 5 scanners concurrently
set -euo pipefail
cd /root/.hermes/wickedyoda-bot
mkdir -p security-report-$(date -u +%Y%m%dT%H%M%SZ)

echo "Starting parallel security scan..."

# Run scans in parallel
ruff check --output-format=json . > security-report-$(date -u +%Y%m%dT%H%M%SZ)/ruff.json 2>&1 &
bandit -r . -x tests,test,node_modules,venv,.venv,build,dist -f json -o security-report-$(date -u +%Y%m%dT%H%M%SZ)/bandit.json 2>&1 &
pip-audit -r requirements.txt --format=json > security-report-$(date -u +%Y%m%dT%H%M%SZ)/pip-audit.json 2>&1 &
gitleaks detect --source . --no-git --report-format=json > security-report-$(date -u +%Y%m%dT%H%M%SZ)/gitleaks.json 2>&1 &
trivy image --format=json ghcr.io/wickedyoda/wickedyodadiscordbot:latest > security-report-$(date -u +%Y%m%dT%H%M%SZ)/trivy-image.json 2>&1 &

wait

echo "All scans complete. Generating report..."
python3 << 'PYEOF'
import json, os, glob
from datetime import datetime
from collections import Counter

ts = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
report_dir = sorted(glob.glob("security-report-*"))[-1]

# Parse results
ruff_issues = []
if os.path.exists(f"{report_dir}/ruff.json"):
    try:
        with open(f"{report_dir}/ruff.json") as f:
            data = json.load(f)
        ruff_issues = data if isinstance(data, list) else []
    except:
        pass

bandit_issues = []
if os.path.exists(f"{report_dir}/bandit.json"):
    with open(f"{report_dir}/bandit.json") as f:
        data = json.load(f)
    bandit_issues = data.get('results', [])

pip_audit = []
if os.path.exists(f"{report_dir}/pip-audit.json"):
    with open(f"{report_dir}/pip-audit.json") as f:
        try:
            pip_audit = json.load(f)
        except:
            pass

gitleaks = []
if os.path.exists(f"{report_dir}/gitleaks.json"):
    with open(f"{report_dir}/gitleaks.json") as f:
        try:
            gitleaks = json.load(f)
        except:
            pass

trivy = {}
if os.path.exists(f"{report_dir}/trivy-image.json"):
    with open(f"{report_dir}/trivy-image.json") as f:
        try:
            trivy = json.load(f)
        except:
            pass

# Count trivy
sev = Counter()
for res in trivy.get('Results', []):
    for v in res.get('Vulnerabilities', []):
        sev[v.get('Severity', 'UNKNOWN').upper()] += 1

report = f"""# Security Scan Report

**Date:** {ts}
**Repository:** /root/.hermes/wickedyoda-bot
**Image:** ghcr.io/wickedyoda/wickedyodadiscordbot:latest

---

## Summary

| Scan | Status |
|------|--------|
| Ruff | {"✅ PASS" if not ruff_issues else f"❌ FAIL ({len(ruff_issues)} issues)"} |
| Bandit | {"✅ PASS" if not bandit_issues else f"❌ FAIL ({len(bandit_issues)} issues)"} |
| pip-audit | {"✅ PASS" if not pip_audit else f"❌ FAIL ({len(pip_audit)} vulns)"} |
| Gitleaks | {"✅ PASS" if not gitleaks else f"❌ FAIL ({len(gitleaks)} findings)"} |
| Trivy | ⚠️ {sev.get('CRITICAL',0)} CRITICAL / {sev.get('HIGH',0)} HIGH / {sev.get('MEDIUM',0)} MEDIUM / {sev.get('LOW',0)} LOW |

---

## Details

### Ruff
{len(ruff_issues)} issues found.

### Bandit
{len(bandit_issues)} issues found.

### pip-audit
{len(pip_audit)} vulnerabilities found.

### Gitleaks
{len(gitleaks)} secrets found.

### Trivy
- CRITICAL: {sev.get('CRITICAL',0)}
- HIGH: {sev.get('HIGH',0)}
- MEDIUM: {sev.get('MEDIUM',0)}
- LOW: {sev.get('LOW',0)}

Last scan: {ts}
"""

with open('SecurityScanReport.md', 'w') as f:
    f.write(report)
print(f"Report saved: SecurityScanReport.md ({len(report)} bytes)")
PYEOF

echo "Scan complete."
