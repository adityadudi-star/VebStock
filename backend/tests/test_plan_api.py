def _plan(client, **body):
    r = client.post("/plan", json=dict({"horizon_days": 14}, **body))
    assert r.status_code == 200, r.text
    return r.json()


def test_plan_response_schema_and_validity(client):
    p = _plan(client, alphas={"Dairy": 0.2})
    for k in ("id", "status", "solver_status", "solve_seconds", "total_cost", "kpis", "validation", "lines", "notes"):
        assert k in p
    assert p["status"] == "pending"
    assert p["validation"]["valid"] and p["validation"]["n_violations"] == 0
    assert p["kpis"]["explanation_coverage_pct"] == 100.0
    assert p["kpis"]["constraint_violations"] == 0
    assert p["alphas"] == {"Dairy": 0.2}
    assert p["notes"]["timing"]["wall_clock_seconds"] > 0           # actual timing reported
    line = p["lines"][0]
    for k in ("sku_code", "warehouse", "batch_code", "store", "qty", "transport_cost", "reason", "batch_expiry"):
        assert k in line
    assert [l["days_to_expiry"] for l in p["lines"]] == sorted(l["days_to_expiry"] for l in p["lines"])  # FEFO order


def test_plan_request_validation(client):
    assert client.post("/plan", json={"horizon_days": 0}).status_code == 422
    assert client.post("/plan", json={"alphas": {"Dairy": 1.5}}).status_code == 422
    assert client.post("/plan", json={"default_alpha": -0.1}).status_code == 422


def test_override_validation_approval_and_pick_list(client):
    p = _plan(client)
    pid, ln = p["id"], p["lines"][0]
    # reason is required
    assert client.patch(f"/plan/{pid}", json={"overrides": [{"line_id": ln["id"], "qty": 1, "reason": ""}]}).status_code == 422
    # infeasible override is rejected and nothing is stored
    r = client.patch(f"/plan/{pid}", json={"overrides": [{"line_id": ln["id"], "qty": 10 ** 7, "reason": "way too much"}]})
    assert r.status_code == 422
    assert {v["type"] for v in r.json()["detail"]["violations"]} & {"supply", "batch_stock", "lane_capacity"}
    assert client.get(f"/plans/{pid}", params={"page_size": 1000}).json()["lines"][0]["qty"] == ln["qty"]
    # dry-run validation
    ok = client.patch(f"/plan/{pid}", json={"validate_only": True, "overrides": [{"line_id": ln["id"], "qty": 0, "reason": "cancel line"}]})
    assert ok.status_code == 200 and ok.json()["applied"] is False
    # valid override
    new_qty = max(ln["qty"] - 1, 0)
    ov = client.patch(f"/plan/{pid}", json={"actor": "priya", "overrides": [{"line_id": ln["id"], "qty": new_qty, "reason": "store full"}]})
    assert ov.status_code == 200 and ov.json()["status"] == "overridden" and ov.json()["applied"]
    # pick list only after approval
    assert client.get(f"/plans/{pid}/pick-list").status_code == 409
    ap = client.patch(f"/plan/{pid}", json={"approve": True, "actor": "priya"})
    assert ap.status_code == 200 and ap.json()["status"] == "approved" and ap.json()["pick_list_ready"]
    # approved plans are immutable
    assert client.patch(f"/plan/{pid}", json={"approve": True}).status_code == 409
    pl = client.get(f"/plans/{pid}/pick-list").json()
    days = [b["days_to_expiry"] for b in pl["batches"]]
    assert days == sorted(days) and pl["batches"]
    assert all(l["utilization_pct"] <= 100.0 + 1e-6 for l in pl["lanes"])
    wh = pl["batches"][0]["warehouse_id"]
    pl1 = client.get(f"/plans/{pid}/pick-list", params={"warehouse_id": wh}).json()
    assert pl1["batches"] and all(b["warehouse_id"] == wh for b in pl1["batches"])
    # override log persisted with actor, time, reason, quantities
    log = client.get("/overrides", params={"plan_id": pid, "action": "override"}).json()
    assert log["total"] == (1 if new_qty != ln["qty"] else 0)
    row = log["rows"][0]
    assert row["actor"] == "priya" and row["reason"] == "store full" and row["original_qty"] == ln["qty"] and row["new_qty"] == new_qty
    assert row["ts"]
    assert client.get("/overrides", params={"plan_id": pid, "action": "approve"}).json()["total"] > 0


def test_get_plan_filters_and_404(client):
    p = _plan(client)
    wh = p["lines"][0]["warehouse_id"]
    r = client.get(f"/plans/{p['id']}", params={"warehouse_id": wh, "page_size": 1000}).json()
    assert r["lines"] and all(l["warehouse_id"] == wh for l in r["lines"])
    assert client.get("/plans/999999").status_code == 404
    assert client.patch("/plan/999999", json={"approve": True}).status_code == 404


def test_alpha_slider_changes_plan(client):
    low = _plan(client, default_alpha=0.05)
    high = _plan(client, default_alpha=0.95)
    assert high["kpis"]["unmet_demand_units"] <= low["kpis"]["unmet_demand_units"] + 1e-6
    assert high["kpis"]["expected_expiring_units"] >= low["kpis"]["expected_expiring_units"] - 1e-6
