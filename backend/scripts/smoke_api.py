"""End-to-end smoke test of the P0/P1 journey through the HTTP API (in-process)."""
import json
import time

from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def show(name, r, keys=None):
    ok = r.status_code < 300
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    t = r.headers.get("X-Process-Time-Ms")
    print(f"{'OK ' if ok else 'ERR'} {name:28s} {r.status_code} {t}ms", "" if ok else json.dumps(body)[:400])
    return body


show("health", c.get("/health"))
meta = show("meta", c.get("/meta"))
show("overview", c.get("/overview"))
inv = show("inventory", c.get("/inventory", params={"level": "store_sku", "page_size": 5}))
print("   summary", {k: v for k, v in inv["summary"].items() if k != "thresholds"}, "ms", inv["elapsed_ms"])
for lvl in ("store", "sku", "region", "distributor", "warehouse", "warehouse_sku"):
    show(f"inventory/{lvl}", c.get("/inventory", params={"level": lvl, "page_size": 3}))
show("inventory/batches", c.get("/inventory/batches", params={"page_size": 3}))
f = show("forecast", c.get("/forecast", params={"page_size": 3}))
it = f["items"][0]
fs = show("forecast single+series", c.get("/forecast", params={"store_id": it["store_id"], "sku_id": it["sku_id"], "include_series": True}))
print("   series pts", len(fs["series"]), "stockout", fs["items"][0]["predicted_stockout_date"])
show("alerts", c.get("/alerts"))
t = time.time()
p = show("POST /plan", c.post("/plan", json={"horizon_days": 14, "alphas": {"Dairy": 0.3}}))
print("   plan", p["id"], p["status"], p["solver_status"], "wall", round(time.time() - t, 2), "valid", p["validation"]["valid"],
      "lines", p["total_lines"], "kpis", {k: p["kpis"][k] for k in ("projected_fill_rate_pct", "transport_cost", "explanation_coverage_pct")})
print("   baseline", p["baseline_kpis"])
pid = p["id"]
ln = p["lines"][0]
show("PATCH validate_only ok", c.patch(f"/plan/{pid}", json={"overrides": [{"line_id": ln["id"], "qty": max(ln["qty"] - 1, 0), "reason": "test lower"}], "validate_only": True}))
bad = show("PATCH too large", c.patch(f"/plan/{pid}", json={"overrides": [{"line_id": ln["id"], "qty": 10**7, "reason": "absurd"}]}))
show("PATCH reasonless", c.patch(f"/plan/{pid}", json={"overrides": [{"line_id": ln["id"], "qty": 1, "reason": ""}]}))
ov = show("PATCH override", c.patch(f"/plan/{pid}", json={"overrides": [{"line_id": ln["id"], "qty": max(ln["qty"] - 1, 0), "reason": "store refused extra unit"}], "actor": "priya"}))
print("   status", ov["status"], "applied", ov["applied"])
show("pick-list before approve", c.get(f"/plans/{pid}/pick-list"))
ap = show("PATCH approve", c.patch(f"/plan/{pid}", json={"approve": True, "actor": "priya"}))
print("   status", ap["status"], "ms", ap["elapsed_ms"])
pl = show("pick-list", c.get(f"/plans/{pid}/pick-list", params={"warehouse_id": 1}))
print("   batches", len(pl["batches"]), "lanes", len(pl["lanes"]), "first exp", pl["batches"][0]["days_to_expiry"] if pl["batches"] else None)
show("overrides", c.get("/overrides"))
show("plans", c.get("/plans"))
sim = show("POST /simulate closure", c.post("/simulate", json={"scenario": {"type": "warehouse_closure", "warehouse_id": 2, "days": 3}, "base_plan_id": pid}))
print("   diff", sim["comparison"]["shipment_diff"], "cost", sim["comparison"]["cost_delta"], "addl shortage", sim["comparison"]["additional_shortage_units"])
for sc in ({"type": "demand_spike", "pct": 40}, {"type": "transport_cost_change", "pct": 25}, {"type": "supplier_delay", "delay_days": 4}):
    s2 = show(f"simulate {sc['type']}", c.post("/simulate", json={"scenario": sc, "base_plan_id": pid}))
    print("   ", s2["comparison"]["cost_delta"], s2["new_plan"]["validation"]["valid"])
show("simulate invalid", c.post("/simulate", json={"scenario": {"type": "warehouse_closure"}}))
cmp_ = show("compare", c.get("/compare", params={"plan_id": pid}))
print("   replay available", cmp_["available"])
a = show("assistant", c.post("/assistant", json={"question": "What is the forecast for SKU1 at store 1 for 7 days?"}))
print("  ", a["answer"][:160])
show("assistant oos", c.post("/assistant", json={"question": "who won the world cup"}))
