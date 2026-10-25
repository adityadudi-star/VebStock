# VebStock frontend

Next.js (App Router) + TypeScript + Tailwind CSS + Recharts. Client-side data fetching against the VebStock FastAPI backend.

Navigation is a hamburger drawer (top-left); there is no navigation bar. Views (10): Overview, Inventory, Forecast, Distribution Plan, Trade-off, Scenario Simulator, Baseline Comparison, Alerts & Dispatch, Override Log, Data & Assumptions. The assistant is not a view: it is a button at the top-right of every page that opens a slide-over panel, and its conversation persists while you navigate.

## Assistant widget

The slide-over panel hosts [`react-chatbotify`](https://github.com/tjtanjin/react-chatbotify) (MIT, pinned to 2.5.0) wired to `POST /assistant`. The backend assistant is an open-source RapidFuzz intent matcher (spelling tolerant, entity extraction, curated glossary and how-to answers, database lookups). It is **not an LLM**, and the panel shows the backend's `label` text to say so. Each answer shows the detected topic and confidence ("Understood as: stock lookup (97%)"), sources in a collapsed line, and clickable suggestion chips; questions are limited to 300 characters; failures show an error with Retry.

Why this library: it was the lightest that met every requirement. Measured on npm-installed builds (JS gzip):

| Library | Licence | Unpacked | Main JS (raw / gzip) | Notes |
| --- | --- | --- | --- | --- |
| react-chatbotify 2.5.0 | MIT | 0.5 MB | 180 KB / 61 KB (+ 3 KB CSS) | custom flow handlers, JSX messages (chips, sources), embeddable, every part stylable |
| deep-chat-react 2.5.1 | MIT | 6.9 MB (deep-chat) | 785 KB / 160 KB | web component; heavier, harder to skin flat |
| @chatscope/chat-ui-kit-react 2.1.1 | MIT | 0.7 MB + Font Awesome (37 MB installed) | per-component modules + 43 KB CSS | UI kit only: no flow or connect layer, extra dependencies |

In this app the lazily loaded widget chunk is about 350 KB raw / 118 KB gzip (library, flow code and its CSS), fetched only the first time the panel is opened (`next/dynamic` with `ssr: false`). Initial JS of every page is unchanged apart from a ~0.4 KB gzip loader. The widget stays mounted after the first open, so the conversation survives route changes and closing the panel. Its default look (rounded bubbles, soft effects) is overridden in `components/assistant-widget.css`: square or 2 px corners, 1 px charcoal borders, flat fills.

## Motion and imagery

Motion libraries (exact versions in `package.json`): `motion` (scroll reveals, drawer spring, layout animation), `lenis` (smooth scrolling) and `gsap` with ScrollTrigger (hero parallax and the pinned "how it works" band). `lenis` and `gsap` are loaded with dynamic imports inside effects, so they are client-only and code-split. Everything is disabled under `prefers-reduced-motion`. Photos are hot-linked from Unsplash (`images.unsplash.com`) with a flat sage fallback if they cannot load.

## Local setup

```bash
cd frontend
npm install
cp .env.example .env.local     # then set NEXT_PUBLIC_API_BASE_URL to your running backend
npm run dev                    # http://localhost:3000
```

Scripts: `npm run dev`, `build`, `start`, `lint`, `typecheck`.

## Environment variable

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Base URL of the backend, no trailing slash. It is public (bundled into the browser build), so never put secrets in it. |

When it is unset, development builds fall back to the conventional local default defined in `lib/api.ts`. A production build with it unset shows a configuration-error banner and makes no requests. All requests go through `lib/api.ts`.

## Deploy to Vercel

1. Import the repository in Vercel.
2. Set **Root Directory** to `frontend`. Framework preset: **Next.js** (auto-detected).
3. Add the environment variable `NEXT_PUBLIC_API_BASE_URL` set to the backend's public URL (for example the Render service URL).
4. Deploy. Whenever you change `NEXT_PUBLIC_API_BASE_URL`, **redeploy**: the value is inlined at build time.
5. The backend must allow the Vercel origin via CORS (set the backend `CORS_ORIGINS` to include the Vercel URL, or `CORS_ORIGIN_REGEX` for preview deployments).

Free-tier backends sleep when idle. The first request can take up to a minute; the UI shows a "backend unreachable or waking up" message with a Retry button instead of failing.

## Data honesty

All figures derive from simulated data and are labelled as such. Targets are shown separately, with the met / not met status computed by the backend. Nothing is hardcoded or interpolated in the interface.
