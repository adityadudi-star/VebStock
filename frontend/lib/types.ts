// Types mirroring backend/app/schemas/api.py and the dict responses of /meta, /overview, /alerts, /plans.

export type Json = Record<string, unknown>;

export interface Health {
  status: "ok";
  database: boolean;
  environment: string;
  as_of: string | null;
  forecast_run_id: number | null;
  version: string;
}

// ---------------------------------------------------------------- meta
export interface Warehouse {
  id: number;
  name: string;
  region: string;
}
export interface CategoryAssumption {
  category: string;
  avg_price: number;
  lost_margin_per_unit: number;
  writeoff_per_unit: number;
  shelf_life_days: number;
  min_remaining_shelf_life_days: number;
  skus: number;
}
export interface Meta {
  generator_settings: Record<string, string | number | boolean | null>;
  as_of: { date: string; day_idx: number };
  counts: Record<string, number>;
  festivals: { date: string; name: string }[];
  notes: string[];
  categories: CategoryAssumption[];
  cost_assumptions: Record<string, string>;
  forecast_run_id: number | null;
  comparison: {
    run_id: number;
    created_at: string;
    config: Record<string, string | number | boolean | null>;
  } | null;
  thresholds: Record<string, string | number>;
  warehouses: Warehouse[];
  categories_list: string[];
}

// ---------------------------------------------------------------- inventory
export interface InventoryRow {
  key: string;
  level: string;
  name: string;
  region: string | null;
  warehouse: string | null;
  distributor: string | null;
  store: string | null;
  sku_code: string | null;
  sku_name: string | null;
  category: string | null;
  on_hand: number;
  reserved: number;
  available: number;
  incoming: number;
  avg_daily_demand: number;
  days_of_cover: number | null;
  nearest_expiry: string | null;
  qty_expiry_at_risk: number;
  low_stock: boolean;
  excess_stock: boolean;
  expiry_risk: boolean;
  n_series: number;
  n_low_stock: number;
  n_excess: number;
  n_expiry_risk: number;
}
export interface InventorySummary {
  skus: number;
  warehouses: number;
  stores: number;
  series: number;
  on_hand: number;
  reserved: number;
  available: number;
  incoming: number;
  low_stock_series: number;
  excess_series: number;
  expiry_risk_series: number;
  thresholds: Record<string, string | number>;
}
export type InventoryLevel =
  | "warehouse"
  | "store"
  | "sku"
  | "region"
  | "distributor"
  | "store_sku"
  | "warehouse_sku";
export interface InventoryResponse {
  as_of: string;
  level: string;
  total: number;
  page: number;
  page_size: number;
  summary: InventorySummary;
  rows: InventoryRow[];
  elapsed_ms: number;
}
export interface BatchRow {
  batch_id: number;
  batch_code: string;
  warehouse: string;
  sku_code: string;
  sku_name: string;
  category: string;
  qty: number;
  received_date: string;
  expiry_date: string;
  days_to_expiry: number;
  expiry_risk: boolean;
  qty_at_risk: number;
}
export interface BatchResponse {
  as_of: string;
  total: number;
  page: number;
  page_size: number;
  rows: BatchRow[];
}

// ---------------------------------------------------------------- forecast
export interface HorizonForecast {
  horizon_days: number;
  p10: number;
  p50: number;
  p90: number;
  safety_stock: number;
}
export interface ForecastItem {
  store_id: number;
  store: string;
  region: string;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  category: string;
  horizons: HorizonForecast[];
  available_stock: number;
  avg_daily_demand: number;
  days_of_cover: number | null;
  predicted_stockout_date: string | null;
  stockout_within_days: number | null;
  uncertainty_ratio_7d: number | null;
  safety_stock_explanation: string;
}
export interface WeekPoint {
  week_start: string;
  units: number;
  kind: "history" | "actual_held_out" | "forecast";
  p10?: number | null;
  p50?: number | null;
  p90?: number | null;
}
export interface AccuracyWeek {
  week: number;
  start_idx: number;
  mape: number;
  wape: number;
  actual_units: number;
  forecast_units: number;
  coverage_p10_p90: number;
  n_series_positive: number;
}
export interface ForecastAccuracy {
  run_id: number;
  mode: string;
  mape_mean: number;
  mape_min: number;
  mape_max: number;
  wape: number;
  coverage_p10_p90: number;
  target_mape: number;
  target_met: boolean;
  weeks: AccuracyWeek[];
  note: string;
}
export interface ForecastResponse {
  as_of: string;
  run_id: number;
  total: number;
  page: number;
  page_size: number;
  items: ForecastItem[];
  series: WeekPoint[] | null;
  accuracy: ForecastAccuracy;
  elapsed_ms: number;
}

// ---------------------------------------------------------------- plan
export interface PlanRequest {
  horizon_days?: number;
  alphas?: Record<string, number>;
  default_alpha?: number;
}
export interface PlanLine {
  id: number;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  category: string;
  warehouse_id: number;
  warehouse: string;
  batch_id: number;
  batch_code: string;
  batch_expiry: string;
  days_to_expiry: number;
  store_id: number;
  store: string;
  qty: number;
  original_qty: number;
  transport_cost: number;
  reason: string;
  status: string;
  override_reason: string | null;
}
export interface PlanKpis {
  projected_fill_rate_pct: number;
  unmet_demand_units: number;
  shortage_vs_target_units: number;
  expected_expiring_units: number;
  expected_expiry_value: number;
  transport_cost: number;
  shortage_cost: number;
  expiry_cost: number;
  shipments: number;
  units_shipped: number;
  stores_served: number;
  explanation_coverage_pct: number;
  constraint_violations: number;
  solve_seconds: number;
  basis: string;
}
export interface Violation {
  type?: string;
  rule?: string;
  warehouse_id?: number;
  sku_id?: number;
  message?: string;
  line_id?: number;
  [k: string]: unknown;
}
export interface Plan {
  id: number;
  status: "pending" | "approved" | "overridden";
  created_at: string;
  approved_at: string | null;
  approved_by: string | null;
  as_of: string;
  horizon_days: number;
  alphas: Record<string, number>;
  default_alpha: number;
  scenario: Json | null;
  parent_plan_id: number | null;
  solver_status: string;
  solve_seconds: number;
  total_cost: number;
  cost_breakdown: Record<string, number>;
  kpis: PlanKpis;
  baseline_kpis: {
    basis?: string;
    kpis?: Record<string, { baseline: number; optimized: number }>;
  } | null;
  validation: {
    valid?: boolean;
    n_violations?: number;
    checked?: string[];
    violations?: Violation[];
    violation_counts?: Record<string, number>;
    [k: string]: unknown;
  };
  notes: {
    relaxation?: string;
    timing?: Record<string, number | boolean>;
    [k: string]: unknown;
  };
  total_lines: number;
  page: number;
  page_size: number;
  lines: PlanLine[];
}
export interface PlanSummary {
  id: number;
  status: "pending" | "approved" | "overridden";
  created_at: string;
  horizon_days: number;
  solver_status: string;
  total_cost: number;
  kpis: PlanKpis;
  scenario: Json | null;
  parent_plan_id: number | null;
}
export interface OverrideItem {
  line_id: number;
  qty: number;
  reason: string;
}
export interface PlanPatchBody {
  actor?: string;
  overrides?: OverrideItem[];
  approve?: boolean;
  validate_only?: boolean;
}
export interface PlanPatchOut {
  plan_id: number;
  status: string;
  valid: boolean;
  applied: boolean;
  violations: Violation[];
  updated_lines: PlanLine[];
  kpis: PlanKpis | null;
  total_cost: number | null;
  pick_list_ready: boolean;
  elapsed_ms: number;
}

// ---------------------------------------------------------------- pick list
export interface PickDestination {
  store: string;
  qty: number;
  lead_time_days: number;
}
export interface PickBatch {
  warehouse_id: number;
  warehouse: string;
  batch_id: number;
  batch_code: string;
  sku_code: string;
  sku_name: string;
  expiry_date: string;
  days_to_expiry: number;
  qty: number;
  destinations: PickDestination[];
}
export interface LaneLoad {
  warehouse_id: number;
  warehouse: string;
  store_id: number;
  store: string;
  units: number;
  volume: number;
  capacity: number;
  utilization_pct: number;
}
export interface PickList {
  plan_id: number;
  status: string;
  warehouse_id: number | null;
  ordering: string;
  batches: PickBatch[];
  lanes: LaneLoad[];
}

// ---------------------------------------------------------------- simulate
export type ScenarioType =
  | "demand_spike"
  | "warehouse_closure"
  | "transport_cost_change"
  | "supplier_delay";
export interface Scenario {
  type: ScenarioType;
  pct?: number;
  category?: string;
  warehouse_id?: number;
  days?: number;
  delay_days?: number;
}
export interface SimulateBody {
  scenario: Scenario;
  base_plan_id?: number;
  horizon_days?: number;
  alphas?: Record<string, number>;
  default_alpha?: number;
}
export interface SimulateComparison {
  base_plan_id: number;
  new_plan_id: number;
  shipment_diff: {
    lines_changed: number;
    lines_added: number;
    lines_removed: number;
    store_skus_rerouted: number;
    store_skus_newly_served: number;
    store_skus_no_longer_served: number;
    units_base: number;
    units_new: number;
  };
  additional_shortage_units: number;
  additional_shortage_vs_target_units: number;
  cost_delta: Record<string, number>;
  kpi_deltas: Record<string, number>;
  kpis_base: Record<string, number>;
  kpis_new: Record<string, number>;
  changed_lines: {
    store: string;
    sku_code: string;
    warehouse: string;
    qty_base: number;
    qty_new: number;
    delta: number;
  }[];
  [k: string]: unknown;
}
export interface SimulateOut {
  simulation_id: number;
  scenario: Json;
  base_plan_id: number;
  new_plan: Plan;
  comparison: SimulateComparison;
}

// ---------------------------------------------------------------- compare
export interface Spread {
  mean: number;
  min: number;
  max: number;
  values: number[];
}
export interface CompareKpi {
  baseline: Spread;
  optimized: Spread;
  abs_diff: number;
  rel_diff_pct: number | null;
  target_status: { target: string; met: boolean };
}
export interface PerSeed {
  seed: number;
  weekly_mape: number;
  wape: number;
  baseline: Record<string, number | null | string[]>;
  optimized: Record<string, number | null | string[]>;
}
export interface Compare {
  available: boolean;
  message: string | null;
  replay: {
    kpis: Record<string, CompareKpi>;
    extra: Record<string, Record<string, (number | null)[]>>;
    per_seed: PerSeed[];
    seeds: number[];
    config: Record<string, string | number | boolean | null>;
    window_days: number;
    as_of: string;
    data_profile: string;
    label: string;
    wall_clock_seconds: number;
    run_id: number;
    created_at: string;
  } | null;
  plan_projection: Json | null;
  targets: Record<string, string>;
  labels: Record<string, string>;
}

// ---------------------------------------------------------------- overrides
export interface OverrideLogRow {
  id: number;
  plan_id: number;
  line_id: number | null;
  action: string;
  actor: string;
  ts: string;
  original_qty: number | null;
  new_qty: number | null;
  reason: string;
  sku_code: string | null;
  store: string | null;
  warehouse: string | null;
}
export interface OverrideLogResponse {
  total: number;
  page: number;
  page_size: number;
  rows: OverrideLogRow[];
}

// ---------------------------------------------------------------- assistant
export interface AssistantSource {
  tool: string;
  args: Record<string, unknown>;
  rows: number;
  [k: string]: unknown;
}
export interface AssistantAnswer {
  mode: "intent_matching";
  label: string;
  answer: string;
  in_scope: boolean;
  intent: string | null;
  confidence: number; // 0..1
  sources: AssistantSource[];
  suggestions: string[];
}

// ---------------------------------------------------------------- overview
export interface ReplayKpi {
  baseline: number;
  optimized: number;
  rel_diff_pct: number | null;
}
export interface Overview {
  as_of: string;
  inventory: InventorySummary;
  alert_counts: Record<string, number>;
  kpis_replay: Record<string, ReplayKpi> | null;
  kpis_replay_label: string | null;
  forecast_accuracy: ForecastAccuracy | null;
  latest_plan: {
    id: number;
    status: string;
    created_at: string;
    kpis: PlanKpis;
    solver_status: string;
    total_cost: number;
  } | null;
  charts: {
    inventory_by_warehouse: { warehouse: string; on_hand: number; reserved: number; available: number }[];
    inventory_by_category: { category: string; on_hand: number; reserved: number; available: number }[];
    demand_trend: WeekPoint[];
    optimized_vs_baseline: { kpi: string; baseline: number; optimized: number }[] | null;
  };
}

// ---------------------------------------------------------------- alerts
export type AlertType =
  | "stockout_prediction"
  | "low_stock"
  | "rising_demand"
  | "near_expiry"
  | "delayed_shipment";
export interface AlertRow {
  type: AlertType;
  severity: string;
  store: string;
  region: string;
  sku_code: string;
  sku_name: string;
  message: string;
  value: number;
}
export interface AlertsResponse {
  as_of: string;
  counts: Record<string, number>;
  total: number;
  alerts: AlertRow[];
  refreshed_with_forecast_run: number | null;
}

// ---------------------------------------------------------------- role portal
export interface FinanceSummary {
  as_of: string;
  inventory_value: {
    basis: string;
    total: number;
    by_tier: Record<string, { value: number; units: number }>;
    by_category: { category: string; store: number; warehouse: number; in_transit: number }[];
  };
  sales: {
    basis: string;
    days: number;
    total: number;
    units: number;
    by_category: { category: string; value: number; units: number }[];
  };
  expiry_exposure: Record<string, { units: number; writeoff_value: number; list_value: number }>;
  latest_plan: {
    id: number;
    status: string;
    cost_breakdown: { transport: number; shortage: number; expiry: number; total: number };
    units_shipped: number | null;
    projected_fill_rate_pct: number | null;
    expected_expiry_value: number | null;
  } | null;
  limitations: string[];
}

export interface RetailDeliveries {
  store: { id: number; name: string; region: string };
  incoming: {
    sku_code: string;
    sku_name: string;
    qty: number;
    eta_date: string;
    delay_days: number;
    status: string;
  }[];
  approved_plan: { id: number; approved_at: string | null; approved_by: string | null } | null;
  planned_lines: { sku_code: string; sku_name: string; warehouse: string; qty: number; lead_time_days: number | null }[];
}
