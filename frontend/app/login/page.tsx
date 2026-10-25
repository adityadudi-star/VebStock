"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { Loading } from "@/components/Stateful";
import { TextInput } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { canAccess, roleById, ROLES, type RoleId } from "@/lib/roles";

function LoginForm() {
  const params = useSearchParams();
  const router = useRouter();
  const { status, login } = useAuth();
  const [role, setRole] = useState<RoleId>(roleById(params.get("role"))?.id ?? "manufacturer");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const def = roleById(role)!;

  if (status === "loading") return <Loading label="Checking your session" />;
  if (status === "open") {
    return (
      <div className="border border-ink-40 px-4 py-6 text-[14px]">
        This server runs in open demo mode, so there is nothing to sign in to.{" "}
        <Link href="/" className="underline underline-offset-2">
          Choose a workspace
        </Link>
        .
      </div>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password, role);
      // Only follow a same-site path the role may open; anything else lands on the role's own dashboard.
      const next = params.get("next");
      const ok = next && next.startsWith("/") && !next.startsWith("//") && canAccess(role, next);
      router.replace(ok ? next : def.home);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in. Try again.");
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-[460px]">
      <Link href="/" className="mb-6 inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.08em] hover:underline">
        <ArrowLeft aria-hidden size={14} /> All workspaces
      </Link>
      <header className="mb-6 border-b border-ink pb-4">
        <div className="kicker">Sign in</div>
        <h1 className="serif text-[34px] font-medium leading-[1.05] tracking-[-0.02em]">{def.label}</h1>
        <p className="mt-2 text-[13.5px] leading-relaxed text-ink-60">{def.audience}</p>
      </header>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <div>
          <label htmlFor="role" className="field-label">
            Workspace
          </label>
          <select id="role" className="field w-full" value={role} onChange={(e) => setRole(e.target.value as RoleId)}>
            {ROLES.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
        <TextInput label="Username" value={username} onChange={setUsername} />
        <TextInput label="Password" type="password" value={password} onChange={setPassword} />
        {error ? (
          <div role="alert" className="border border-ink px-3 py-2 text-[13px]">
            {error}
          </div>
        ) : null}
        <button type="submit" className="btn w-full justify-center !bg-ink !text-paper" disabled={busy || !username || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="font-mono text-[10.5px] uppercase leading-relaxed tracking-[0.08em] text-ink-60">
          Your account decides what you can open. Choosing a workspace here does not grant access to it.
        </p>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<Loading label="Loading" />}>
      <LoginForm />
    </Suspense>
  );
}
