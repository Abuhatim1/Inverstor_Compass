# بوصلة (Bousala) — Investment Research & Portfolio Compass

Beginner-friendly SEC EDGAR investment research app with portfolio tracking, FX valuation, allocation charts, and AI-powered thesis analysis.

## Stable Versions

| Label | Commit ID | Date | What it includes |
|---|---|---|---|
| **Stable rev 0.1** | `4c99e7b10faa47dce53755c2fe94b04769e46c72` | 2026-05-29 | Multi-select allocation filters, PDF export, Developer Mode, warnings moved to bottom of Holdings page |
| **Stable core engine code ver 0.1** | `ee366d6abe715b8ed18c8e1d7e349dff6a50bc35` | 2026-05-30 | SAHMK routing PASS · Valuation consistency PASS · UI valuation consistency PASS · Portfolio accounting N01–N10 PASS · Cash integrity PASS · Closed holdings PASS · Persistence PASS · Report history persistence (FIFO 3-file retention) |
| **MVP Core Engine Stable Baseline ver 0.2** | `36b23e3896c1577f3f6eab48f63766457e2a0b25` | 2026-05-30 | Same engine as ver 0.1 + relabelled stable checkpoint in docs |

To roll back: open Version History (clock icon, left sidebar) → find the checkpoint whose description matches → click **Rollback here**.

## Run & Operate

- `streamlit run edgar_app/app.py --server.address=0.0.0.0 --server.port=5000` — start the app
- Required env: `SESSION_SECRET`

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- API: Express 5
- DB: PostgreSQL + Drizzle ORM
- Validation: Zod (`zod/v4`), `drizzle-zod`
- API codegen: Orval (from OpenAPI spec)
- Build: esbuild (CJS bundle)

## Where things live

_Populate as you build — short repo map plus pointers to the source-of-truth file for DB schema, API contracts, theme files, etc._

## Architecture decisions

_Populate as you build — non-obvious choices a reader couldn't infer from the code (3-5 bullets)._

## Product

_Describe the high-level user-facing capabilities of this app once they exist._

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

_Populate as you build — sharp edges, "always run X before Y" rules._

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
