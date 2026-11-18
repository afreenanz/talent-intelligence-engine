# Frontend

React 19 + TypeScript + Vite, Tailwind 4, shadcn/ui, TanStack Query, React Router. Design notes and decisions: [ADR-013](../docs/engineering-decisions.md).

## Run

```bash
# backend on :8080 first (see the root README)
npm install
npm run dev        # http://127.0.0.1:5180  (/api is proxied to :8080)
```

Port 5180 is fixed with `strictPort`, so the dev server fails loudly instead of silently moving to another port.

## Checks

```bash
npm run typecheck && npm run lint && npm test && npm run build
```

CI runs the same four commands.

## Layout

| Path | What lives there |
|---|---|
| `src/lib/api.ts` | Typed fetch client: error envelope → `ApiError`, token handling, single-flight refresh |
| `src/lib/terrain.ts` | Terrain constants + height function shared by the shader and pointer picking |
| `src/lib/theme.ts` | Dark/light theme store |
| `src/features/auth/` | Auth context, provider, route guards |
| `src/components/brand/` | Mark, WebGL terrain, border beam |
| `src/components/ui/` | shadcn components (generated, then restyled through tokens in `index.css`) |
| `src/pages/` | Landing, sign-in/up, app pages |
| `src/test/` | Test setup and `renderApp` (real route tree in a memory router) |

## Design tokens

Defined once in `src/index.css`. Dark is the default theme: blue-black ink `#07080c`, warm paper text `#eee8dc`, a single amber signal `#ff8a3d` used only for what needs attention (the best match, focus, live values). Type is Schibsted Grotesk on a 1.25 scale from 15 px; all numbers use tabular figures.

## Honesty rules

Pages show real API data only. Unbuilt pages say so. The landing page's "Live index" numbers come from `GET /api/v1/stats`, and the job listings are labelled as synthetic.
