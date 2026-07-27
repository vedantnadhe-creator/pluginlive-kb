# Shortlist Gate (the "neutralising agent") — BUILT, THEN REVERTED

> **Status: reverted on 2026-07-27, parked for a rework.** Not in `Development`
> and not running anywhere. This document exists so the work can be resumed
> from where it stopped rather than reinvented — it records the design, what was
> actually proven on DEV, and the three problems that stopped it.

**Service:** `corporate-node-v2` · **UI:** `corporate-react-v2` (`/v2`)

## The problem it solves

More candidates clear the automated rounds than anyone can interview. Every one
of them lands in the human stage for a person to sift, and that sifting is the
work the agentic pipeline was supposed to remove. The gate cuts the cohort to an
interviewable number by itself, so what is left at the human round is
"interview these N", not "review all of these".

It also fixed something the pipeline still gets wrong: `rounds.service.ts`
advances **everyone who was invited** to the last automated round without
reading their scores (there is a `ponytail:` comment saying so). The gate
required passing the round's own bar to be in the cohort at all.

## Where it sat

Between the **last automated round** and the **first human round after it**.
Anchored on the last automated round rather than the first human stage, because
that is where the evidence stops — a workflow that interleaves (screening →
comms → human sift → aptitude → final interview) would otherwise be cut before
two more rounds of evidence existed.

Consequence worth remembering: **after the gate there are never automated rounds
left**, by construction. Any stage between boundary and target would be either
human (and become the target) or automated (and become the boundary).

## The decision rule — dominance, not weights

The gate auto-rejects candidates who passed **every bar the recruiter set**, so
the rule has to be provable rather than tuned. Nothing weights one round against
another:

> **A dominates B** ⟺ over the rounds they BOTH sat, A is at least as good on
> all of them and strictly better on at least one.

From that, two facts hold for `seats` places, and both are **one-way** — no
later result can overturn either. That is what let the gate decide most of a
cohort while stragglers were still sitting:

| Verdict | Test | Why it is safe |
|---|---|---|
| **CUT** | `dominatedBy >= rejectRank` | ≥ rejectRank people are definitely above them; a new result can only ADD dominators |
| **KEEP** | `unresolved < seats` | at most `seats − 1` others could place higher, counting every straggler as though they will |
| contested | everything else | genuinely weight-dependent, so settle it with a test instead |

Three subtleties that cost correctness if missed — all three were found the hard
way:

1. **`unresolved` counts candidates this one does NOT dominate**, not the ones
   that dominate it. Under a partial order those differ: five mutually
   incomparable candidates are dominated by nobody, and releasing all five for
   three seats is exactly the failure the gate exists to prevent.
2. **Only a candidate whose own results are all in can be decided.** Gaining a
   round can break a dominance that already held, in either direction, which
   would make both tests two-way for anyone mid-pipeline.
3. **A noise margin is required** (`SHORTLIST_EPSILON`, default 3). Assessment
   scores are not precise to the point; calling a 1-point difference "better"
   manufactures dominance out of measurement error and then rejects someone on
   it.

## The ladder — every rung terminates

The gate must never hand back a pile of undecided candidates; removing that work
is the entire point.

1. **Dominance** — provable keeps released, provable cuts rejected
2. **Tie-break** — the contested band sits one authored Role_Based assessment.
   It **RANKS, it does not pass/fail** (everyone already cleared the bar, so a
   bar cannot separate them) and its difficulty is calibrated to the band, not
   the role — a paper they would all pass separates nobody. Topics come from the
   gaps still open in `candidate_memory`.
3. **Composite** — tie-break impossible or unattempted: rank on z-scores with
   declared weights, and record that this is what happened. Deliberately the
   last resort; weights are indefensible as a primary rule.
4. **Surplus** — an exact tie on the seat boundary lets the extra through. One
   more interview is far cheaper than an arbitrary rejection.

## Seats and the padding

```
seats      = max_vacancies × SHORTLIST_INTERVIEW_RATIO   (default 3)
rejectRank = ceil(seats × SHORTLIST_REJECT_PADDING)      (default 1.5)
```

A role with **no vacancy figure gets no gate** — guessing a target and then
rejecting real people against the guess is the wrong kind of helpful. Several
DEV roles carry `0/0`.

The padding is breathing room: the gate only auto-rejects beyond `rejectRank`,
leaving a buffer that a recruiter widening the shortlist can still draw on. The
buffer comes off only at finalisation, when the shortlist can no longer be
widened.

## The hold window — why it always finishes

A stalled gate is a **wall** in front of the interview round, and it fails
silently: nothing errors, no candidate complains, the shortlist simply never
happens. So the deadline is set from the first sweep as the **earliest** of:

- **quorum** — once ≥ 80% of the cohort has landed, stragglers get
  `SHORTLIST_MAX_HOLD_HOURS` (72) and no more
- **window** — the assessment window closing; nothing can arrive after it
- **absolute** — `SHORTLIST_ABSOLUTE_MAX_HOLD_HOURS` (336 = 14 days) from gate
  creation, whatever else is true

Only ever brought **forward**, never pushed out — otherwise a trickle of late
results extends it indefinitely.

## Candidate-facing behaviour

- Rejections used a **separate template** (`shortlistCapacityEmail`). These
  people met the standard, so "after reviewing your profile against the
  requirements" would be false and they would know it. The copy said there were
  more strong applications than interview places.
- Rejections were recorded against the **target** stage, not the boundary —
  both the honest description and the only one that works, since every
  candidate already holds a `sent` dispatch on the boundary round and
  `sendRejection`'s idempotency guard would silently drop it. It also buys the
  never-retract rule for free: a released candidate holds a `manual` dispatch
  there, so rejecting them becomes impossible.
- **The gate adds to a shortlist, it never retracts from one.**

## Proven on DEV

A 13-candidate fixture (`scripts/demo-shortlist-gate.sql` in the service repo,
kept) exercised every rung in one run:

| Check | Result |
|---|---|
| 13 cleared → 6 seats | **6 released, 7 capacity rejections, zero recruiter decisions** |
| Padding | a candidate beaten by 8 of 12 was **held**, not cut, while the round was open |
| Tie-break | authored at the calibrated **5 medium / 3 hard** mix for a band averaging 61.8; settled on score |
| Straggler | landed at 71, took a seat; nothing already decided had to be revisited |
| Screening-only workflow | 3 of 4 released (used to hang forever) |
| Behavior boundary (no score) | gate stood down and released all 4 |
| Discovery | opened 6 gates with **no round ended at all** |
| 3 concurrent sweeps | exactly one set of decisions, no duplicate rows or memory events |

## Why it was reverted — three unsolved problems

All three are the same shape: **the gate stops being a shortlist and becomes a
wall, or decides on an incomplete picture.**

### 1. Workflow edits mid-flight strand candidates *(verified live)*

The gate's identity is pinned to stage ids — `(role, boundary_stage_id)` keyed
off `target_stage_id`. Flipping a round from automated to human moves both.
Tested with 3 candidates held:

- gate correctly went `inert` ✅
- **the 3 held candidates were stranded** — never released, nothing would ever
  move them ❌
- **no new gate opened at the new boundary** ❌
- the note misdescribed the cause ❌

The role ended with no active gate and 3 people frozen. Same failure for
human→automated, disabling a stage, or reordering.

**The fix, unbuilt:** a shared `standDown(gate, reason)` on *every* path to
`inert` that releases what it holds into the freshly-resolved target; discovery
keyed on the **current** boundary rather than "any gate exists"; a hook on
workflow save so the transition is atomic with the edit; and a warning in the
editor, because **an edit cannot un-reject anyone**.

### 2. The gate cannot see candidates still upstream *(verified live)*

The cohort is built purely from dispatches on the boundary stage. Candidates
still sitting an earlier round are invisible, so the gate can hand out every
seat and start rejecting while the pipeline is still feeding it. On DEV,
`a99f336b` (Customer Success demo) **finalised with 3 live candidates
upstream** — harmless only because seats exceeded the cohort.

**The fix, unbuilt:** count live upstream candidates (not rejected, deepest
stage before the boundary, still progressing) and feed them into the split as
additional `pending`. That reuses the already-proven one-way maths — they make
every keep harder while leaving cuts untouched — and blocks finalisation,
bounded by the existing hold deadline so it cannot reintroduce a hang.

### 3. Seats assume exactly one human round

`max_vacancies × 3` implicitly assumes **one** interview round. With three human
rounds at ~50% survival each, a shortlist sized for one starves before the
offer.

Latent today: `proposals.service.ts` enforces *"The LAST must be a human stage"*
with `ai_interview` immediately before it, and DEV has **25 workflows with one
human round and zero with two**. But a recruiter can hand-build more.

**The fix, unbuilt:**
`seats = max_vacancies × RATIO × EXTRA_ROUND_MULTIPLIER^(k−1)` where `k` = human
rounds after the gate. Chosen so **k = 1 reproduces today's number exactly** —
no behaviour change on any existing role.

## What still exists (so resuming is cheap)

| Thing | Where | State |
|---|---|---|
| Tables `corporate.shortlist_gates`, `corporate.shortlist_decisions` | DEV database | **present**, rows cleared |
| `candidate_probes.purpose` column | DEV database | **present**, defaults `gap_probe`; code reference removed |
| Migration | `migrations/20260727T095309Z__shortlist_gate.sql`, and DB-Scripts `Corporate ATS v2 Agentic Evaluation/` | kept, marked **not required** for UAT/PROD so promotion sweeps skip it |
| 13-candidate fixture | `scripts/demo-shortlist-gate.sql` | kept, validated |
| `src/modules/rounds/stageKind.ts` | service | **kept** — introduced by this feature, other work now builds on it |

## Commits

| Repo | Commit | What |
|---|---|---|
| corporate-node-v2 | `6023a40` | the agent |
| corporate-node-v2 | `caa8e99` | hourly sweep timer |
| corporate-node-v2 | `cf511ee` | five stall/mis-placement/double-act fixes |
| corporate-node-v2 | `9ca7ee9` | **the revert** |
| corporate-react-v2 | `5425c6b` → `cb557c6` | timeline node + drawer, then reverted |
| DB-Scripts | `324a7f4` → `1621a83` | schema, then marked not-required |

To resume: `git revert 9ca7ee9` gives the whole feature back (26 tests
included), then work the three problems above before arming anything.

## Env vars (removed; restore with the revert)

`SHORTLIST_GATE_ENABLED` (off by default — it rejects candidates),
`SHORTLIST_INTERVIEW_RATIO` (3), `SHORTLIST_REJECT_PADDING` (1.5),
`SHORTLIST_EPSILON` (3), `SHORTLIST_MAX_HOLD_HOURS` (72),
`SHORTLIST_ABSOLUTE_MAX_HOLD_HOURS` (336),
`SHORTLIST_TIEBREAK_DEADLINE_DAYS` (3), `SHORTLIST_MAX_GATES_PER_SWEEP` (25).
The sweep trigger reused `REMINDER_TICK_TOKEN`.

## Gotchas worth keeping

- **admin-node returns 200 for a failed assignment.** Its role-based candidate
  loop catches per-candidate errors, logs "Successfully assigned assessment to
  all candidates" and still returns 2xx. Never treat a 2xx as proof — verify the
  candidates are really mapped onto the assessment.
- **`candidate_probes_uniq` is `(submission_id, parent_stage_id)`.** A candidate
  who reached the gate by passing a gap probe already owns a probe on the
  boundary stage, so tie-breaks were anchored to the **target** stage instead.
- **Validate authored questions per question, not per paper.** One malformed
  MCQ invalidating all sixteen is what sent the first live tie-break down to the
  composite fallback.
- **z-normalisation amplifies noise.** Three candidates within 2 points came out
  1.22 SD apart. Rounds whose entire spread sits inside the noise margin must be
  treated as non-separating.
- **A stray bare `node dist/index.js` repeatedly held port 4001 on DEV**, so
  `systemctl restart` silently did nothing and the old binary kept serving with
  stale env. Check the port holder against `systemctl show -p MainPID` before
  trusting a restart.
