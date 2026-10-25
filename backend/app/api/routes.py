"""HTTP routes. Thin: validation here, logic in app.services."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.database.session import get_db
from app.schemas import api as S
from app.services import alerts as alerts_svc
from app.services import assistant as assistant_svc
from app.services import compare as compare_svc
from app.services import forecast as forecast_svc
from app.services import inventory as inv_svc
from app.services import overview as ov_svc
from app.services import plans as plan_svc
from app.services import simulate as sim_svc
from app.services.inputs import asof_date, latest_forecast_run

router = APIRouter()


def _lookup(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except LookupError as e:
        raise HTTPException(503, f"dataset not ready: {e}")
    except plan_svc.PlanError as e:
        raise HTTPException(e.status, detail=dict(message=e.message, **e.extra))


@router.get("/health", response_model=S.Health, tags=["system"])
def health(db: Session = Depends(get_db)):
    ok, as_of, run = True, None, None
    try:
        db.execute(text("select 1"))
        try:
            as_of = asof_date(db).isoformat()
            run = latest_forecast_run(db)
        except Exception:  # empty database: still healthy, just not seeded
            pass
    except Exception:
        ok = False
    return S.Health(status="ok", database=ok, environment=get_settings().environment, as_of=as_of,
                    forecast_run_id=run, version=__version__)


@router.get("/meta", tags=["system"])
def meta(db: Session = Depends(get_db)):
    return _lookup(ov_svc.meta, db)


@router.get("/overview", tags=["dashboard"])
def overview(db: Session = Depends(get_db)):
    return _lookup(ov_svc.overview, db)


@router.get("/inventory", response_model=S.InventoryResponse, tags=["inventory"])
def inventory(level: Literal["store_sku", "store", "sku", "region", "distributor", "warehouse", "warehouse_sku"] = "store_sku",
              product: Optional[str] = Query(None, description="SKU id/code or category"),
              region: Optional[str] = None, date: Optional[date] = Query(None, description="as-of date for expiry maths"),
              search: Optional[str] = None, flag: Optional[Literal["low_stock", "excess", "expiry_risk"]] = None,
              warehouse_id: Optional[int] = Query(None, ge=1), store_id: Optional[int] = Query(None, ge=1),
              page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500), sort: str = "name",
              db: Session = Depends(get_db)):
    return _lookup(inv_svc.get_inventory, db, level=level, product=product, region=region, as_of=date, search=search,
                   flag=flag, warehouse_id=warehouse_id, store_id=store_id, page=page, page_size=page_size, sort=sort)


@router.get("/inventory/batches", response_model=S.BatchResponse, tags=["inventory"])
def inventory_batches(warehouse_id: Optional[int] = Query(None, ge=1), product: Optional[str] = None,
                      date: Optional[date] = None, only_risk: bool = False, page: int = Query(1, ge=1),
                      page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    return _lookup(inv_svc.get_batches, db, warehouse_id=warehouse_id, product=product, as_of=date,
                   only_risk=only_risk, page=page, page_size=page_size)


@router.get("/forecast", response_model=S.ForecastResponse, tags=["forecast"])
def forecast(store_id: Optional[int] = Query(None, ge=1), sku_id: Optional[int] = Query(None, ge=1),
             region: Optional[str] = None, category: Optional[str] = None,
             horizon: Optional[Literal[7, 14, 30]] = None, page: int = Query(1, ge=1),
             page_size: int = Query(50, ge=1, le=500), sort: str = "days_of_cover", include_series: bool = False,
             db: Session = Depends(get_db)):
    return _lookup(forecast_svc.get_forecast, db, store_id=store_id, sku_id=sku_id, region=region, category=category,
                   horizon=horizon, page=page, page_size=page_size, sort=sort, include_series=include_series)


@router.get("/alerts", tags=["alerts"])
def alerts(region: Optional[str] = None, type: Optional[Literal[
    "stockout_prediction", "low_stock", "rising_demand", "near_expiry", "delayed_shipment"]] = None,
           limit: int = Query(60, ge=1, le=500), db: Session = Depends(get_db)):
    return _lookup(alerts_svc.get_alerts, db, region, type, limit)


@router.post("/plan", response_model=S.PlanOut, tags=["plan"])
def create_plan(body: S.PlanRequest, db: Session = Depends(get_db)):
    pid = _lookup(plan_svc.create_plan, db, horizon=body.horizon_days, alphas=body.alphas,
                  default_alpha=body.default_alpha)
    return _lookup(plan_svc.get_plan, db, pid)


@router.patch("/plan/{plan_id}", response_model=S.PlanPatchOut, tags=["plan"])
def patch_plan(plan_id: int, body: S.PlanPatch, db: Session = Depends(get_db)):
    res = _lookup(plan_svc.patch_plan, db, plan_id, body)
    if not res["valid"]:
        raise HTTPException(422, detail=dict(message="override rejected: it would violate plan constraints",
                                             violations=res["violations"]))
    return res


@router.get("/plans", tags=["plan"])
def list_plans(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return _lookup(plan_svc.list_plans, db, limit)


@router.get("/plans/{plan_id}", response_model=S.PlanOut, tags=["plan"])
def get_plan(plan_id: int, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=1000),
             warehouse_id: Optional[int] = Query(None, ge=1), store_id: Optional[int] = Query(None, ge=1),
             q: Optional[str] = None, db: Session = Depends(get_db)):
    return _lookup(plan_svc.get_plan, db, plan_id, page=page, page_size=page_size, warehouse_id=warehouse_id,
                   store_id=store_id, q=q)


@router.get("/plans/{plan_id}/pick-list", response_model=S.PickListResponse, tags=["plan"])
def pick_list(plan_id: int, warehouse_id: Optional[int] = Query(None, ge=1), db: Session = Depends(get_db)):
    return _lookup(plan_svc.pick_list, db, plan_id, warehouse_id)


@router.post("/simulate", response_model=S.SimulateOut, tags=["simulate"])
def simulate(body: S.SimulateRequest, db: Session = Depends(get_db)):
    return _lookup(sim_svc.simulate, db, body)


@router.get("/compare", response_model=S.CompareOut, tags=["compare"])
def compare(plan_id: Optional[int] = Query(None, ge=1), db: Session = Depends(get_db)):
    try:
        return compare_svc.get_compare(db, plan_id)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/overrides", response_model=S.OverrideLogResponse, tags=["plan"])
def overrides(plan_id: Optional[int] = Query(None, ge=1), action: Optional[Literal["override", "approve"]] = None,
              page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    return _lookup(ov_svc.overrides, db, plan_id, action, page, page_size)


@router.post("/assistant", response_model=S.AssistantAnswer, tags=["assistant"])
def assistant(body: S.AssistantRequest, db: Session = Depends(get_db)):
    return _lookup(assistant_svc.answer, db, body.question)
