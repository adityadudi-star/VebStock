"""Grounded assistant: intent matching (RapidFuzz) + entity extraction over read-only lookups.

Not an LLM. A question is normalised, entities (SKU, store, warehouse, region, category, plan id, horizon) are
extracted, and the best-matching intent is chosen by fuzzy similarity to example phrasings plus keyword evidence.
Every number in an answer comes from a database lookup (listed under `sources`); "how do I / what is" answers come
from a small curated glossary written from the PRD. Anything else is refused with suggested questions.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from rapidfuzz import fuzz, process
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import models as m
from app.services import alerts as al
from app.services import forecast as fs
from app.services import inventory as inv
from app.services.inputs import asof_date, latest_forecast_run

REFUSAL = "I can only answer from this system's data."
LABEL = ("Intent-matching assistant (open-source RapidFuzz, no LLM): it understands questions about stock, forecasts, "
         "risks, plans, comparison results and how VebStock works, and answers only from stored data.")

REGIONS = ["north", "south", "east", "west", "central"]
SYNONYMS = [
    (r"\binventory\b|\bunits? in stock\b|\bon hand\b|\bon-hand\b|\bstock level", "stock"),
    (r"\brun(s|ning)? out\b|\bstock ?outs?\b|\bout of stock\b|\bshortage", "stockout"),
    (r"\bprojection\b|\bpredict(ion|ed)?\b|\bdemand\b|\bexpected sales\b", "forecast"),
    (r"\bexpir(e|es|ed|ing|y)\b|\bgo(es)? bad\b|\bshelf life\b", "expiry"),
    (r"\bshipments?\b|\bdeliver(y|ies)\b", "shipment"),
]

# --- curated glossary / how-to (static text from the PRD and the app's own behaviour; no numbers) -------------------
GLOSSARY = {
    "fefo": "FEFO means first-expired, first-out: the batch that expires earliest ships first. VebStock picks earliest-expiry batches "
            "first and checks that the plan respects it.",
    "alpha": "Alpha (0 to 1) is the trade-off slider. The optimiser minimises transport cost + alpha x lost-margin x unmet demand + "
             "(1 - alpha) x write-off x units expected to expire. Higher alpha = avoid stockouts; lower alpha = avoid expiry waste. "
             "It can be set per category.",
    "safety stock": "Safety stock is the extra buffer per store and SKU. VebStock sets it from forecast uncertainty: the gap between the "
                    "P90 (high) and P50 (expected) demand over the lead time, not a flat percentage.",
    "p10 p50 p90": "P10 / P50 / P90 are the low, expected and high demand forecasts: demand should fall below P10 about 10% of the time, "
                   "below P50 half the time and below P90 about 90% of the time.",
    "mape": "MAPE is the average percentage error of the weekly forecast (store-SKU weeks with sales > 0). WAPE is total absolute error "
            "divided by total actual sales, which is steadier for low-volume items.",
    "wape": "WAPE is total absolute forecast error divided by total actual sales; it is steadier than MAPE for low-volume items.",
    "reserved": "Reserved (shown as 'held back') is stock committed or kept as safety and not available to ship. Available = on hand - reserved.",
    "days of cover": "Days of cover (days of stock left) = available units divided by the average daily demand.",
    "expiry risk": "Expiry risk means units that cannot be sold before they expire at the average daily sales rate, assuming oldest stock sells first.",
    "lead time": "Lead time is the number of days a shipment takes from a warehouse to a store on a lane.",
    "pick list": "A pick list is generated after a plan is approved: batches per warehouse in earliest-expiry order with their destination "
                 "stores, plus each lane's load against its capacity.",
    "baseline": "The baseline is the reorder-point policy distributors use today: reorder when stock falls below average lead-time demand "
                "plus a fixed margin, ship from the nearest warehouse, share stock proportionally when short, pick FIFO.",
    "reorder point": "A reorder point is the stock level that triggers a new order: average demand over the lead time plus a safety margin.",
    "fill rate": "Fill rate = units sold divided by units demanded.",
    "stockout rate": "Stockout rate = store-SKU-days with zero stock at the start of the selling day divided by all store-SKU-days.",
    "optimizer": "The optimiser is a linear program (PuLP with the CBC solver) that chooses what to ship, from which warehouse batch to which "
                 "store, within supply, batch, capacity, safety-stock and shelf-life limits.",
    "simulated": "All data in VebStock is simulated (seeded generator). Replay results are measured on simulated data; PRD targets are goals, not guarantees.",
}
HOWTO = {
    "generate": "Open Distribution Plan and click Generate plan (choose a horizon in days). The optimiser runs, validates every constraint, and shows "
                "each shipment with a one-line reason.",
    "override": "In Distribution Plan, click Edit on a shipment, enter a new quantity and a reason (required), then Validate or Apply. The backend "
                "rejects quantities that break supply, batch, capacity or shelf-life limits.",
    "approve": "In Distribution Plan, click Approve plan. The plan becomes approved and a batch pick list is generated; approved plans cannot be edited.",
    "simulate": "Open Scenario Simulator, pick a scenario (demand spike, warehouse closure, transport cost change or supplier delay), set its "
                "values and run it. You get the new plan and what changed against the base plan.",
    "tradeoff": "Open Trade-off, move the alpha slider for a category and click Re-solve. The panel then shows how fill rate, expiry and cost changed "
                "versus the previous solve.",
}

# (intent, example phrasings, keywords that add evidence)
INTENTS = [
    ("greeting", ["hello", "hi", "hey there", "good morning", "help", "what can you do", "what can i ask"], {"hello", "hi", "hey", "help"}),
    ("about", ["what is vebstock", "what does this app do", "explain vebstock", "how does it work", "tell me about this system"], {"vebstock", "app", "system", "work", "works"}),
    ("snapshot", ["what is the snapshot date", "what date is the data from", "what is today in the simulation", "as of date", "current date"], {"date", "snapshot"}),
    ("counts", ["how many stores", "how many skus", "how many warehouses", "how many products do we have", "give me an overview", "summary of the network", "total stock"], {"many", "total", "overview", "summary", "count"}),
    ("stock", ["how much stock of sku at store", "stock of sku at store", "stock at store", "stock at warehouse", "how much stock do we have", "stock of dairy"], {"stock", "units", "much"}),
    ("forecast", ["forecast for sku at store", "demand forecast for the next 7 days", "how much will sell next week", "what is the forecast", "expected forecast demand"], {"forecast"}),
    ("stockout_risk", ["which stores will run out of stock", "stockout risks", "what is likely to stockout", "which items will stockout soon"], {"stockout"}),
    ("low_stock", ["which items are low on stock", "low stock alerts", "what is running low", "low stock items"], {"low"}),
    ("excess", ["which items have excess stock", "overstocked items", "too much stock"], {"excess", "overstock", "overstocked"}),
    ("expiry", ["which items are about to expire", "expiry risk", "near expiry stock", "what will expire", "expiring batches"], {"expiry", "expire"}),
    ("delayed", ["which shipments are delayed", "delayed deliveries", "late shipments"], {"delayed", "late"}),
    ("plan", ["show me the latest plan", "summary of plan", "how many shipments in the plan", "what is the total cost of the plan", "plan kpis", "plan status"], {"plan"}),
    ("compare", ["how does the optimized plan compare with the baseline", "optimized vs baseline", "did the optimizer beat the baseline", "replay results", "kpi comparison", "is the optimizer better"], {"baseline", "optimized", "optimised", "compare", "comparison", "replay", "beat"}),
    ("accuracy", ["what is the forecast accuracy", "how accurate is the forecast", "what is the mape", "forecast error", "wape"], {"accuracy", "accurate", "mape", "wape", "error"}),
    ("glossary", ["what is fefo", "what does alpha mean", "explain safety stock", "define mape", "what is a pick list", "what does reserved mean", "meaning of days of cover"], {"what", "meaning", "mean", "define", "explain"}),
    ("howto", ["how do i generate a plan", "how do i override a shipment", "how do i approve a plan", "how do i run a scenario", "how to use the trade off slider"], {"how", "generate", "approve", "override", "simulate"}),
]


def _vocab() -> list[str]:
    words: set[str] = set()
    for _i, examples, kws in INTENTS:
        for e in examples:
            words.update(w for w in e.split() if len(w) >= 5)
        words.update(w for w in kws if len(w) >= 5)
    for k in list(GLOSSARY) + list(HOWTO):
        words.update(w for w in k.split() if len(w) >= 5)
    words.update(["forecast", "inventory", "warehouse", "shipment", "expiry", "stockout", "baseline", "optimised", "optimized", "accuracy"])
    return sorted(words)


_VOCAB: list[str] = []


def _norm(q: str) -> str:
    global _VOCAB
    if not _VOCAB:
        _VOCAB = _vocab()
    s = q.lower().replace("’", "'")
    s = re.sub(r"\bwhat'?s\b", "what is", s)
    s = re.sub(r"[^\w\s#\-]", " ", s)
    # spell-correct long non-numeric tokens to the closest word the assistant knows (e.g. forcast -> forecast)
    toks = []
    for t in s.split():
        if len(t) >= 5 and not any(c.isdigit() for c in t) and t not in _VOCAB:
            best = process.extractOne(t, _VOCAB, scorer=fuzz.ratio, score_cutoff=82)
            t = best[0] if best else t
        toks.append(t)
    s = " ".join(toks)
    for pat, rep in SYNONYMS:
        s = re.sub(pat, rep, s)
    return re.sub(r"\s+", " ", s).strip()


def _entities(q: str, db: Session) -> dict:
    ent: dict = {}
    low = q.lower()
    if (m_ := re.search(r"\bsku\s*-?0*(\d+)\b", low)):
        ent["sku_code"] = f"SKU{int(m_.group(1)):04d}"
    if (m_ := re.search(r"\bstore\s*-?#?0*(\d+)\b", low)):
        ent["store_id"] = int(m_.group(1))
    if (m_ := re.search(r"\b(?:wh|warehouse)\s*-?#?0*(\d+)\b", low)):
        ent["warehouse_id"] = int(m_.group(1))
    for r in REGIONS:
        if re.search(rf"\b{r}\b", low):
            ent["region"] = r.title()
    if (m_ := re.search(r"\bplan\s*#?\s*(\d+)\b", low)):
        ent["plan_id"] = int(m_.group(1))
    elif re.search(r"\b(latest|last|current|recent)\b.*\bplan\b|\bplan\b.*\b(latest|last)\b", low):
        ent["plan_id"] = "latest"
    if (m_ := re.search(r"\b(\d+)\s*-?\s*(day|days|week|weeks)\b", low)):
        n = int(m_.group(1)) * (7 if m_.group(2).startswith("week") else 1)
        ent["horizon"] = min((7, 14, 30), key=lambda h: abs(h - n))
    elif "next week" in low:
        ent["horizon"] = 7
    elif "next month" in low:
        ent["horizon"] = 30
    cats = [r[0] for r in db.execute(text("select distinct category from skus")).fetchall()]
    for c in cats:
        if c.lower() in low or (c.lower().endswith("s") and c.lower()[:-1] in low):
            ent["category"] = c
            if (m_ := re.search(rf"{re.escape(c.lower()[:5])}\w*\s+item\s+(\d+)", low)):
                row = db.execute(text("select code from skus where name = :n"), {"n": f"{c} item {int(m_.group(1))}"}).first()
                if row:
                    ent["sku_code"] = row[0]
    return ent


def _score(nq: str, ent: dict) -> list[tuple[str, float]]:
    # remove entity tokens so "store 12" does not drown the verb phrase
    core = re.sub(r"\b(sku|store|wh|warehouse|plan)\s*-?#?\s*\d+\b", " ", nq)
    core = re.sub(r"\b\d+\b", " ", core)
    toks = set(core.split())
    out = []
    for intent, examples, kws in INTENTS:
        if intent == "greeting":
            s = max(fuzz.ratio(core, e) for e in examples) if len(toks) <= 4 else 0.0
        else:
            sim = max(fuzz.token_set_ratio(core, e) for e in examples)
            sim2 = max(fuzz.partial_ratio(core, e) for e in examples if len(e) >= 12) * 0.85
            s = max(sim, sim2)
        hit = len(toks & kws)
        s += 12 * min(hit, 2)
        # without any keyword evidence (or a relevant entity) a fuzzy match alone is not trusted
        if intent not in ("greeting", "glossary", "howto") and hit == 0 and not (ent.get("sku_code") or ent.get("store_id")
                                                                              or ent.get("warehouse_id") or ent.get("plan_id")):
            s = min(s, 55.0)
        if intent == "stock" and ("store_id" in ent or "sku_code" in ent) and "forecast" not in toks:
            s += 8
        if intent == "forecast" and "forecast" in toks and not (toks & {"accuracy", "accurate", "mape", "wape", "error"}):
            s += 15
        if intent == "accuracy" and (toks & {"accuracy", "accurate", "mape", "wape", "error"}):
            s += 25
        if intent == "glossary" and re.search(r"\b(what is|what's|what does|meaning|define|explain|what are)\b", nq) and _glossary_key(nq):
            s = max(s + 30, 90.0)
        if intent == "howto" and re.search(r"\bhow (do|can|to|should)\b", nq):
            s += 25
        if intent == "stockout_risk" and "stockout" in toks:
            s += 15
        if intent == "plan" and ("plan_id" in ent):
            s += 25
        out.append((intent, s))
    return sorted(out, key=lambda x: -x[1])


def _glossary_key(nq: str) -> str | None:
    keys = list(GLOSSARY)
    for k in keys:
        if re.search(rf"\b{re.escape(k)}\b", nq):
            return k
    if re.search(r"\bp10\b|\bp50\b|\bp90\b|quantile", nq):
        return "p10 p50 p90"
    if "first expired" in nq or "first-expired" in nq:
        return "fefo"
    if "cover" in nq:
        return "days of cover"
    if "held back" in nq:
        return "reserved"
    if "optimi" in nq and ("what" in nq or "explain" in nq):
        return "optimizer"
    best = process.extractOne(nq, keys, scorer=fuzz.partial_ratio, score_cutoff=88)
    return best[0] if best else None


SUGGESTIONS = [
    "How much stock of SKU0001 is at Store 001?",
    "What is the forecast for SKU0001 at Store 001 for 14 days?",
    "Which stores will run out of stock in the North region?",
    "How does the optimized plan compare with the baseline?",
    "What is the forecast accuracy?",
    "What is FEFO?",
    "How do I approve a plan?",
    "Show me the latest plan",
]


def _ans(answer, in_scope=True, intent=None, conf=0.0, sources=None, suggestions=None):
    return dict(mode="intent_matching", label=LABEL, answer=answer, in_scope=in_scope, intent=intent,
                confidence=round(conf / 100.0, 2), sources=sources or [], suggestions=suggestions or [])


def _fmt(n) -> str:
    return f"{int(round(n)):,}"


def answer(db: Session, question: str) -> dict:
    nq = _norm(question)
    ent = _entities(question, db)
    ranked = _score(nq, ent)
    intent, conf = ranked[0]
    conf = min(conf, 100.0)
    if conf < 62 or len(nq) < 2:
        alt = [e for i, _s in ranked[:3] for e in (next(x for x in INTENTS if x[0] == i)[1][0],)]
        return _ans(f"{REFUSAL} I could not match that to anything I know. Try one of these:", False, None, conf, [], SUGGESTIONS[:4] + alt[:1])
    # ambiguity: two intents almost tied and the question has no verbs we trust
    if len(ranked) > 1 and ranked[1][1] >= conf - 2 and conf < 75 and ranked[1][0] not in ("greeting",):
        opts = [next(x for x in INTENTS if x[0] == i)[1][0] for i, _ in ranked[:2]]
        return _ans("I want to be sure I understood. Did you mean one of these?", True, None, conf, [], [o.capitalize() + "?" for o in opts])
    fn = HANDLERS[intent]
    res = fn(db, ent, nq)
    res.update(mode="intent_matching", label=LABEL, intent=intent, confidence=round(conf / 100.0, 2))
    res.setdefault("suggestions", [])
    res.setdefault("sources", [])
    return res


# ------------------------------------------------------------------------------------------ handlers
def _h_greeting(db, ent, nq):
    return _ans("Hi! I can look up stock, forecasts and risks, summarise plans, report the baseline-vs-optimised results, and explain terms "
                "like FEFO or alpha. All figures come from the stored simulated data.", True, suggestions=SUGGESTIONS[:5])


def _h_about(db, ent, nq):
    return _ans("VebStock forecasts demand per SKU and store, sets safety stock from forecast uncertainty, allocates warehouse batches "
                "earliest-expiry first with a linear program, explains each shipment, and compares the plan with a reorder-point baseline. "
                "All data is simulated.", True, suggestions=["What is FEFO?", "How do I generate a plan?", "Give me an overview"])


def _h_snapshot(db, ent, nq):
    d = asof_date(db)
    now = datetime.now().astimezone()
    return _ans(f"The simulated data snapshot is {d.strftime('%d %b %Y')} (first day of the 90-day held-out window). The real current "
                f"date and time is {now.strftime('%A, %d %B %Y, %H:%M %Z')}.", True,
                sources=[dict(tool="get_meta", args={}, rows=1)])


def _h_counts(db, ent, nq):
    s = inv.get_inventory(db, level="region", page_size=1, region=ent.get("region"))["summary"]
    t = s["thresholds"]
    return _ans(f"The network has {s['stores']} stores, {s['skus']} SKUs and {s['warehouses']} warehouses ({s['series']:,} store-SKU lines). "
                f"Stores hold {_fmt(s['available'])} units available ({_fmt(s['reserved'])} held back, {_fmt(s['incoming'])} incoming); "
                f"warehouses hold {_fmt(t['warehouse_available'])} available.", True,
                sources=[dict(tool="get_stock", args=dict(region=ent.get("region")), rows=s["series"])],
                suggestions=["Which items are low on stock?", "What is the forecast accuracy?"])


def _h_stock(db, ent, nq):
    args = {k: v for k, v in ent.items() if k in ("sku_code", "store_id", "warehouse_id", "region", "category")}
    if "store_id" in ent and "sku_code" in ent:
        r = inv.get_inventory(db, level="store_sku", product=ent["sku_code"], store_id=ent["store_id"], page_size=1)
        if not r["rows"]:
            return _ans("no data", True, sources=[dict(tool="get_stock", args=args, rows=0)])
        x = r["rows"][0]
        flags = [n for n, f in (("low stock", x["low_stock"]), ("excess", x["excess_stock"]), ("units may expire", x["expiry_risk"])) if f]
        return _ans(f"{x['name']}: {x['on_hand']} on hand, {x['reserved']} held back, {x['incoming']} incoming, {x['available']} available "
                    f"(about {x['days_of_cover']} days of stock left). Flags: {', '.join(flags) or 'none'}. Snapshot {r['as_of']}.", True,
                    sources=[dict(tool="get_stock", args=args, rows=1)],
                    suggestions=[f"What is the forecast for {ent['sku_code']} at Store {ent['store_id']:03d}?"])
    if "warehouse_id" in ent or ("region" in ent and "store" not in nq and "stores" not in nq):
        wid = ent.get("warehouse_id")
        r = inv.get_inventory(db, level="warehouse", warehouse_id=wid, region=ent.get("region"), product=ent.get("category") or ent.get("sku_code"), page_size=5)
        if not r["rows"]:
            return _ans("no data", True, sources=[dict(tool="get_stock", args=args, rows=0)])
        parts = "; ".join(f"{x['name']}: {_fmt(x['on_hand'])} on hand, {_fmt(x['available'])} available, {x['n_expiry_risk']} lines with units that may expire" for x in r["rows"])
        return _ans(parts + ".", True, sources=[dict(tool="get_stock", args=args, rows=len(r["rows"]))])
    level = "store" if "store_id" in ent else "sku" if "sku_code" in ent else "region"
    r = inv.get_inventory(db, level=level, store_id=ent.get("store_id"), product=ent.get("sku_code") or ent.get("category"),
                          region=ent.get("region"), page_size=3)
    s = r["summary"]
    if not r["total"]:
        return _ans("no data", True, sources=[dict(tool="get_stock", args=args, rows=0)])
    what = ent.get("sku_code") or (f"Store {ent['store_id']:03d}" if "store_id" in ent else ent.get("category") or ent.get("region") or "the network")
    return _ans(f"{what}: {_fmt(s['on_hand'])} units on hand across stores ({_fmt(s['available'])} available, {_fmt(s['reserved'])} held back, "
                f"{_fmt(s['incoming'])} incoming). {s['low_stock_series']} lines are running low and {s['expiry_risk_series']} have units that may expire.",
                True, sources=[dict(tool="get_stock", args=args, rows=r["total"])])


def _h_forecast(db, ent, nq):
    if "store_id" in ent and "sku_code" in ent:
        sid = db.execute(text("select id from skus where code = :c"), {"c": ent["sku_code"]}).scalar()
        f = fs.get_forecast(db, store_id=ent["store_id"], sku_id=sid, horizon=ent.get("horizon"), page_size=1) if sid else None
        args = dict(sku=ent["sku_code"], store=ent["store_id"], horizon=ent.get("horizon"))
        if not f or not f["items"]:
            return _ans("no data", True, sources=[dict(tool="get_forecast", args=args, rows=0)])
        it = f["items"][0]
        hs = "; ".join(f"next {h['horizon_days']} days: low {h['p10']:.0f}, expected {h['p50']:.0f}, high {h['p90']:.0f} units" for h in it["horizons"])
        so = it["predicted_stockout_date"]
        return _ans(f"{it['store']} / {it['sku_code']}: {hs}. "
                    + (f"Expected to run out around {so.strftime('%d %b %Y')}." if so else "No stockout expected within 30 days."), True,
                    sources=[dict(tool="get_forecast", args=args, rows=1)])
    run = latest_forecast_run(db)
    rows = db.execute(text("select horizon, sum(p10), sum(p50), sum(p90) from forecasts where run_id = :r group by horizon order by horizon"),
                      {"r": run}).fetchall()
    if not rows:
        return _ans("no data", True)
    h = ent.get("horizon")
    sel = [r for r in rows if h is None or r[0] == h]
    t = "; ".join(f"next {int(r[0])} days: low {_fmt(r[1])}, expected {_fmt(r[2])}, high {_fmt(r[3])} units" for r in sel)
    return _ans(f"Network demand forecast: {t}. Ask about a specific item, e.g. 'forecast for SKU0001 at Store 001'.", True,
                sources=[dict(tool="get_forecast", args=dict(horizon=h), rows=len(sel))])


def _alert(db, ent, kind, noun):
    a = al.get_alerts(db, region=ent.get("region"), alert_type=kind, limit=5)
    cnt = a["counts"].get(kind, 0)
    src = [dict(tool="get_alerts", args=dict(type=kind, region=ent.get("region")), rows=cnt)]
    if not a["alerts"]:
        return _ans("no data", True, sources=src)
    top = "; ".join(f"{x['store']} / {x['sku_code']} ({x['message']})" for x in a["alerts"][:3])
    where = f" in {ent['region']}" if ent.get("region") else ""
    return _ans(f"{cnt} store-SKU lines{where} have {noun}. Most urgent: {top}.", True, sources=src)


def _h_stockout(db, ent, nq):
    return _alert(db, ent, "stockout_prediction", "a predicted stockout within 7 days")


def _h_low(db, ent, nq):
    return _alert(db, ent, "low_stock", "low stock (under 3 days of cover)")


def _h_expiry(db, ent, nq):
    return _alert(db, ent, "near_expiry", "units that may expire before they sell")


def _h_delayed(db, ent, nq):
    return _alert(db, ent, "delayed_shipment", "a delayed shipment")


def _h_excess(db, ent, nq):
    r = inv.get_inventory(db, level="store_sku", flag="excess", region=ent.get("region"), page_size=3, sort="-on_hand")
    src = [dict(tool="get_stock", args=dict(flag="excess", region=ent.get("region")), rows=r["total"])]
    if not r["total"]:
        return _ans("no data", True, sources=src)
    top = "; ".join(f"{x['name']} ({_fmt(x['on_hand'])} units, {x['days_of_cover']} days)" for x in r["rows"])
    return _ans(f"{r['total']} store-SKU lines hold more than 30 days of stock. Largest: {top}.", True, sources=src)


def _plan_row(db, ent):
    pid = ent.get("plan_id")
    if pid in (None, "latest"):
        pid = db.execute(text("select max(id) from plans")).scalar()
    return db.get(m.Plan, int(pid)) if pid else None


def _h_plan(db, ent, nq):
    p = _plan_row(db, ent)
    src = [dict(tool="get_plan", args=dict(plan_id=ent.get("plan_id", "latest")), rows=1 if p else 0)]
    if p is None:
        return _ans("no data: no plan has been generated yet. Open Distribution Plan and click Generate plan.", True, sources=src)
    k = p.kpis
    return _ans(f"Plan {p.id} is {p.status}: {k['shipments']:,} shipments moving {k['units_shipped']:,} units to {k['stores_served']} stores, "
                f"total cost {p.total_cost:,.0f} (transport {k['transport_cost']:,.0f}). Projected fill rate {k['projected_fill_rate_pct']}%, "
                f"{k['constraint_violations']} constraint violations, every shipment explained ({k['explanation_coverage_pct']}%).", True, sources=src,
                suggestions=["How do I approve a plan?", "How does the optimized plan compare with the baseline?"])


def _h_compare(db, ent, nq):
    row = db.execute(text("select result from comparison_runs order by id desc limit 1")).first()
    if not row:
        return _ans("no data: the baseline-vs-optimised replay has not been run yet (python -m scripts.run_compare).", True,
                    sources=[dict(tool="get_kpis", args={}, rows=0)])
    r = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    k = r["kpis"]
    def d(key, unit=""):
        e = k[key]
        return f"{e['baseline']['mean']:.2f}{unit} -> {e['optimized']['mean']:.2f}{unit} ({e['rel_diff_pct']:+.1f}%)"
    txt = (f"On simulated data over {len(r['seeds'])} seeds (baseline -> optimised): stockout rate {d('stockout_rate', '%')}; "
           f"fill rate {d('fill_rate', '%')}; transport cost {d('transport_cost')}; store expiry wastage {d('expiry_wastage_pct', '%')}. "
           f"Warehouse expiry rises ({d('expiry_wastage_warehouse_pct', '%')}) because the shelf-life rule stops short-dated stock shipping. "
           "These are measured replay results, not guarantees.")
    only = next((n for n, key in (("stockout", "stockout_rate"), ("fill", "fill_rate"), ("transport", "transport_cost"), ("expiry", "expiry_wastage_pct")) if n in nq), None)
    if only:
        key = {"stockout": "stockout_rate", "fill": "fill_rate", "transport": "transport_cost", "expiry": "expiry_wastage_pct"}[only]
        txt = f"{key.replace('_', ' ')} (baseline -> optimised, mean of {len(r['seeds'])} simulated seeds): {d(key, '' if key == 'transport_cost' else '%')}."
    return _ans(txt, True, sources=[dict(tool="get_kpis", args={}, rows=len(k))],
                suggestions=["What is the forecast accuracy?", "What is FEFO?"])


def _h_accuracy(db, ent, nq):
    run = latest_forecast_run(db)
    if not run:
        return _ans("no data", True)
    a = fs.accuracy(db, run)
    return _ans(f"Weekly MAPE is {a['mape_mean']:.1f}% (range {a['mape_min']:.1f}-{a['mape_max']:.1f}%) and WAPE {a['wape']:.1f}% over "
                f"{len(a['weeks'])} rolling-origin weeks of the held-out window. The PRD target of under 20% MAPE is "
                f"{'met' if a['target_met'] else 'not met'}.", True, sources=[dict(tool="get_forecast_accuracy", args={}, rows=len(a["weeks"]))])


def _h_glossary(db, ent, nq):
    k = _glossary_key(nq)
    if not k:
        return _ans(f"{REFUSAL} I can explain: " + ", ".join(sorted(GLOSSARY)) + ".", False, suggestions=["What is FEFO?", "What does alpha mean?"])
    return _ans(GLOSSARY[k], True, sources=[dict(tool="glossary", args=dict(term=k), rows=1)])


def _h_howto(db, ent, nq):
    key = next((k for k, pat in (("generate", r"generat|create|run a plan|make a plan"), ("override", r"overrid|edit|change a shipment"),
                                 ("approve", r"approv|pick list"), ("simulate", r"scenario|simulat|what.?if|disruption|closure"),
                                 ("tradeoff", r"alpha|slider|trade.?off")) if re.search(pat, nq)), None)
    if not key:
        return _ans(f"{REFUSAL} I can explain how to: generate a plan, override a shipment, approve a plan, run a scenario, or use the trade-off slider.",
                    False, suggestions=["How do I generate a plan?", "How do I approve a plan?"])
    return _ans(HOWTO[key], True, sources=[dict(tool="howto", args=dict(topic=key), rows=1)])


HANDLERS = {"greeting": _h_greeting, "about": _h_about, "snapshot": _h_snapshot, "counts": _h_counts, "stock": _h_stock,
            "forecast": _h_forecast, "stockout_risk": _h_stockout, "low_stock": _h_low, "excess": _h_excess, "expiry": _h_expiry,
            "delayed": _h_delayed, "plan": _h_plan, "compare": _h_compare, "accuracy": _h_accuracy, "glossary": _h_glossary,
            "howto": _h_howto}
