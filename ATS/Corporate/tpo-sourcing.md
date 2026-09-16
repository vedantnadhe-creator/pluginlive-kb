# Suggested institutes / TPO sourcing (LIVE on DEV + UAT + PROD since 2026-09-16)

Create-role wizard step 4 ("Invite institutes & NGOs") no longer shows the old
"Evaluation agent suggested" column or the "Search & add" campus picker. It
shows one **Suggested institutes** panel: the recruiter says *where to look* and
*how many*, clicks **Find institutes**, and gets a ranked campus list to tick.
**Nothing is sent from the corporate side** — the ticked institutes are stored
and Client Success works the list from the database.

PROD went live 2026-09-16 on `release-v1.40` (images `2026-09-16-07-46-54-release-v1.40`).

## What the recruiter sees

- **Where to look for colleges** — defaults to the job location; accepts states
  as regions and cities, mixed (`Maharashtra` + `Nashik`). Empty = all of India
  (ranked on course fit alone, and the panel says so). "Use job location"
  resets it. Typing shows each state with its live campus count.
- **Campus tiers** (since 2026-09-16, UAT) — a tier band sits between *where* and
  *how many* on one row. It is pre-filled by `GET /v2/sourcing/tier-suggestion`
  from the role's title, CTC max and type (`src/modules/sourcing/tiers.ts`, pure
  + unit-tested): up-market titles (research, quant, ML, PM, IB…) or high CTC
  → tiers 1–2; volume titles (field sales, telecaller, BPO, collections…) or low
  CTC / interns → tiers 2–4; otherwise the middle. Directory reality: tier 1 ≈
  240 campuses, tier 2 ≈ 47k, tier 3 ≈ 200, tier 4 ≈ 39k, so a band is always
  ≥ 2 tiers wide. The ranking (`POST /sourcing/runs` `tiers`) is then
  **limited** to those tiers, and the reason is shown to the recruiter; it is a
  default they can change, not a decision.
- **Institutes to find** — 1–50, default 15. This is *campuses looked up*, not
  contacts found.
- **Find institutes / Run again** — the run ranks every campus in the area that
  fits the role, then walks the list; rows land in rank order with a progress
  line ("Ranked 6 campuses · looking up 3 of 6…"). A 15-campus run is ~1 min,
  50 is ~3 min.
- Each row: rank, campus, city/state, and the reasons — *In Pune · Teaches
  Mechatronics Engineering · Invited to 2 of your roles before · Tier 1 · On
  PluginLive*. **No names, emails or phone numbers are shown anywhere.**
- On-campus roles require at least one institute ticked.
- After **Create role**, the success dialog adds one line: *"Invitations with
  this link will be sent to the placement officers of the N institutes you
  selected."* The institutes are not listed.

## How a run works (corporate-node-v2 `src/modules/sourcing/*`)

1. **Read the JD** — title, department and JD go to Gemini (via LiteLLM, model
   `SOURCING_MODEL`, default `gemini-2.5-flash`) with the same extractor the old
   suggestions used → domains, branches/streams, level. Gateway down → title
   keywords, and the run says so.
2. **Rank campuses** — one SQL over the whole live directory
   (`institute.institutes_campuses`, ~87k rows) inside the chosen area:
   location 40 same city / 18 same state; course fit up to 40 (domain via
   `institute.institute_campus_course_view`, rank-weighted, plus `pg_trgm`
   `public.similarity()` on stream names — must be schema-qualified because the
   pool's `search_path` is `corporate`); tier 20/14/8/4 as a tiebreak only
   (61% of campuses are un-triaged tier 4); +2 per prior invite from this
   corporate (max 8); +6 if the campus is onboarded on PluginLive.
3. **Contacts** — for each of the top N: placement staff with a PluginLive
   login (`user_management.users`) and the campus record first; where email
   OR phone is still missing, one Gemini **grounded** call
   (`tools:[{googleSearch:{}}]`, ~15 s, `SOURCING_CONCURRENCY`=4 in parallel)
   reads the college's own site. Grounded Gemini rejects `response_format`, so
   the prompt asks for JSON and the parser is lenient. Runs in-process, not
   BullMQ.
4. **Stripped at the BFF** — the Next.js route `src/app/api/sourcing/runs/*`
   returns only `id, campusId, campusName, city, state, tier, domains, score,
   reasons`. The browser never receives a contact.

## Endpoints

| Route (corporate-node-v2, `/v2` prefix) | Purpose |
|---|---|
| `POST /sourcing/runs` | start a run: role draft + `sourcingLocations` (cities/states) + `limit` ≤ 50 |
| `GET /sourcing/runs/:id` | poll; the BFF strips contacts |
| `POST /roles/:id/sourcing-selection` | store the ticked institutes after create |
| `GET /sourcing/tier-suggestion?title&ctcMax&employmentType` | default tier band + reason |
| `GET /cities/states` | Indian states/UTs with live campus counts (~100 ms) |
| `GET/POST /roles/:id/outreach`, `/outreach/drafts` | email/WhatsApp send path — **unused**: no BFF route and corporate-node-v2 has no public ingress on PROD |

## Tables (`corporate` schema, DB-Scripts `Corporate TPO Sourcing/`)

- `tpo_sourcing_runs` — one run per wizard pass (`role_id` NULL until create),
  status/progress, the draft it ranked from.
- `tpo_sourcing_leads` — one row per campus per run: ranking facts, and the
  contact the lookup found with provenance (`source_url`). **This is where CS
  reads the TPO name/email/WhatsApp from.**
- `tpo_sourcing_selections` — one row per institute per role (`UNIQUE
  (role_id, campus_id)`): campus, rank shown, links to run and lead.
- `tpo_outreach` — audit of sends; empty while the send path is unused.

Applied DEV 2026-09-15/16, UAT 2026-09-16, PROD 2026-09-16 (tables only; code ships with release-v1.40).

## Gotchas

- DEV DB emails are masked (`abc…@`), so DB-tier leads look odd there; UAT and
  PROD are real.
- The count is campuses, not contacts: "14 of 20 campuses have a contact"
  means widen the area or the number, not a setting.
- A failed grounded lookup degrades to "no contact"; it never breaks ranking.
- Related: [bulk-candidate-upload.md](bulk-candidate-upload.md) sits on the
  same step; [v2-strangler-fig.md](v2-strangler-fig.md) for the PROD topology.
