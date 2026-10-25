// The four portal roles. Access lists here only decide what the interface shows and which pages it routes to.
// The backend enforces the same boundaries on every API call (backend/app/api/routes.py, app/auth.py).

export type RoleId = "manufacturer" | "finance" | "warehouse" | "retail";

export interface RoleDef {
  id: RoleId;
  n: string;
  label: string;
  audience: string;
  blurb: string;
  can: string[];
  home: string;
  /** Path prefixes this role may open. */
  paths: string[];
}

export const ROLES: RoleDef[] = [
  {
    id: "manufacturer",
    n: "A",
    label: "Manufacturer",
    audience: "Manufacturing units, production managers and manufacturing partners",
    blurb: "See what the market will need, where finished stock sits and which shipments are on their way.",
    can: ["Demand forecast by product", "Finished stock and expiry risk", "Delivery readiness and delays"],
    home: "/manufacturer",
    paths: ["/manufacturer", "/overview", "/inventory", "/forecast", "/compare", "/data"],
  },
  {
    id: "finance",
    n: "B",
    label: "Business Owner / Finance",
    audience: "Owners, management, accounts and finance teams",
    blurb: "Follow sales, stock value, expiry exposure and plan cost, with every limit in the data stated.",
    can: ["Stock value and sales at list price", "Plan cost and expiry exposure", "Approve plans and download records"],
    home: "/finance",
    paths: ["/finance", "/overview", "/inventory", "/forecast", "/plan", "/tradeoff", "/simulator", "/compare", "/alerts", "/overrides", "/data"],
  },
  {
    id: "warehouse",
    n: "C",
    label: "Warehouse & Dispatch",
    audience: "Warehouse operators, inventory managers, packing teams and dispatch",
    blurb: "Work the stock, the batches closest to expiry and the plans waiting to be picked and dispatched.",
    can: ["Stock by warehouse and batch", "Plans, approval and pick lists", "Low-stock and delay alerts"],
    home: "/warehouse",
    paths: ["/warehouse", "/overview", "/inventory", "/forecast", "/plan", "/simulator", "/alerts", "/overrides", "/data"],
  },
  {
    id: "retail",
    n: "D",
    label: "Retail Stores",
    audience: "Retailers, shop managers and store employees",
    blurb: "Check your own store's stock, see what is arriving and spot products about to run out.",
    can: ["Your store's stock and cover", "Incoming deliveries", "Products likely to run out"],
    home: "/retail",
    paths: ["/retail"],
  },
];

export const roleById = (id: string | null | undefined): RoleDef | undefined => ROLES.find((r) => r.id === id);

/** Pages that anyone may open without a role. */
export const PUBLIC_PATHS = ["/", "/login"];

export function canAccess(role: RoleId | null, pathname: string): boolean {
  if (PUBLIC_PATHS.includes(pathname)) return true;
  if (!role) return false;
  const r = roleById(role);
  return !!r?.paths.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}
