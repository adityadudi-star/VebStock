export const GLOSSARY: Record<string, { term: string; plain: string }> = {
  fefo: { term: "FEFO", plain: "First expired, first out: the oldest stock ships first." },
  mape: { term: "MAPE", plain: "Average size of the forecast miss, week by week, as a percentage of what was actually sold. Lower is better." },
  wape: { term: "WAPE", plain: "Total forecast miss across all products as a percentage of total units sold. Lower is better." },
  coverage: { term: "P10–P90 coverage", plain: "How often actual sales landed between the Low and High forecast. About 80% is the ideal." },
  alpha: { term: "Alpha", plain: "A dial from 0 to 1. Closer to 1 the plan avoids running out of stock; closer to 0 it avoids stock that expires." },
  cover: { term: "Days of stock left", plain: "How many days the stock on hand lasts at the average daily sales rate." },
  held: { term: "Held back", plain: "Stock that is reserved and cannot be shipped (a safety reserve in warehouses)." },
  safety: { term: "Safety stock", plain: "Extra units kept to cover demand that comes in higher than expected while a delivery is on its way." },
  fill: { term: "Fill rate", plain: "Share of customer demand that was met from stock." },
  simulated: { term: "Simulated", plain: "Produced from a synthetic dataset, not from a real business." },
};
