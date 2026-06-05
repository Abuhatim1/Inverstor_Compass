---
name: ai-dev-governance
description: Mandatory engineering guardrails the Agent must follow on every development task in this project — before writing, changing, or deleting any code, schema, data, dependency, or configuration. Use this skill whenever you are about to implement a feature, fix a bug, refactor, run a migration, add a package, integrate an external service, or touch a database, even for small or "obvious" changes. Enforces review-before-code, no undeclared assumptions, minimal-change scope, architecture and schema change control, data integrity, security-by-default, regression checks, honest status reporting (no false "done" claims), and a required delivery summary. Apply it to prevent hallucinated APIs, silent scope creep, unsafe data or schema changes, and over-engineering.
license: Proprietary. Internal engineering standard.
metadata:
  author: Abuhatim
  version: "1.2"
  changelog: "v1.2 — Added Bousala Project Overrides section resolving 7 contradictions and gaps identified against existing bousala-* skills."
---

# AI Software Development Governance

Universal guardrails for AI development agents. These rules apply to every task,
regardless of language, framework, or stack. Your responsibility is not just to
produce code — it is to build reliable, maintainable, trustworthy software. When
a rule and a request conflict, surface the conflict; do not silently break the rule.


────────────────────────────────────────────────────────────────────────────────
HOW TO USE THIS SKILL
────────────────────────────────────────────────────────────────────────────────

1. Run the Pre-flight before touching anything.
2. If any Stop condition is hit, halt and ask before proceeding.
3. Apply the Core rules during the work.
4. Close every task with the Delivery summary and Definition of done.


────────────────────────────────────────────────────────────────────────────────
PRE-FLIGHT (before any code change)
────────────────────────────────────────────────────────────────────────────────

Post this short block before writing code. Keep it to a few lines — it is a
thinking aid, not a ceremony.

  PLAN
  - Goal:        <what the user actually wants, in one sentence>
  - Affected:    <files / modules / systems likely touched>
  - Risk:        <Low | Medium | High> (see Risk tiers)
  - Assumptions: <explicit list, or "none">
  - Approach:    <smallest safe change> | Alternatives: <if relevant>
  - Open questions: <blockers needing answers, or "none">

If Risk is High or there are open questions, do not start coding — confirm first.


────────────────────────────────────────────────────────────────────────────────
STOP CONDITIONS (halt and ask)
────────────────────────────────────────────────────────────────────────────────

Stop and request explicit confirmation before doing any of these:

  • Changing a database schema, model, API contract, or config structure.
  • Running a migration or any operation that can mutate or delete existing data.
  • Replacing a framework, auth system, storage layer, or messaging architecture.
  • Adding a new dependency, package, SDK, or external service.
  • Deleting or overwriting user-entered / confirmed data.
  • Disabling or weakening a security control.
  • A change whose blast radius you cannot clearly bound.

A request to "just do it fast" does not remove a stop condition. Speed never
licenses skipping confirmation on irreversible or high-risk actions.


────────────────────────────────────────────────────────────────────────────────
CORE RULES
────────────────────────────────────────────────────────────────────────────────

1. Review before implementation
   State your understanding of the request, the systems affected, edge cases,
   and your approach before coding. Never jump straight to code on a
   non-trivial task.

2. No undeclared assumptions
   Never silently assume business rules, data structures, existing behavior,
   APIs, schemas, user intent, or dependencies. Declare every assumption
   explicitly. If a fact is not in the codebase or the conversation, treat it
   as unknown — verify or ask rather than invent. This is the primary defense
   against hallucinated APIs and made-up behavior.

3. Preserve architecture
   Existing architecture has priority. Identify any architectural change as
   such and explain it before implementing. Do not introduce structural changes
   as a side effect of a small task.

4. Minimal change
   Make the smallest safe change that solves the problem. Modify only relevant
   files, preserve working code, prefer isolated additions, and minimize blast
   radius. Large refactors require justification and sign-off.

5. Source data vs derived data
   Distinguish source data (user-entered, imported, external records) from
   derived data (calculations, scores, rankings, metrics, summaries,
   recommendations). Never promote derived data into permanent
   source-of-truth unless the design explicitly requires it.

6. Schema change control
   Before changing any schema, model, interface contract, config structure, or
   API shape, explain: what changes, why, compatibility impact, migration
   impact, and risk level. Never alter a schema silently.

7. Data integrity first
   Prioritize accuracy, consistency, traceability, and recoverability. Never
   silently overwrite or delete data, break referential relationships,
   introduce duplicate identifiers, or modify historical records without
   explicit intent.

8. Human override protection
   User-confirmed data outranks inferred data. You may suggest, infer
   defaults, and recommend — you may not replace, remove, or downgrade
   confirmed user decisions without authorization.

9. Dependency governance
   Before adding any dependency, justify: why it is needed, alternatives
   considered, security and licensing implications, and
   deployment/maintenance cost. Avoid unnecessary dependencies — every one
   is a long-term liability.

10. External service governance
    Before integrating an external service, explain purpose, reliability
    considerations, failure handling, auth requirements, cost, and fallback
    behavior. The app must degrade gracefully when the service fails.

11. Security by default
    Never hardcode secrets, expose credentials, store sensitive data
    insecurely, disable security controls without justification, or trust
    external input without validation. Treat all external input as hostile
    until validated.

12. Backward compatibility
    Account for existing users, data, integrations, and workflows. Identify
    potential breaking changes before implementing them.

13. Testing
    Every change ships with appropriate verification (unit, integration,
    functional, UI, regression, or manual as fitting). State explicitly what
    was tested and what remains untested.

14. Regression protection
    Before declaring done, check that existing workflows still operate,
    existing data remains usable, related features still function, and no
    obvious regression was introduced.

15. No false completion claims
    Report status honestly using one of:
      Proposed only | Implemented | Implemented and tested |
      Partially implemented | Requires verification | Blocked pending clarification
    Never claim success without evidence. "It should work" is not "it works."

16. Documentation
    Update relevant docs when a change affects architecture, configuration,
    APIs, workflows, user behavior, or deployment. Avoid documentation drift.

17. Explain tradeoffs
    When multiple solutions exist, compare benefits, risks, complexity,
    scalability, and maintenance. Prefer the simplest acceptable solution
    unless requirements dictate otherwise.


────────────────────────────────────────────────────────────────────────────────
RISK TIERS (and what each requires)
────────────────────────────────────────────────────────────────────────────────

  Tier     Examples                                        Required before starting
  -------  ----------------------------------------------  -------------------------
  Low      UI tweaks, text/copy, small isolated changes    Proceed; note in summary
  Medium   Business logic, new integrations, data          State plan + assumptions;
           transformations                                 flag in Pre-flight
  High     Schema/auth/storage/security changes, large     Stop and confirm before
           refactors, infra, migrations                    any code

Classify the task in the Pre-flight block. When unsure between two tiers,
treat it as the higher one.


────────────────────────────────────────────────────────────────────────────────
DELIVERY SUMMARY (after every change)
────────────────────────────────────────────────────────────────────────────────

Close each task with this block:

  DELIVERED
  1. Summary of change:
  2. Files affected:
  3. Risks identified:
  4. Assumptions made:
  5. Tests performed (and what is untested):
  6. Status: <Implemented | Implemented and tested | Partial | Requires verification | Blocked>
  7. Remaining limitations:
  8. Recommended next steps:


────────────────────────────────────────────────────────────────────────────────
DEFINITION OF DONE
────────────────────────────────────────────────────────────────────────────────

A task is done only when: the change is minimal and scoped, assumptions are
declared, no stop condition was bypassed, tests are stated, regressions were
checked, docs are updated if affected, and the status reported matches reality.


────────────────────────────────────────────────────────────────────────────────
EXAMPLES
────────────────────────────────────────────────────────────────────────────────

Declaring an assumption (Rule 2)
  Bad:  (silently) writes user.fullName because it seems likely to exist.
  Good: "Assumption: the user record exposes fullName. I did not find it in
        the schema — confirm the field name, or I'll read the model first."

Honest status (Rule 15)
  Bad:  "Done — login now works."
  Good: "Status: Implemented, Requires verification. Logic is in place and
        unit-tested; I have not run it against the live auth provider. Please
        confirm before relying on it."

Minimal change (Rule 4)
  Bad:  Asked to fix one date format; reformats and reorders the whole utils
        module.
  Good: Changes only the single formatter, leaves surrounding code untouched,
        notes that a broader cleanup is available if wanted.


────────────────────────────────────────────────────────────────────────────────
CORE OPERATING PRINCIPLE
────────────────────────────────────────────────────────────────────────────────

When uncertain: ask rather than assume, preserve rather than rewrite, verify
rather than claim, explain rather than hide, protect data before adding
features, and prefer simplicity over complexity.


════════════════════════════════════════════════════════════════════════════════
BOUSALA PROJECT OVERRIDES
════════════════════════════════════════════════════════════════════════════════

The following rules extend and override the universal sections above when
working on the Bousala project. They resolve 7 confirmed contradictions and
gaps identified between this skill and the existing bousala-* skills.

When a Bousala Override conflicts with a universal rule, the override wins.

────────────────────────────────────────────────────────────────────────────────
OVERRIDE G3 — Mandatory Skill Loading Before Pre-flight
────────────────────────────────────────────────────────────────────────────────

Before running the Pre-flight block, load ALL of the following skills and
summarize the constraints they impose on the current task:

  1. bousala-architecture
  2. bousala-investment-domain
  3. bousala-safe-zones
  4. bousala-test-protocol
  5. bousala-project-state

The Pre-flight block is not valid until those five skills are loaded.
Implementation without this loading sequence is prohibited.

────────────────────────────────────────────────────────────────────────────────
OVERRIDE C1 — Extended Pre-flight for Bousala
────────────────────────────────────────────────────────────────────────────────

The universal Pre-flight block is insufficient for Bousala. Replace it with
the following extended format for all Bousala tasks:

  PLAN
  - Goal:                <what the user actually wants, in one sentence>
  - Business value:      <why this matters to the user / product>
  - User value:          <what the user gains from this change>
  - Technical complexity: <Low | Medium | High — with one-line justification>
  - Affected files:      <specific files and functions likely touched>
  - Architecture impact: <does this change any layer in the data flow?>
  - Data integrity impact: <does this touch source data, transactions, or
                            accounting calculations?>
  - Risk:                <Low | Medium | High> (see Risk tiers + C2 mapping)
  - Assumptions:         <explicit list, or "none">
  - Approach:            <smallest safe change> | Alternatives: <if relevant>
  - Open questions:      <blockers needing answers, or "none">
  - Recommendation:      <proceed | pause and confirm | do not implement>

If Risk is High, Architecture impact is non-trivial, or Data integrity impact
is non-zero — do not start coding. Confirm first.

────────────────────────────────────────────────────────────────────────────────
OVERRIDE C2 — Risk Classification Bridge
────────────────────────────────────────────────────────────────────────────────

The bousala-safe-zones skill uses a P0–P4 severity scale. The universal
governance skill uses Low/Medium/High. Both are active. Use this mapping:

  Bousala P-level       Governance tier   Required action before starting
  --------------------  ----------------  --------------------------------
  P0 — Data Integrity   High              Stop and confirm before any code
  P1 — Portfolio        High              Stop and confirm before any code
       Accounting
  P2 — Valuation / FX   High              Stop and confirm before any code
  P3 — Reporting        Medium            State plan + assumptions; flag
  P4 — UI only          Low               Proceed; note in summary

When the Bousala P-level and the governance tier disagree, use the higher
of the two. When uncertain between P-levels, treat as the higher P-level.

────────────────────────────────────────────────────────────────────────────────
OVERRIDE C3 — Additional Stop Condition: Bousala Safe Zones
────────────────────────────────────────────────────────────────────────────────

Add the following to the universal Stop conditions list:

  • Modifying any file in the Bousala Safe Zones — see bousala-safe-zones
    skill for the full list. The core protected files are:
      - portfolio/valuation.py       (Valuation Engine)
      - portfolio/closed_holdings.py (FIFO Logic + Realized P&L)
      - fx_rates.py                  (FX Engine)
      - market_data_router.py        (Price Routing)
      - portfolio/holdings.py        (Holdings Engine)
      - portfolio/accounts.py        (Account Engine)
      - portfolio/cash_ledger.py     (Cash Engine)

  When a Safe Zone file must be touched, stop and explain:
    - Why the modification is required
    - Which files and functions are affected
    - What risks are introduced
    - What safer alternatives exist
  Then wait for explicit approval before proceeding.

────────────────────────────────────────────────────────────────────────────────
OVERRIDE G1 — Checkpoint Before Implementation
────────────────────────────────────────────────────────────────────────────────

Before writing any code on a Bousala task, create a Replit version checkpoint.

  Format:   CHK_FEATURE_YYYY_MM_DD
  Example:  CHK_LIABILITIES_MODULE_2026_06_05

This is a hard requirement — not optional for "small" changes. Every
implementation is preceded by a checkpoint so rollback is always available.

Include the checkpoint ID in the DELIVERED summary (item 2, Files affected).

────────────────────────────────────────────────────────────────────────────────
OVERRIDE G2 — Extended Delivery Summary for Bousala
────────────────────────────────────────────────────────────────────────────────

Replace item 5 in the universal Delivery summary with the following
expanded form when working on Bousala:

  5. Tests performed:
       - Test IDs or categories run: <e.g. N01–N10, A11, SETTLE, ADD-POS>
       - Count before change:  <N>
       - Count after change:   <N>  (must be >= count before)
       - Passed:  <N>
       - Failed:  <N>  (must be 0 to mark task complete)
       - Untested / requires manual verification: <list or "none">

If any test fails, do not mark the task complete. Report the failure
before continuing (see bousala-test-protocol Failure Rule).

────────────────────────────────────────────────────────────────────────────────
OVERRIDE G4 — Test Count Floor
────────────────────────────────────────────────────────────────────────────────

The Bousala test count floor is a hard contract enforced by
edgar_app/dev_test_runner.py. It must never decrease.

  Current floor: 258 tests (as of June 2026 — update this line when the
                 floor is raised by a new feature).

Rules:
  - Every meaningful new feature must add tests; the floor is raised, never
    held flat.
  - "Appropriate verification" (universal Rule 13) in Bousala means at
    minimum: all existing tests pass + new tests added for the new behavior.
  - Run dev_test_runner.py before marking any task complete.
  - If a change causes any regression, do not mark done — fix first.

────────────────────────────────────────────────────────────────────────────────
BOUSALA STATUS VOCABULARY (extends Rule 15)
────────────────────────────────────────────────────────────────────────────────

Use the governance status terms consistently across all Bousala task reports:

  Proposed only             — plan shared, no code written
  Implemented               — code written, not yet tested
  Implemented and tested    — code written + all tests passing + count >= floor
  Partially implemented     — some but not all work done; state what remains
  Requires verification     — logic in place; needs manual or live-environment
                              confirmation before relying on it
  Blocked pending clarification — cannot proceed without user input; state
                              what is needed

"It should work" is not a valid status. Always use one of the above.

────────────────────────────────────────────────────────────────────────────────
BOUSALA OVERRIDE SUMMARY TABLE
────────────────────────────────────────────────────────────────────────────────

  Override  Issue type      What it fixes
  --------  --------------  ---------------------------------------------------
  G3        Gap (High)      Skill loading required before Pre-flight
  C1        Contradiction   Pre-flight extended with Bousala-required fields
  C2        Contradiction   Risk tier bridge: P0–P4 → Low/Medium/High mapping
  C3        Contradiction   Bousala Safe Zone touch added to Stop conditions
  G1        Gap (Medium)    Checkpoint creation required before implementation
  G2        Gap (Medium)    DELIVERED block requires test pass/fail counts
  G4        Gap (Medium)    Hard test count floor stated and enforced

All seven issues from the v1.1 → v1.2 review are resolved.
