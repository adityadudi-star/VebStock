"""Request/response contracts (see docs/API.md). All responses are JSON."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Health(BaseModel):
    status: Literal["ok"]
    database: bool
    environment: str
    as_of: Optional[str] = None
    forecast_run_id: Optional[int] = None
    version: str


# ---------------------------------------------------------------- inventory
class InventoryRow(BaseModel):
    key: str
    level: str
    name: str
    region: Optional[str] = None
    warehouse: Optional[str] = None
    distributor: Optional[str] = None
    store: Optional[str] = None
    sku_code: Optional[str] = None
    sku_name: Optional[str] = None
    category: Optional[str] = None
    on_hand: int
    reserved: int
    available: int
    incoming: int
    avg_daily_demand: float
    days_of_cover: Optional[float] = None
    nearest_expiry: Optional[date] = None
    qty_expiry_at_risk: int
    low_stock: bool
    excess_stock: bool
    expiry_risk: bool
    n_series: int = 1
    n_low_stock: int = 0
    n_excess: int = 0
    n_expiry_risk: int = 0


class InventorySummary(BaseModel):
    skus: int
    warehouses: int
    stores: int
    series: int
    on_hand: int
    reserved: int
    available: int
    incoming: int
    low_stock_series: int
    excess_series: int
    expiry_risk_series: int
    thresholds: dict[str, Any]


class InventoryResponse(BaseModel):
    as_of: date
    level: str
    total: int
    page: int
    page_size: int
    summary: InventorySummary
    rows: list[InventoryRow]
    elapsed_ms: float


class BatchRow(BaseModel):
    batch_id: int
    batch_code: str
    warehouse: str
    sku_code: str
    sku_name: str
    category: str
    qty: int
    received_date: date
    expiry_date: date
    days_to_expiry: int
    expiry_risk: bool
    qty_at_risk: int


class BatchResponse(BaseModel):
    as_of: date
    total: int
    page: int
    page_size: int
    rows: list[BatchRow]


# ---------------------------------------------------------------- forecast
class HorizonForecast(BaseModel):
    horizon_days: int
    p10: float
    p50: float
    p90: float
    safety_stock: float


class ForecastItem(BaseModel):
    store_id: int
    store: str
    region: str
    sku_id: int
    sku_code: str
    sku_name: str
    category: str
    horizons: list[HorizonForecast]
    available_stock: int
    avg_daily_demand: float
    days_of_cover: Optional[float]
    predicted_stockout_date: Optional[date]
    stockout_within_days: Optional[float]
    uncertainty_ratio_7d: Optional[float]
    safety_stock_explanation: str


class WeekPoint(BaseModel):
    week_start: date
    units: float
    kind: Literal["history", "actual_held_out", "forecast"]
    p10: Optional[float] = None
    p50: Optional[float] = None
    p90: Optional[float] = None


class ForecastAccuracy(BaseModel):
    run_id: int
    mode: str
    mape_mean: float
    mape_min: float
    mape_max: float
    wape: float
    coverage_p10_p90: float
    target_mape: float
    target_met: bool
    weeks: list[dict[str, Any]]
    note: str


class ForecastResponse(BaseModel):
    as_of: date
    run_id: int
    total: int
    page: int
    page_size: int
    items: list[ForecastItem]
    series: Optional[list[WeekPoint]] = None
    accuracy: ForecastAccuracy
    elapsed_ms: float


# ---------------------------------------------------------------- plan
class PlanRequest(BaseModel):
    horizon_days: int = Field(14, ge=1, le=60)
    alphas: dict[str, float] = Field(default_factory=dict, description="category -> alpha in [0,1]")
    default_alpha: float = Field(0.7, ge=0, le=1)

    @field_validator("alphas")
    @classmethod
    def _alpha_range(cls, v):
        for k, a in v.items():
            if not 0 <= a <= 1:
                raise ValueError(f"alpha for {k} must be within [0, 1]")
        return v


class PlanLineOut(BaseModel):
    id: int
    sku_id: int
    sku_code: str
    sku_name: str
    category: str
    warehouse_id: int
    warehouse: str
    batch_id: int
    batch_code: str
    batch_expiry: date
    days_to_expiry: int
    store_id: int
    store: str
    qty: int
    original_qty: int
    transport_cost: float
    reason: str
    status: str
    override_reason: Optional[str] = None


class PlanKpis(BaseModel):
    projected_fill_rate_pct: float
    unmet_demand_units: float
    shortage_vs_target_units: float
    expected_expiring_units: float
    expected_expiry_value: float
    transport_cost: float
    shortage_cost: float
    expiry_cost: float
    shipments: int
    units_shipped: int
    stores_served: int
    explanation_coverage_pct: float
    constraint_violations: int
    solve_seconds: float
    basis: str = "static projection over the planning horizon (not the day-by-day replay)"


class PlanOut(BaseModel):
    id: int
    status: Literal["pending", "approved", "overridden"]
    created_at: datetime
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    as_of: date
    horizon_days: int
    alphas: dict[str, float]
    default_alpha: float
    scenario: Optional[dict[str, Any]] = None
    parent_plan_id: Optional[int] = None
    solver_status: str
    solve_seconds: float
    total_cost: float
    cost_breakdown: dict[str, float]
    kpis: PlanKpis
    baseline_kpis: Optional[dict[str, Any]] = None
    validation: dict[str, Any]
    notes: dict[str, Any]
    total_lines: int
    page: int
    page_size: int
    lines: list[PlanLineOut]


class OverrideItem(BaseModel):
    line_id: int
    qty: int = Field(ge=0)
    reason: str = Field(min_length=3, max_length=500)


class PlanPatch(BaseModel):
    actor: str = Field("demo.planner", min_length=1, max_length=64)
    overrides: list[OverrideItem] = Field(default_factory=list)
    approve: bool = False
    validate_only: bool = False

    @model_validator(mode="after")
    def _something(self):
        if not self.overrides and not self.approve:
            raise ValueError("provide at least one override or approve=true")
        return self


class PlanPatchOut(BaseModel):
    plan_id: int
    status: str
    valid: bool
    applied: bool
    violations: list[dict[str, Any]]
    updated_lines: list[PlanLineOut]
    kpis: Optional[PlanKpis] = None
    total_cost: Optional[float] = None
    pick_list_ready: bool = False
    elapsed_ms: float


# ---------------------------------------------------------------- pick list
class PickDestination(BaseModel):
    store: str
    qty: int
    lead_time_days: int


class PickBatch(BaseModel):
    warehouse_id: int
    warehouse: str
    batch_id: int
    batch_code: str
    sku_code: str
    sku_name: str
    expiry_date: date
    days_to_expiry: int
    qty: int
    destinations: list[PickDestination]


class LaneLoad(BaseModel):
    warehouse_id: int
    warehouse: str
    store_id: int
    store: str
    units: int
    volume: float
    capacity: float
    utilization_pct: float


class PickListResponse(BaseModel):
    plan_id: int
    status: str
    warehouse_id: Optional[int] = None
    ordering: str = "earliest expiry first (FEFO)"
    batches: list[PickBatch]
    lanes: list[LaneLoad]


# ---------------------------------------------------------------- simulate
class Scenario(BaseModel):
    type: Literal["demand_spike", "warehouse_closure", "transport_cost_change", "supplier_delay"]
    pct: Optional[float] = Field(None, ge=-90, le=500, description="demand spike / cost change percentage")
    category: Optional[str] = None
    sku_ids: Optional[list[int]] = None
    warehouse_id: Optional[int] = Field(None, ge=1)
    days: Optional[int] = Field(None, ge=1, le=60, description="warehouse closure length")
    delay_days: Optional[int] = Field(None, ge=1, le=60)

    @model_validator(mode="after")
    def _required(self):
        t = self.type
        if t == "demand_spike" and self.pct is None:
            raise ValueError("demand_spike requires pct")
        if t == "warehouse_closure" and (self.warehouse_id is None or self.days is None):
            raise ValueError("warehouse_closure requires warehouse_id and days")
        if t == "transport_cost_change" and self.pct is None:
            raise ValueError("transport_cost_change requires pct")
        if t == "supplier_delay" and self.delay_days is None:
            raise ValueError("supplier_delay requires delay_days")
        return self


class SimulateRequest(BaseModel):
    scenario: Scenario
    base_plan_id: Optional[int] = None
    horizon_days: int = Field(14, ge=1, le=60)
    alphas: dict[str, float] = Field(default_factory=dict)
    default_alpha: float = Field(0.7, ge=0, le=1)


class SimulateOut(BaseModel):
    simulation_id: int
    scenario: dict[str, Any]
    base_plan_id: int
    new_plan: PlanOut
    comparison: dict[str, Any]


# ---------------------------------------------------------------- compare
class CompareOut(BaseModel):
    available: bool
    message: Optional[str] = None
    replay: Optional[dict[str, Any]] = None
    plan_projection: Optional[dict[str, Any]] = None
    targets: dict[str, Any]
    labels: dict[str, str]


# ---------------------------------------------------------------- overrides
class OverrideLogRow(BaseModel):
    id: int
    plan_id: int
    line_id: Optional[int]
    action: str
    actor: str
    ts: datetime
    original_qty: Optional[int]
    new_qty: Optional[int]
    reason: str
    sku_code: Optional[str] = None
    store: Optional[str] = None
    warehouse: Optional[str] = None


class OverrideLogResponse(BaseModel):
    total: int
    page: int
    page_size: int
    rows: list[OverrideLogRow]


# ---------------------------------------------------------------- assistant
class AssistantRequest(BaseModel):
    question: str = Field(min_length=2, max_length=300)


class AssistantAnswer(BaseModel):
    mode: Literal["intent_matching"]
    label: str
    answer: str
    in_scope: bool
    intent: Optional[str] = None
    confidence: float = 0.0
    sources: list[dict[str, Any]]
    suggestions: list[str] = Field(default_factory=list)
