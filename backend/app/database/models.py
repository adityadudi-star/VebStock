"""SQLAlchemy schema. Created idempotently via `python -m scripts.init_db`."""
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Meta(Base):
    """Key/value store: generator settings, cost assumptions, as-of date, etc."""
    __tablename__ = "meta"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class Warehouse(Base):
    __tablename__ = "warehouses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(32), index=True)


class Distributor(Base):
    __tablename__ = "distributors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(32), index=True)


class Sku(Base):
    __tablename__ = "skus"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(96))
    category: Mapped[str] = mapped_column(String(48), index=True)
    unit_volume: Mapped[float] = mapped_column(Float)          # v_s (litres)
    unit_price: Mapped[float] = mapped_column(Float)
    lost_margin: Mapped[float] = mapped_column(Float)          # pi_s
    writeoff_cost: Mapped[float] = mapped_column(Float)        # eps_s
    shelf_life_days: Mapped[int] = mapped_column(Integer)
    min_shelf_life_days: Mapped[int] = mapped_column(Integer)  # m_s


class Store(Base):
    __tablename__ = "stores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(32), index=True)
    distributor_id: Mapped[int] = mapped_column(ForeignKey("distributors.id"))
    cluster: Mapped[int] = mapped_column(Integer)
    capacity_volume: Mapped[float] = mapped_column(Float)      # Store[j] per planning run


class Lane(Base):
    __tablename__ = "lanes"
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), primary_key=True)
    cost_per_unit: Mapped[float] = mapped_column(Float)        # c_ij
    lead_time_days: Mapped[int] = mapped_column(Integer)       # tau_ij
    capacity_volume: Mapped[float] = mapped_column(Float)      # Cap[i,j] per planning run
    cost_rank: Mapped[int] = mapped_column(Integer)            # 1 = cheapest for that store


class WarehouseSku(Base):
    __tablename__ = "warehouse_sku"
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"), primary_key=True)
    reserved_qty: Mapped[int] = mapped_column(Integer)         # SSW: held back, not shippable


class WarehouseBatch(Base):
    __tablename__ = "warehouse_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"))
    batch_code: Mapped[str] = mapped_column(String(32))
    qty: Mapped[int] = mapped_column(Integer)
    received_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date)
    __table_args__ = (Index("ix_wb_wh_sku", "warehouse_id", "sku_id"),)


class StoreStock(Base):
    __tablename__ = "store_stock"
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"), primary_key=True)
    on_hand: Mapped[int] = mapped_column(Integer)
    reserved: Mapped[int] = mapped_column(Integer)
    incoming: Mapped[int] = mapped_column(Integer)
    nearest_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    qty_near_expiry: Mapped[int] = mapped_column(Integer, default=0)
    avg_daily_demand: Mapped[float] = mapped_column(Float, default=0.0)


class StoreBatch(Base):
    __tablename__ = "store_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"))
    qty: Mapped[int] = mapped_column(Integer)
    expiry_date: Mapped[date] = mapped_column(Date)
    __table_args__ = (Index("ix_sb_store_sku", "store_id", "sku_id"),)


class IncomingShipment(Base):
    __tablename__ = "incoming_shipments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"))
    qty: Mapped[int] = mapped_column(Integer)
    expiry_date: Mapped[date] = mapped_column(Date)
    eta_date: Mapped[date] = mapped_column(Date)
    delay_days: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="in_transit")


class SalesDaily(Base):
    """Non-zero daily sales only (zeros are implied). day_idx 0 = start_date."""
    __tablename__ = "sales_daily"
    store_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day_idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    qty: Mapped[int] = mapped_column(Integer)


class Promotion(Base):
    __tablename__ = "promotions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku_id: Mapped[int] = mapped_column(Integer, index=True)
    region: Mapped[str] = mapped_column(String(32))
    start_idx: Mapped[int] = mapped_column(Integer)
    end_idx: Mapped[int] = mapped_column(Integer)
    discount: Mapped[float] = mapped_column(Float)
    uplift: Mapped[float] = mapped_column(Float)


class SupplierDelay(Base):
    __tablename__ = "supplier_delays"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(Integer)
    sku_id: Mapped[int] = mapped_column(Integer)
    day_idx: Mapped[int] = mapped_column(Integer)
    delay_days: Mapped[int] = mapped_column(Integer)
    qty: Mapped[int] = mapped_column(Integer)


class ForecastRun(Base):
    __tablename__ = "forecast_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    mode: Mapped[str] = mapped_column(String(24))
    metrics: Mapped[dict] = mapped_column(JSON)
    as_of_idx: Mapped[int] = mapped_column(Integer)


class Forecast(Base):
    __tablename__ = "forecasts"
    run_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    horizon: Mapped[int] = mapped_column(Integer, primary_key=True)
    p10: Mapped[float] = mapped_column(Float)
    p50: Mapped[float] = mapped_column(Float)
    p90: Mapped[float] = mapped_column(Float)
    safety_stock: Mapped[float] = mapped_column(Float)
    __table_args__ = (Index("ix_fc_store_sku", "store_id", "sku_id"),)


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    horizon_days: Mapped[int] = mapped_column(Integer)
    alphas: Mapped[dict] = mapped_column(JSON)
    scenario: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parent_plan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    solver_status: Mapped[str] = mapped_column(String(32))
    solve_seconds: Mapped[float] = mapped_column(Float)
    total_cost: Mapped[float] = mapped_column(Float)
    kpis: Mapped[dict] = mapped_column(JSON)
    validation: Mapped[dict] = mapped_column(JSON)
    notes: Mapped[dict] = mapped_column(JSON)       # relaxation/rounding, timings


class PlanLine(Base):
    __tablename__ = "plan_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, index=True)
    sku_id: Mapped[int] = mapped_column(Integer)
    warehouse_id: Mapped[int] = mapped_column(Integer)
    batch_id: Mapped[int] = mapped_column(Integer)
    store_id: Mapped[int] = mapped_column(Integer)
    qty: Mapped[int] = mapped_column(Integer)
    original_qty: Mapped[int] = mapped_column(Integer)
    transport_cost: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="planned")  # planned|overridden|approved
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class OverrideLog(Base):
    __tablename__ = "override_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, index=True)
    line_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(16))            # override | approve
    actor: Mapped[str] = mapped_column(String(64))
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    original_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text)


class SimulationResult(Base):
    __tablename__ = "simulation_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    base_plan_id: Mapped[int] = mapped_column(Integer)
    new_plan_id: Mapped[int] = mapped_column(Integer)
    scenario: Mapped[dict] = mapped_column(JSON)
    comparison: Mapped[dict] = mapped_column(JSON)


class ComparisonRun(Base):
    __tablename__ = "comparison_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    config: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)



class SeriesParam(Base):
    """One row per stocked store-SKU series: the generator's base demand level and list price."""
    __tablename__ = "series"
    store_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    base_rate: Mapped[float] = mapped_column(Float)
    growth: Mapped[float] = mapped_column(Float)


class AppUser(Base):
    """Login account. Additive table; role is one of manufacturer | finance | warehouse | retail.
    Retail users are bound to exactly one store and can only read that store's data."""
    __tablename__ = "app_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), index=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True)
    active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
