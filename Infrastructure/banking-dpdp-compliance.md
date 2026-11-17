# Banking LMS (lms.pluginlive.com) — DPDP Act 2023 / DPDP Rules 2025 due diligence

Audit date 2026-11-17 (read-only; code at UAT `f8f79c42a`, PROD `release/prod-v1.1` `951b758a8` v1.1.19, PROD DB `banking_prod`).
DPDP Rules notified 13 Nov 2025; substantive obligations (notice, consent, security, breach, retention, rights, children) apply from
**13 May 2027**. Companion: `pilvidya-dpdp-compliance.md` (aividya). Not legal advice — have counsel approve notice/consent text.

## Role
- Self-registered learners (Google sign-in / self-register): PluginLive is the **Data Fiduciary**.
- Learners, faculty and guardians uploaded by colleges/corporates (2,188 of 2,322 PROD student rows have never signed in): the
  institute is the Fiduciary and PluginLive its **Data Processor** — needs a processing agreement with each institute.

## PROD data inventory (2026-11-17)
169 auth accounts, 2,322 student rows, 28 trainers; proctoring photos (`proctoring_logs.photo_url`, 9 violations), 10 interview
recordings (61 MB), assessment uploads/media, project documents, curriculum PDFs; college mode adds guardian name/phone/email and
APAAR/ABC IDs (`student_academic_profiles`, 0 rows on PROD yet); `admin_error_logs` 3,524 rows since 2026-06-03 (10 with emails,
9 with mobile numbers). No date of birth anywhere → age (child status) unknown.

## In place
Hosting in India (OCI Mumbai, VM + OCI Object Storage); TLS; RLS on all tables, anon locked out; edge functions require a signed-in
caller (11-11 + 11-17 TTS fix); open signup closed; OTP login; nightly DB backup kept 14 days; auth audit log kept in DB since Aug;
voice practice shows a capture notice + "I agree"; college parent alerts have `guardian_alerts` + `guardian_consent_at`; AI calls
go through the LiteLLM gateway with task attribution.

## Gaps (priority)
| # | Gap | DPDP | Evidence |
|---|---|---|---|
| 1 | No privacy notice; no consent at sign-in/registration; no consent record or withdrawal | s.5, s.6, Rule 3–4 | Login.tsx, register flow: no notice/checkbox; no consent table |
| 2 | No way to exercise rights: access/summary, correction, erasure, nomination; no grievance contact | s.11–14, s.8(9)–(10), Rule 14 | no export/delete/grievance code or page |
| 3 | Proctoring: webcam photos captured and **sent to AI vision models**; no notice/consent before camera; no retention | s.5–6, s.8(7) | ProctoringMonitor.tsx uploads photos; analyze-proctoring sends image_url to LLM |
| 4 | Personal data to foreign AI/speech processors (Gemini, OpenAI, ElevenLabs, Deepgram): names (Robo Faculty, practice plan), learner name+college+**mobile** in agent-runtime context, voice transcripts, face photos; no processor list/DPAs disclosed | s.8(2), s.16, notice | grep of functions |
| 5 | No retention schedule / erasure: recordings, photos, uploads, error logs kept forever; **76 release DB dumps in /data/backups never pruned**; old UAT storage copy on PROD VM | s.8(7), Rule 8 | /data/backups |
| 6 | Logs: nginx 14 days, container logs 5×20 MB; Rules require ≥1 year of access logs | Rule 6 | logrotate |
| 7 | No breach runbook (notify affected users + Board without delay, detailed report within 72 h) | s.8(6), Rule 7 | no doc |
| 8 | Children: no age capture; college first-years may be 17; parental consent is staff-recorded, not verifiable; at-risk analytics/proctoring = behavioural monitoring (education exemption in Fourth Schedule — confirm with counsel) | s.9, Rule 10–12 | no DOB column |
| 9 | Data minimisation / PII in logs: emails + mobiles in admin_error_logs; APAAR/ABC IDs collected | s.8, s.6 | DB scan |
| 10 | Institute contracts: no data-processing terms (instructions, security, breach notice, deletion on exit) | s.8(2) | contract templates |
| 11 | Still-open security items from the 11-02 audit (shared 3rd-party keys UAT/PROD, CSP report-only, answer keys/payment secrets in browser) | s.8(5) reasonable safeguards | project_lms_security_audit |

## Recommended order
1. Now (low effort): privacy notice page + first-login consent screen with stored, versioned consent + withdraw; grievance/DPO contact
   in app footer; proctoring/recording notice before camera; drop mobile/email from agent-runtime LLM context; mask emails/phones in
   admin_error_logs; prune release backups (keep last N) and remove the UAT storage copy from PROD.
2. Next: data-rights requests (download my data, correct, delete account → admin queue with 30-day SLA, cascading delete incl. storage);
   retention jobs (proctoring photos/recordings e.g. 180 days after result, error logs 1 year, inactive accounts per policy);
   1-year access-log retention (ship nginx/auth logs to OCI Object Storage); breach runbook + contact list.
3. Before 13 May 2027: processor register + DPAs (Google, OpenAI, ElevenLabs, Deepgram, Sarvam, MSG91, Resend/mail relay);
   institute data-processing addendum; age declaration + verifiable parental consent path for under-18 learners; counsel review.

## 2026-11-17 — Priority-1 (high) gaps fixed on UAT `40fc816e0` (PROD pending go)
- **Notice:** public `/privacy` (data, purposes, processors incl. foreign AI/speech, retention, rights, grievance contact
  `VITE_PRIVACY_CONTACT_EMAIL` → default privacy@pluginlive.com — mailbox must exist), linked from sign-in. Version constant
  `PRIVACY_NOTICE_VERSION` in `src/lib/privacy.ts`; bump it to re-ask everyone.
- **Consent:** `PrivacyConsentGate` (App level, all roles incl. admins) blocks until the user agrees; stored in `privacy_consents`
  (purpose platform/proctoring/recording, notice version, user agent, withdrawn_at).
- **Rights:** My Profile and Trainer profile → "Privacy & my data": download my data (JSON, own rows via RLS, ~40 tables),
  requests (correction, erasure, full copy, nominee, grievance) in `data_requests` with 30-day `due_at`, withdraw consent
  (signs out; gate blocks until re-agreed). Admin console → Users → **Privacy Requests** queue; **Erase account** runs edge fn
  `privacy-requests` (admin only): user's storage objects (owner) → `erase_user_data` (nullable refs unlinked, required ones
  deleted, students/profile/roles) → auth user; request kept with user_id null as proof.
- **Capture consent:** proctored assessments (TakeAssessment, StudentAssessmentTaker) and interview recording (practice
  interview, video interview runner) show what is captured + require a tick before camera/mic; stored per purpose.
- **Retention:** edge fn `privacy-retention` (service-role only) deletes `assessment-media/proctoring/*` and `interview-recordings/*`
  older than `PRIVACY_MEDIA_RETENTION_DAYS` (default 180) and clears `proctoring_logs.photo_url`; UAT cron 21:15 UTC
  `~/banking-sb/privacy-retention-daily.sh` → `~/logs/privacy-retention.log`.
- **AI minimisation:** agent-runtime tools no longer return learner mobile numbers to the model.
- Migration `20261117140000_dpdp_consent_requests_retention` (DB-Scripts `c8adf4b`, DEV+UAT applied, PROD pending).
- Checks: `~/banking-checks/dpdp/flow.cjs` (18/18 on UAT; erases the QA learner from `journeys/fixture-flow.sql`), `capture.cjs`.
- **Not done (needs go / business):** PROD release; PROD backup pruning (71 release dumps + 4 app dirs = 1.8 GB, keep newest 5;
  UAT storage copy 391 MB on the PROD VM); DPAs with processors; institute data-processing addendum; counsel review of the text.

## 2026-11-17 — Student-journey DPDP test + fixes: UAT `a4a9d9fbd`
Test `~/banking-checks/dpdp/student.cjs` (steps gate assess interview download requests api withdraw college erase; fixtures
`journeys/fixture-flow.sql` + `fixture.sql` + override of the proctored "Banking KYC AML Assessment May 2026"; the erase step deletes
the QA learner): **49/49 PASS** on UAT after the fixes below. Leftover scan used by the erase step: `/tmp/leftover.sql` pattern
(every public table's user_id/student_id/learner_* columns + storage owner).
Fixed:
- `b1ce9a160` — consent/request records could be rewritten (03_grants gives authenticated full UPDATE): trigger
  `private.privacy_record_guard` sets accepted_at/created_at/due_at to server time, consent only withdrawable once (at now()),
  requesters can't change requests; download reads `proctoring_violations` through the learner's attempts (no student_id column).
- `a4a9d9fbd` — erasure left 11 tables with the person's id (no FK: usage stats, coach usage, menu permissions, report tokens,
  module-group assignment, error logs …): `erase_user_data` sweeps user_id/student_id/learner columns, clears authorship columns,
  keeps `payment_requests` (legal retention) and `data_requests` (proof); the admin function stops if anything is skipped.
DB-Scripts 155e7f4 + e4de44b (DEV+UAT applied, PROD pending). Sign-out from the consent prompt lands on `/` (session cleared) by design.
