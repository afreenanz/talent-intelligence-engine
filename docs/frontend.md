# Frontend

> Status: **As built (Milestones 8A–8C, hardened in 9).** Code: `frontend/`. Quick start and checks:
> [frontend/README.md](../frontend/README.md). Decision record: ADR-013.

## Stack

| Concern | Choice (exact pinned versions) | Why |
|---|---|---|
| Build | Vite 8.3.5, TypeScript 7.0.2 (strict) | Fast dev server; a client-only SPA needs no server framework |
| UI | React 19.3.1, Tailwind CSS 4.3.4, shadcn/ui on Radix 1.8.1 | shadcn components are copied into the repo, so they can be restyled through tokens |
| Routing | React Router 8.5.1 (data router, lazy routes) | |
| Server state | TanStack Query 5.105.3 | Caching, retries, optimistic updates and polling without hand-written state |
| Toasts, icons, font | sonner 2.0.8, lucide-react, Schibsted Grotesk (self-hosted via fontsource) | No third-party font requests |
| Tests | Vitest 5.1.0, Testing Library 16, MSW 3.0.3 | Real components against a mocked network |
| Lint | oxlint 1.90.0 | |

Dependencies are installed with a release-date cutoff (`npm_config_before`) and `--save-exact`: no version
ranges, so a fresh install reproduces the same tree.

## Structure

```
src/
  main.tsx              QueryClient (no retries on 4xx), AuthProvider, router, toaster
  index.css             design tokens (both themes), type scale, motion, panel + beam styles
  app/                  router.tsx (routes, lazy pages), AppShell.tsx (sidebar, theme, sign-out)
  pages/                Landing, auth/AuthForm, app/{Overview, Search, ForYou, JobDetail, Assistant,
                        Saved, Applications, Resume, Preferences, Evaluation}
  features/
    auth/               AuthProvider, context (useAuth), guards (RequireAuth, GuestOnly)
    jobs/               api.ts (queries, mutations, feedback), components.tsx (JobRow, FitMeter,
                        MatchBreakdown, SaveButton, JobFacts, ReasonLines)
    assistant/          api.ts, Reply.tsx (safe renderer), parts.tsx (steps, confirmation text)
    resume/             api.ts (upload, polling, apply)
    evaluation/         api.ts, batches.ts (latest batch per experiment)
  components/
    brand/              TerrainField (WebGL hero), BorderBeam, Mark
    ui/                 shadcn components
    PageHeader.tsx      page title + Notice (empty / error states)
  lib/                  api.ts (fetch client), types.ts, format.ts, preferences.ts, theme.ts, terrain.ts
  test/                 setup.ts (jsdom shims), renderApp.tsx (real route tree in a memory router)
```

## Routing
`/` (landing), `/login`, `/register`, and `/app/*` behind `RequireAuth`: overview, search, recommendations,
jobs/:id, assistant, saved, applications, resume, preferences, evaluation (admin; the API enforces it too).
App pages are **lazy-loaded**, so a landing-page visitor doesn't download the app. Each lazy route has a
`hydrateFallbackElement` for a first visit straight to its URL.

**State in the URL** where it matters: search query and filters (`?q=…&city=…&min_lpa=…`), and the open
conversation (`?c=<id>`), so back/forward, reloads and shared links reproduce the screen.

## Talking to the API (`src/lib/api.ts`)
- One `api<T>(path, {method, body, form, auth, signal})` function. Errors become `ApiError` with the
  backend envelope's `status`, `code`, `message`, `details` and `requestId`.
- **Tokens:** the 15-minute access token lives **in memory only**; the refresh token is in `localStorage`
  so a reload keeps you signed in (trade-off in ADR-013 and security.md).
- **Single-flight refresh:** when several requests get a 401 at once they share one refresh call. Two
  parallel refreshes would send the same refresh token twice, and the server's reuse detection would
  (correctly) revoke the session.
- In development Vite proxies `/api` to `127.0.0.1:8080`; in Docker nginx serves the app and proxies
  `/api` on the same origin, so there is no CORS anywhere.

## Data layer
TanStack Query keys per resource (`['search', q, filters, useProfile]`, `['recommendations']`, `['job', id]`,
`['saved']`, `['applications']`, `['preferences']`, `['profile']`, `['conversation', id]`, …).
- **Optimistic save/unsave** with rollback on error.
- **Résumé parsing is polled** every 2 s only while an upload is pending or processing; polling stops by itself.
- **Hit context:** when a result list loads, each hit (with its feature contributions) is cached under
  `['hit', jobId]`, so the job page can show "Why it ranks here" without re-ranking. Opened directly by URL,
  it says to open the job from Search or For you instead.
- After an assistant turn, saved jobs, preferences and recommendations are invalidated, since the
  assistant may have changed them.
- Click and "not interested" feedback is fire-and-forget, with the search log id and position, and never blocks the UI.

## Design system
Defined once in `src/index.css` as CSS variables; both themes; Tailwind reads them.
- **Dark (default):** blue-black `#07080c`, warm paper text `#eee8dc`, **one** amber signal `#ff8a3d`
  reserved for what deserves attention (fit-score meters, the top match, focus, live values). Light theme:
  cool paper `#eef0f3`. The theme is applied before first paint by a small inline script, allowed by its
  hash in the CSP.
- **Type:** Schibsted Grotesk on a 1.25 scale from 15 px. Tabular figures only in number columns (this
  face gives commas a digit's width in tabular mode, so headline numbers use proportional figures).
- **Radii carry hierarchy:** controls 8 px, panels 14 px, the beam card 20 px.
- **Motion:** one orchestrated entrance on the landing page; motion elsewhere only answers an action.
  `prefers-reduced-motion` is respected everywhere (the beam freezes, the terrain draws one still frame).

### Signature components
- **TerrainField:** a raw WebGL points field (about 76k points on desktop, half on narrow screens) with
  contours, a scanner line, hover swell and a click ring. The height function exists in GLSL (drawing) and
  TypeScript (pointer picking), both generated from one constants file; `terrain.test.ts` checks they use
  the same constants. It pauses when the tab is hidden and frees its GL resources on unmount without
  losing the context. That was a real bug: `loseContext()` broke remounts under StrictMode.
- **BorderBeam:** one short amber beam travelling around a card at constant speed. Four SVG paths trace the
  card's rounded rectangle with `pathLength="100"` (dash values are percentages of the perimeter) and the
  path is rebuilt by a ResizeObserver. Used once per screen: the live index on the landing page and the
  best match on For you.

## Rendering model output safely
`features/assistant/Reply.tsx` renders the assistant's replies (paragraphs, lists, **bold**, job
references) by building React elements; it never uses `dangerouslySetInnerHTML`. `[job_id: …]` becomes a
"View job" link, and a bare job id becomes the job's title. A test feeds it an `<img onerror>` payload and
checks no element is created.

## Accessibility
Semantic landmarks and headings; every control labelled; visible focus ring (amber, 2 px); errors announced
with `role="alert"`; live regions for search results and assistant progress; decorative visuals
`aria-hidden`; touch targets at least 36 px; tested at 390 px wide (the sidebar becomes a top bar with sign-out).

## Testing
`npm test`: 28 tests in 9 files (Vitest + Testing Library + MSW):
- API client: bearer token, single-flight refresh under concurrency, session expiry, error envelope.
- Flows on the real route tree (`renderApp`): sign-in/up, redirects, rate-limit message; search from the
  URL; For you dismiss feedback; empty-profile guidance; application status moves; résumé review applying
  only reviewed fields (including a regression test for a form silently blocked by `step="0.5"`).
- Units: formatting (LPA, experience, dates, status transitions), terrain math parity, theme store, safe
  reply rendering, evaluation batching.

`src/test/setup.ts` shims what jsdom lacks (`ResizeObserver`, pointer capture, `scrollIntoView`).
Every milestone was also checked in a real browser (Playwright) at 1440 and 390 px, in both themes;
several bugs were found only that way and are listed in PROJECT_STATUS.md.

## Build
`npm run build`: entry bundle about 346 kB (111 kB gzipped) at the end of Milestone 10, with each app page
as its own chunk (4–13 kB). The entry has grown from 250 kB in 8B as shared components moved into it; still
a modest size for a 13-page app, and the next thing to look at if load time ever matters.
