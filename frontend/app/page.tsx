"use client";

import { ArrowRight, Factory, Landmark, Store, Warehouse } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/components/AuthProvider";
import { Banner, Loading } from "@/components/Stateful";
import { Stagger, StaggerItem } from "@/components/Motion";
import { Photo } from "@/components/Photo";
import { ROLES, type RoleId } from "@/lib/roles";

const ICONS: Record<RoleId, typeof Factory> = {
  manufacturer: Factory,
  finance: Landmark,
  warehouse: Warehouse,
  retail: Store,
};

/** Entry point: pick the workspace. Signed-in users go straight to their own dashboard. */
export default function PortalPage() {
  const { status, user, roleDef, chooseDemoRole } = useAuth();
  const router = useRouter();
  const signedIn = !!user;

  useEffect(() => {
    if (user && roleDef) router.replace(roleDef.home);
  }, [user, roleDef, router]);

  if (status === "loading" || signedIn) return <Loading label="Opening your dashboard" />;

  const open = status === "open";
  return (
    <div>
      <header className="relative mb-8 overflow-hidden bg-sage text-paper">
        <div className="absolute inset-0">
          <Photo k="warehouse" w={1600} fill eager />
          <div aria-hidden className="absolute inset-0 bg-ink opacity-40" />
        </div>
        <div className="relative px-6 pb-8 pt-16 sm:px-10 sm:pt-24">
          <div className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-paper-60">
            Distribution intelligence and inventory optimization
          </div>
          <h1 className="serif mt-3 text-[56px] font-medium leading-[0.95] tracking-[-0.03em] sm:text-[96px]">VebStock</h1>
          <p className="serif mt-3 text-[20px] italic leading-snug sm:text-[28px]">The right stock. The right place. The right time.</p>
        </div>
      </header>

      <section aria-labelledby="portal-title" className="mb-10">
        <div className="mb-4 border-t border-ink pt-3">
          <div className="kicker">Choose your workspace</div>
          <h2 id="portal-title" className="h2">
            Who is using VebStock today?
          </h2>
          <p className="mt-2 max-w-[70ch] text-[14px] leading-relaxed">
            Every workspace reads the same live data. Each one shows only what that team needs.
          </p>
        </div>

        {open ? (
          <div className="mb-4">
            <Banner>
              <b className="font-mono text-[11px] uppercase tracking-[0.1em]">Open demo mode.</b> This server is running without sign-in, so the role you pick only changes what is shown. It does not restrict data. Production deployments require sign-in.
            </Banner>
          </div>
        ) : null}

        <Stagger className="grid grid-cols-1 gap-px border border-ink-15 bg-ink-15 sm:grid-cols-2 lg:grid-cols-4 [&>*]:bg-paper">
          {ROLES.map((r) => {
            const Icon = ICONS[r.id];
            const href = open ? r.home : `/login?role=${r.id}`;
            return (
              <StaggerItem key={r.id}>
                <Link
                  href={href}
                  onClick={open ? () => chooseDemoRole(r.id) : undefined}
                  aria-label={`${r.label}: ${open ? "enter dashboard" : "sign in"}`}
                  className="group flex h-full flex-col p-5 transition-colors hover:!bg-ink hover:text-paper focus-visible:!bg-ink focus-visible:text-paper"
                >
                  <div className="flex items-start justify-between">
                    <span className="flex h-12 w-12 items-center justify-center border border-current">
                      <Icon aria-hidden size={24} strokeWidth={1.5} />
                    </span>
                    <span className="num text-[11px] opacity-60">{r.n}</span>
                  </div>
                  <h3 className="serif mt-5 text-[26px] font-medium leading-tight tracking-[-0.01em]">{r.label}</h3>
                  <p className="kicker mt-2 !text-current opacity-60">{r.audience}</p>
                  <p className="mt-3 text-[13.5px] leading-relaxed">{r.blurb}</p>
                  <ul className="mt-3 space-y-1 border-t border-current/20 pt-3 text-[12.5px]">
                    {r.can.map((c) => (
                      <li key={c} className="flex gap-2">
                        <span aria-hidden>·</span>
                        {c}
                      </li>
                    ))}
                  </ul>
                  <span className="mt-auto flex items-center gap-2 pt-5 font-mono text-[11.5px] uppercase tracking-[0.08em]">
                    {open ? "Enter dashboard" : "Sign in to continue"}
                    <ArrowRight aria-hidden size={14} className="transition-transform group-hover:translate-x-1" />
                  </span>
                </Link>
              </StaggerItem>
            );
          })}
        </Stagger>

        <p className="mt-4 font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-60">
          {open ? "All figures come from simulated data." : "Accounts are created by an administrator. Every figure comes from simulated data."}{" "}
          <Link href="/overview" className="underline decoration-ink-40 underline-offset-2">
            Company overview
          </Link>{" "}
          is available to signed-in staff.
        </p>
      </section>
    </div>
  );
}
