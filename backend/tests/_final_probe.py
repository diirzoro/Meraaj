"""Read-only probe for the final report numbers."""
import requests
from conftest import API, client, ADMIN_EMAIL, ADMIN_PASSWORD

t = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).json()["access_token"]
a = client(t)
d = a.get(f"{API}/admin/integrations/diagnose").json()
print("DIAGNOSE undelivered:", d["undelivered"], "meraaj_fixable:", d["meraaj_side_fixable"],
      "rahal_fixable:", d["rahal_side_fixable"])
for g in d["groups"]:
    print("  ", g["cause"], g["owner"], g["count"], list(g["events"].items())[:3])
p = a.get(f"{API}/admin/reconciliation/preview").json()
print("PREVIEW count:", p["count"], "totals:", p["totals"], "exec:", p["execution_enabled"],
      "already_adjusted:", sum(1 for i in p["items"] if i["already_adjusted"]))
b = a.get(f"{API}/admin/backups").json()
print("BACKUPS:", len(b["items"]), "enc:", b["encrypted"], "restore:", b["restore_enabled"],
      "latest:", b["items"][0]["file"], b["items"][0]["size"])
h = a.get(f"{API}/admin/system/health").json()
print("HEALTH:", [(c["service"], c["status"]) for c in h["checks"]])
r = a.get(f"{API}/admin/reports").json()
keys = list(r["reports"].keys()) if isinstance(r.get("reports"), dict) else r
print("REPORTS:", len(keys))
ex = a.get(f"{API}/admin/report-exports") if False else None
print("REPORT_EXPORTS pdf logged:", a.get(f"{API}/admin/audit?limit=1").status_code)
rec = a.get(f"{API}/admin/reconciliation").json()
print("RECON mismatch_count:", rec["mismatch_count"], "returned(list capped):", len(rec["mismatches"]))
