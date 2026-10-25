import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Newsreader } from "next/font/google";
import "./globals.css";
import Drawer from "@/components/Drawer";
import { ConfigBanner } from "@/components/Stateful";
import { AssistantProvider } from "@/components/Assistant";
import Disclosure, { Glossary } from "@/components/Disclosure";
import Ripple from "@/components/Ripple";
import ScrollProgress from "@/components/ScrollProgress";
import SiteHeader from "@/components/SiteHeader";
import SmoothScroll from "@/components/SmoothScroll";

const serif = Newsreader({ subsets: ["latin"], variable: "--font-serif-display", display: "swap" });
const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-sans-ui", display: "swap" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono-data", display: "swap" });

export const metadata: Metadata = {
  title: "VebStock",
  description: "The right stock. The right place. The right time. Distribution intelligence and inventory optimization.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${serif.variable} ${sans.variable} ${mono.variable}`}>
      <body>
        <AssistantProvider>
        <ScrollProgress />
        <SmoothScroll />
        <Ripple />
        <Drawer />
        <SiteHeader />
        <ConfigBanner />
        <main className="mx-auto max-w-[1280px] px-4 pb-24 pt-6 sm:px-8">{children}</main>
        <footer className="mx-auto max-w-[1280px] border-t border-ink-15 px-4 py-6 sm:px-8">
          <Disclosure title="Glossary: plain meanings of a few terms">
            <Glossary />
          </Disclosure>
          <p className="kicker mt-4">VebStock. Every figure in this interface is computed from simulated data.</p>
          <p className="kicker mt-1">
            Photos:{" "}
            <a className="underline decoration-ink-40 underline-offset-2" href="https://unsplash.com" target="_blank" rel="noreferrer">
              Unsplash
            </a>
          </p>
        </footer>
        </AssistantProvider>
      </body>
    </html>
  );
}
