# ForkCheck — Project Context

> Tagline: **Know what you can eat.**
> Check App Store, domain and trademark availability before launch.

## What this is

ForkCheck is a mobile, **plan-first** meal app for people who eat under constraints:

- **Food allergies (primary):** multiple allergies, from mild to severe, including the top 9 (milk, egg, peanut, tree nuts, fish, shellfish, wheat, soy, sesame) and custom ones
- **EoE (eosinophilic esophagitis):** trigger-food exclusions, 2-4-6 elimination diet phases, swallowing difficulty
- **GLP-1 users (Ozempic, Wegovy, Mounjaro):** small portions, nausea, high protein needs, muscle preservation

It tells the user **what they can eat**, logs meals with minimal effort, and tracks symptoms, weight and strength. The founder has multiple food allergies and EoE and is the first user.

ForkCheck started as an allergen search app for restaurant menus. That design (restaurant allergen ingestion) becomes the app's **"Eating out"** feature in phase 2.

## Core principle

**The LLM proposes, code decides.** An LLM may suggest meals and extract ingredients, but a deterministic safety filter written in plain code has the final say on allergens. An LLM that occasionally suggests an allergen is a safety bug, not a quality issue.

## How to work with me (read this first)

I'm building this project to learn and as a serious portfolio piece, so I need to understand every line. Work in small steps and **stop after every addition**.

An "addition" is any new file, feature, endpoint, migration, component, test suite or meaningful change. After each one:

1. **Stop.** Do not start the next addition until I say to continue.
2. **What you added:** list the files created or changed, in one or two lines each.
3. **Code walkthrough:** explain the code section by section in plain language: what each part does and how the pieces connect.
4. **Thought process:** explain how you approached the problem and the order you built it in.
5. **Why it's coded this way:** name the alternatives you considered and why you chose this approach (tradeoffs in safety, simplicity, performance, cost or future flexibility). Point out where it connects to the core principle or the safety rules.
6. **How to test it:** the exact commands or steps to run it and see it working.
7. **New concepts:** the first time a library, pattern or concept appears (for example Pydantic validators, row-level security, property-based testing), explain it briefly.
8. **Then ask** whether I have questions or want changes before moving on.

Keep each addition small enough to explain clearly. If a task is large, propose a plan of small steps first and wait for my approval before writing code.

## Target users

1. Adults with multiple food allergies who are tired of checking every label and menu
2. Adults with EoE, especially during elimination diets
3. GLP-1 users who want to keep muscle while losing weight
4. Any overlap of these groups (common: many people with EoE also have food allergies)

## Non-goals

- No diagnosis or treatment claims. This is a wellness and planning tool. Never write copy that says the app "treats", "cures" or "diagnoses" anything.
- **Never claim a food is guaranteed safe.** Product formulas and restaurant recipes change. The app reduces risk; it does not replace reading the label or asking the restaurant.
- No emergency or medical guidance for allergic reactions beyond "follow your allergy action plan and call emergency services."
- No workout video library, no social feed, no calorie-obsession features.
- Never replace a doctor, allergist or dietitian.

## Stack

| Layer         | Choice                                                                                                                                  |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Mobile app    | Expo (React Native) + TypeScript                                                                                                        |
| Backend       | Python, FastAPI, Pydantic v2                                                                                                            |
| Database      | Postgres on Supabase (row-level security); pgvector later                                                                               |
| Auth / IAM    | Auth0 by Okta: Apple and Google sign-in, RBAC (roles + permissions), MFA; Supabase Third-Party Auth so Postgres RLS trusts Auth0 tokens |
| Food data     | USDA FoodData Central + Open Food Facts (ODbL: keep attribution)                                                                        |
| LLM           | Claude or OpenAI with structured outputs, validated by Pydantic                                                                         |
| Ingestion     | Python jobs on GitHub Actions cron                                                                                                      |
| File storage  | Cloudflare R2 or S3 (meal photos, label photos, source documents)                                                                       |
| Notifications | Expo push                                                                                                                               |
| Hosting       | Railway or Render first; AWS Fargate later                                                                                              |

## Architecture

**Offline (scheduled ingestion):** Fetch sources → Parse ingredient lists → LLM extract (allergens, texture) + alias dictionary match → Validate (rules + human review) → Publish to Postgres with a source link and `verified_at` date for every tag.

**Online (user requests):** Mobile app → FastAPI → LLM planner proposes meals → **Safety filter** checks every ingredient against the user's allergies and exclusions → only passing meals return to the app.

**Health sync:** The app reads weight and body composition from Apple HealthKit / Google Health Connect. Read-only, never write.

## Allergy handling (most important section)

### How allergens are detected

Allergens are detected **two independent ways**, and either one is enough to flag a food:

1. **Alias dictionary (deterministic):** a maintained table mapping ingredient words to allergens. Examples: whey, casein, ghee, lactose → milk; albumin, lysozyme → egg; semolina, spelt, durum → wheat; tahini → sesame; lecithin (soy) → soy. Hidden sources matter: many ingredient names don't contain the allergen's name.
2. **LLM extraction:** reads ingredient lists and "contains" / "may contain" statements and returns structured tags.

If the two disagree, the food goes to the review queue and stays **unsafe until reviewed**.

### Severity drives the rules

Each user allergy has a severity, and the filter gets stricter as severity rises:

| Severity                  | `contains` | `may_contain` / shared facility      | Unknown status | Data older than freshness window |
| ------------------------- | ---------- | ------------------------------------ | -------------- | -------------------------------- |
| Intolerance               | Excluded   | Allowed, with a warning              | Excluded       | Warning                          |
| Allergy                   | Excluded   | Excluded by default (user can allow) | Excluded       | Warning                          |
| Severe (anaphylaxis risk) | Excluded   | Always excluded                      | Excluded       | Excluded until re-verified       |

### Copy rules

- Say **"No listed allergens found"** or **"Fits your profile"**, never "safe" or "allergen-free."
- Always show the data source and when it was last verified.
- Packaged foods: remind users to check the current label, since formulas change.
- Restaurant items (phase 2): always prompt the user to confirm with staff and mention cross-contact.

### Allergy features

- Multi-allergy profile with severity per allergen, including custom allergens (e.g. mustard, celery, lupin, specific fruits)
- Barcode and label-photo scanning that flags allergens in the ingredient list
- **Chef card:** a shareable screen listing the user's allergies and severity, to show restaurant staff (phase 2, translatable)

## Identity and access (IAM)

Auth0 is used deliberately to gain hands-on IAM experience. Treat identity and authorization as a first-class part of the project, not boilerplate.

### Setup

- **One Auth0 tenant shared with Reelsmith** (separate dev and prod tenants later), so the same identity works across both apps.
- **Applications:** ForkCheck mobile app (Native, Authorization Code + PKCE via `react-native-auth0`), ForkCheck admin web (Single Page App, later).
- **API:** `https://api.forkcheck.app` registered in Auth0 with RBAC enabled and "Add Permissions in the Access Token" turned on.
- **Database:** Supabase is used for Postgres only. Supabase Third-Party Auth is configured to trust Auth0 tokens, so row-level security policies can use the token's `sub` claim.

### Roles and permissions (least privilege)

| Role       | Permissions                                                                                 | Who                                                               |
| ---------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `user`     | `read:foods`, `read:plans`, `write:plans`, `write:logs`, `read:own_data`, `delete:own_data` | Every signed-up user (assigned by an Auth0 Action on first login) |
| `reviewer` | user permissions + `review:allergens`                                                       | People who approve alias/LLM disagreements in the review queue    |
| `admin`    | reviewer permissions + `manage:catalog`, `manage:users`, `read:audit_log`                   | The founder                                                       |

### Rules

1. **Authentication in Auth0, authorization in two layers:** FastAPI checks permissions on every endpoint, and Postgres RLS ensures a user can only ever read their own rows. Either layer alone should block unauthorized access.
2. FastAPI validates every access token: signature via JWKS, `iss`, `aud`, expiry. Use a reusable `require_permission("review:allergens")` dependency; never check roles by name in endpoint code, check permissions.
3. **MFA required** for `reviewer` and `admin` (enforced with an Auth0 Action).
4. Users are keyed by the Auth0 `sub` claim; never use email as an identifier.
5. Log every sensitive action (catalog changes, review decisions, role changes, data deletion) to an `audit_log` table with actor `sub`, action, target and timestamp.
6. Short-lived access tokens; refresh tokens with rotation on mobile; tokens stored in secure device storage only.
7. Check which Auth0 features your plan includes (some MFA options and advanced features may require a paid tier).

## Core schema

- `users`: id, auth0_sub (unique), modes (array: allergy / eoe / glp1), protein_target_g, texture_default
- `allergens`: id, name, is_top9
- `allergen_aliases`: allergen_id, alias, notes
- `user_allergies`: user_id, allergen_id, severity (intolerance / allergy / severe), allow_may_contain (bool), notes
- `user_exclusions`: user_id, allergen_id, reason (eoe_trigger / elimination_phase / self), active_from, active_to
- `elimination_phases`: id, user_id, phase (2 / 4 / 6-food), started_on, endoscopy_on, outcome
- `foods`: id, name, source (usda / off / restaurant / user), source_ref, ingredients_text, protein_g, kcal, texture_score (1–5, ease of swallowing), verified_at
- `food_allergens`: food_id, allergen_id, status (contains / may_contain / free / unknown), detected_by (alias / llm / both / manual), confidence, verified
- `recipes`, `recipe_items`: recipe_id, food_id, grams
- `meal_plans`, `plan_items`: user_id, date, slot, recipe_id, filter_version
- `meal_logs`: id, user_id, eaten_at, recipe_id or photo_key, parsed_items (json), confirmed
- `symptom_checkins`: user_id, date, dysphagia, nausea, reaction (none / mild / moderate / severe), energy (0–4), notes
- `body_metrics`: user_id, measured_at, weight_kg, body_fat_pct, lean_mass_kg, source (healthkit / health_connect / manual)
- `strength_logs`: user_id, date, exercise, reps, load_kg
- `audit_log`: id, actor_sub, action, target_type, target_id, details (json), created_at
- Phase 2: `restaurants`, `source_documents`, `menu_items`, `item_allergens` (from the original ForkCheck design)

## Rules for Claude when working on this repo

### Safety (never break these)

1. The safety filter is **plain, deterministic code** with full unit and property-based test coverage. Never move allergen decisions into a prompt.
2. **Unknown allergen status = unsafe.** Apply the severity table above exactly.
3. A food is flagged if **either** the alias dictionary or the LLM finds an allergen. Disagreements go to review and stay unsafe until resolved.
4. The LLM may only return food and recipe **ids that exist in the catalog**. Reject anything else; never let the model invent a food.
5. Every meal plan stores the `filter_version` that approved it.
6. Never write "safe", "allergen-free" or "guaranteed" in user-facing copy.
7. Insight copy describes **patterns, not diagnoses** ("reactions were logged after meals with X", never "you are allergic to X").
8. Any change to the filter, alias table or severity rules requires new tests in the same PR.

### Data and privacy

- Allergy and health data are sensitive: minimal collection, encrypted at rest, read-only health sync.
- Build data export and account deletion from day one.
- Never send user data to ad networks or analytics SDKs that resell data.
- Never put personal data in URLs or logs.

### Code conventions

- Backend: typed Python, Pydantic models for every request, response and LLM output. FastAPI routers by domain (`foods`, `allergies`, `plans`, `logs`, `metrics`).
- Mobile: TypeScript strict mode; logging works offline and syncs later.
- Migrations through Supabase/Alembic only; never edit the schema by hand.
- Every PR: tests pass, filter tests untouched or extended, no secrets committed.
- Keep secrets in environment variables now; AWS Secrets Manager after sprint 8.

### Product rules

- **Plan-first, track-second.** If a feature adds logging effort without giving value back, push back on it.
- Photo logging is two steps: model guesses, user confirms with one tap. Unconfirmed logs never count toward stats.
- Muscle can't be measured directly. Use proxies: body composition from a smart scale, strength log, weekly protein consistency.

## Sprints (two weeks each)

### Sprint 0 — Foundation

- [ ] Monorepo: `/app` (Expo), `/api` (FastAPI), `/ingest` (Python jobs)
- [ ] Supabase project (Postgres only)
- [ ] Auth0 tenant: native application, API with RBAC, `user` / `reviewer` / `admin` roles and permissions, Apple and Google sign-in
- [ ] Auth0 Action that assigns the `user` role on first login
- [ ] FastAPI skeleton with health check, Pydantic settings, JWT validation (JWKS, issuer, audience) and a `require_permission()` dependency
- [ ] Supabase Third-Party Auth trusting Auth0; first RLS policy on `users`
- [ ] CI on GitHub Actions: lint, type-check, tests
- **Done when:** you can sign in on your phone, call an authenticated endpoint, and a test proves a token without the right permission gets a 403.

### Sprint 1 — Food catalog and allergen detection

- [ ] Ingest a USDA FoodData Central subset and Open Food Facts products with ingredient lists
- [ ] Allergen alias dictionary for the top 9 plus common custom allergens, with tests
- [ ] LLM extraction of allergens, may-contain statements and texture_score into Pydantic schemas
- [ ] Disagreement detection between alias and LLM results + review queue, protected by the `review:allergens` permission
- [ ] `audit_log` table recording every review decision
- [ ] Store source link and `verified_at` for every tag
- **Done when:** a few thousand foods are tagged, each traceable to its source, and every alias/LLM disagreement is in the review queue.

### Sprint 2 — Allergy profile, planner and safety filter

- [ ] Multi-allergy profile with severity and may-contain preference; EoE exclusions and elimination phases; protein target; texture preference
- [ ] Safety filter implementing the severity table, with unit + property-based tests (e.g. Hypothesis)
- [ ] LLM planner returning catalog ids only; reject and retry on invalid output
- [ ] "What can I eat?" screen: today's plan, swap a meal, see why a food was excluded
- **Done when:** automated tests show no food containing a user's allergen, at any severity, ever reaches a plan.

### Sprint 3 — Scanning, logging and progress

- [ ] Barcode and label-photo scanning that flags allergens against the user's profile
- [ ] One-tap "ate the planned meal" + two-step photo logging
- [ ] Daily five-second check-in (swallowing, nausea, reactions, energy)
- [ ] HealthKit / Health Connect read sync for weight and body composition
- [ ] Simple strength log and weekly protein consistency score
- [ ] Offline logging with background sync
- **Done when:** the founder uses it every day for a week, including scanning groceries.

### Sprint 4 — Beta

- [ ] TestFlight + Android internal testing for about 20 people from food allergy and EoE communities
- [ ] Insights screen (food-symptom patterns, clearly labeled as patterns)
- [ ] Doctor- and allergist-ready PDF report
- [ ] Data export and account deletion (removes the user from Postgres and Auth0)
- [ ] MFA enforced for `reviewer` and `admin` roles
- [ ] Track retention, meals logged, scans, median time to log
- **Done when:** first real retention numbers are in.

### Sprint 8 — Production hardening (shared with Reelsmith)

- [ ] Move the API to AWS ECS Fargate in a VPC; RDS Postgres in a private subnet
- [ ] Secrets in AWS Secrets Manager; GitHub OIDC with scoped IAM roles
- [ ] CloudWatch logs and alarms; stream Auth0 logs to CloudWatch
- [ ] Separate Auth0 dev and prod tenants; Auth0 config managed as code (Auth0 Deploy CLI or Terraform provider)
- **Done when:** the app runs on the production setup.

### Phase 2 (after sprint 8)

- **Eating out:** restaurant allergen ingestion (fetch, parse PDF/HTML, LLM extract, validate) passed through the same safety filter, with a confirm-with-staff prompt
- Chef card for restaurants, translatable
- GLP-1 mode: nausea-friendly filter, dose and injection-day tracking
- Grocery list from the meal plan

## Metrics to track from day one

- Beta users and day-30 retention (category benchmark: roughly 3–8%)
- Plans checked by the filter, with zero allergen misses
- Alias/LLM disagreement rate and review turnaround
- Median time to log a meal; scans per active user
- p95 API latency
