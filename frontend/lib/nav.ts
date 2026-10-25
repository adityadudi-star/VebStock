export interface View {
  n: string;
  href: string;
  title: string;
  blurb: string;
}

export const VIEWS: View[] = [
  { n: "01", href: "/overview", title: "Overview", blurb: "Position, alerts and measured KPIs" },
  { n: "02", href: "/inventory", title: "Inventory", blurb: "Stock at every tier, with expiry batches" },
  { n: "03", href: "/forecast", title: "Forecast", blurb: "P10 / P50 / P90 demand and accuracy" },
  { n: "04", href: "/plan", title: "Distribution Plan", blurb: "Generate, override, approve, pick" },
  { n: "05", href: "/tradeoff", title: "Trade-off", blurb: "Stockout cost against expiry cost" },
  { n: "06", href: "/simulator", title: "Scenario Simulator", blurb: "Spikes, closures, delays, costs" },
  { n: "07", href: "/compare", title: "Baseline Comparison", blurb: "Optimized against baseline replay" },
  { n: "08", href: "/alerts", title: "Alerts & Dispatch", blurb: "Exceptions, pick lists, lane load" },
  { n: "09", href: "/overrides", title: "Override Log", blurb: "Every manual change, with reason" },
  { n: "10", href: "/data", title: "Data & Assumptions", blurb: "Generator settings and cost model" },
];
