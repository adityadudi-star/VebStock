"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, get, post, setAuthToken, setUnauthorizedHandler } from "@/lib/api";
import { canAccess, PUBLIC_PATHS, roleById, type RoleDef, type RoleId } from "@/lib/roles";
import { Loading } from "@/components/Stateful";

export interface User {
  username: string;
  role: string;
  store_id: number | null;
  store_name: string | null;
}
interface LoginOut {
  token: string;
  expires_at: number;
  user: User;
}

/**
 * secure: the backend requires sign-in and checks roles on every call.
 * open: the backend runs with AUTH_REQUIRED=false (local development). Roles are then only a view preference,
 *       nothing is enforced, and the interface says so.
 */
type Status = "loading" | "secure" | "open";

interface Ctx {
  status: Status;
  user: User | null;
  /** Role whose dashboard and menu are shown: the signed-in role, or the chosen demo role in open mode. */
  role: RoleId | null;
  roleDef: RoleDef | undefined;
  login: (username: string, password: string, role: RoleId) => Promise<void>;
  /** True after an explicit sign-out, so the gate returns to the portal instead of the login form. */
  signedOut: boolean;
  logout: () => void;
  chooseDemoRole: (r: RoleId) => void;
}

const KEY = "vebstock.session";
const DEMO = "vebstock.demoRole";
const AuthContext = createContext<Ctx | null>(null);

export function useAuth(): Ctx {
  const c = useContext(AuthContext);
  if (!c) throw new Error("AuthProvider missing");
  return c;
}

function read(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, v: string | null) {
  try {
    if (v === null) window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, v);
  } catch {
    /* storage unavailable: the session then lasts until reload */
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [demo, setDemo] = useState<RoleId | null>(null);
  const [signedOut, setSignedOut] = useState(false);

  const clear = useCallback(() => {
    setAuthToken(null);
    write(KEY, null);
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      clear();
      setStatus((s) => (s === "open" ? s : "secure"));
    });
    return () => setUnauthorizedHandler(null);
  }, [clear]);

  useEffect(() => {
    let live = true;
    const saved = read(KEY);
    let token: string | null = null;
    try {
      token = saved ? (JSON.parse(saved) as { token: string }).token : null;
    } catch {
      token = null;
    }
    setAuthToken(token);
    get<User>("/auth/me")
      .then((u) => {
        if (!live) return;
        if (u.role === "open") {
          setStatus("open");
          setDemo(roleById(read(DEMO))?.id ?? null);
        } else {
          setUser(u);
          setStatus("secure");
        }
      })
      .catch((e: unknown) => {
        if (!live) return;
        if (e instanceof ApiError && e.status === 401) clear();
        // An unreachable backend is reported by the pages and the login form; treat the visitor as signed out.
        setStatus("secure");
      });
    return () => {
      live = false;
    };
  }, [clear]);

  const login = useCallback(async (username: string, password: string, role: RoleId) => {
    const r = await post<LoginOut>("/auth/login", { username, password, role });
    setAuthToken(r.token);
    write(KEY, JSON.stringify({ token: r.token }));
    setUser(r.user);
    setStatus("secure");
    setSignedOut(false);
  }, []);

  const logout = useCallback(() => {
    setSignedOut(true);
    clear();
    setDemo(null);
    write(DEMO, null);
  }, [clear]);

  const chooseDemoRole = useCallback((r: RoleId) => {
    write(DEMO, r);
    setDemo(r);
  }, []);

  const role = (user ? (user.role as RoleId) : demo) ?? null;
  const value = useMemo<Ctx>(
    () => ({ status, user, role, roleDef: roleById(role), signedOut, login, logout, chooseDemoRole }),
    [status, user, role, signedOut, login, logout, chooseDemoRole],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Wraps page content: redirects signed-out visitors to the login form and blocks pages outside the role's access list. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { status, user, role, roleDef, signedOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isPublic = PUBLIC_PATHS.includes(pathname);
  const needsLogin = status === "secure" && !user && !isPublic;

  useEffect(() => {
    if (needsLogin) router.replace(signedOut ? "/" : `/login?next=${encodeURIComponent(pathname)}`);
  }, [needsLogin, signedOut, pathname, router]);

  if (isPublic) return <>{children}</>;
  if (status === "loading" || needsLogin) return <Loading label="Checking your session" />;
  // Open mode keeps every legacy URL reachable; a chosen demo role only filters the menu.
  if (status === "open") return <>{children}</>;
  if (!canAccess(role, pathname)) {
    return (
      <div role="alert" className="border border-ink px-4 py-8">
        <div className="kicker !text-ink">Not available for your role</div>
        <p className="mt-2 max-w-[70ch] text-[14px] leading-relaxed">
          This page is not part of the {roleDef?.label ?? "current"} workspace. If you need it, ask an administrator to give your account the right role.
        </p>
        <Link href={roleDef?.home ?? "/"} className="btn mt-4">
          Back to my dashboard
        </Link>
      </div>
    );
  }
  return <>{children}</>;
}
