"""Measure the PRD acceptance timings on whatever database DATABASE_URL points to (use the `full` profile).

    python -m scripts.bench_full
Prints measured numbers only; compare them with the PRD budgets yourself (nothing is asserted here).
"""
import statistics
import time

from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def timed(fn, n=5):
    xs = []
    for _ in range(n):
        t = time.time()
        r = fn()
        xs.append(time.time() - t)
        assert r.status_code == 200, r.text[:300]
    return xs


c.get("/inventory", params={"page_size": 50})                      # warm the 60 s frame cache once (cold = first call)
cold = []
from app.services import inventory as inv  # noqa: E402
inv.clear_cache()
t = time.time(); r = c.get("/inventory", params={"page_size": 50}); cold.append(time.time() - t)
print(f"inventory cold  : {cold[0]*1000:8.0f} ms  (budget 1500)  rows total {r.json()['total']}")
x = timed(lambda: c.get("/inventory", params={"page_size": 50}))
print(f"inventory warm  : median {statistics.median(x)*1000:6.0f} ms max {max(x)*1000:6.0f} ms")
x = timed(lambda: c.get("/inventory", params={"page_size": 50, "region": "North", "flag": "low_stock"}))
print(f"inventory filter: median {statistics.median(x)*1000:6.0f} ms")
x = timed(lambda: c.get("/forecast", params={"page_size": 50}))
print(f"forecast list   : median {statistics.median(x)*1000:6.0f} ms max {max(x)*1000:6.0f} ms  (budget 1000)")
x = timed(lambda: c.get("/forecast", params={"store_id": 1, "sku_id": 1, "include_series": True}))
print(f"forecast single : median {statistics.median(x)*1000:6.0f} ms (budget 1000)")
for H, a in ((14, 0.7), (14, 0.3)):
    t = time.time()
    r = c.post("/plan", json={"horizon_days": H, "default_alpha": a})
    wall = time.time() - t
    p = r.json()
    n = p["notes"]
    print(f"POST /plan H={H} alpha={a}: wall {wall:6.2f} s (budget 10) | status {p['solver_status']} | lines {p['total_lines']} "
          f"| valid {p['validation']['valid']} viol {p['validation']['n_violations']} | lp vars {n['lp_variables']} "
          f"groups {n['groups']} by_group {n['solved_by_group']} | timing {n['timing']} | rounding {n['rounded_units']}/{n['lp_units']} "
          f"trimmed {n['capacity_trimmed_units']} fefo_fallback {n['fefo_pool_fallbacks']}")
pid = p["id"]
t = time.time(); r = c.get(f"/plans/{pid}", params={"page_size": 100}); print(f"GET /plans/id   : {1000*(time.time()-t):6.0f} ms")
ln = p["lines"][0]
t = time.time(); r = c.patch(f"/plan/{pid}", json={"overrides": [{"line_id": ln["id"], "qty": max(ln["qty"] - 1, 0), "reason": "bench"}]})
print(f"PATCH override  : {1000*(time.time()-t):6.0f} ms (budget 500) status {r.status_code}")
t = time.time(); r = c.patch(f"/plan/{pid}", json={"approve": True}); print(f"PATCH approve   : {1000*(time.time()-t):6.0f} ms (budget 1000) status {r.status_code}")
t = time.time(); r = c.get(f"/plans/{pid}/pick-list"); print(f"pick-list       : {1000*(time.time()-t):6.0f} ms")
t = time.time(); r = c.post("/simulate", json={"scenario": {"type": "warehouse_closure", "warehouse_id": 2, "days": 3}, "base_plan_id": pid})
print(f"POST /simulate  : {time.time()-t:6.2f} s (budget 10) status {r.status_code}")
