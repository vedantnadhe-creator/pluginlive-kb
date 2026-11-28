# PilVidya (aividya) — DPDP compliance: current state

Status as of 2026-11-17 on UAT (`adc2e83f`, branch `feat/chat-simulations`). There is no PilVidya PROD deployment.
The law is the DPDP Act 2023 plus the DPDP Rules 2025; most obligations apply from about May 2027.

## What is in place

| Area | How it works |
|---|---|
| Data location | UAT runs in OCI Mumbai (`ap-mumbai-1`). |
| Database access | Personal-data tables reject anonymous REST reads (UAT lockdown). Access goes through edge functions or `SECURITY DEFINER` RPCs. |
| Caller checks on edge functions | Every function that reads or changes a child's data must identify the caller. Staff and scheduler functions use `staffGate` (`_shared/staff-guard.ts`): a staff Supabase session or the service key. Student functions use `requireStudentSession`. Parent functions use `requireParentSession`, plus `requireLinkedStudent` when a child id is given. Anonymous calls get 401 / `unauthorized`. |
| Parent right to access | Parent → Family & privacy → **Export my child's data** calls `data-privacy-export` (`action: "export"`) with the parent session. It covers only the parent's verified, linked child. Credential columns (password, token, session, otp, secret) are stripped. The download covers the profile and 14 tables (tests, question history, attendance, period attendance, assignments, homework, exam marks, report cards, progress, doubts, fees, library, transport, wellbeing logs). |
| Parent right to erasure | **Request erasure** only files a `privacy_requests` row (`privacy-request`). An admin completes it in Admin → Data requests with `admin_privacy_erase` (type ERASE), which is audit-logged and has a 30-day target. No endpoint erases on the parent's click. |
| Nova assistant | `nova-agent` data tools use only ids the caller proves: a student device session, a parent session plus linked child, or a staff sign-in (school from `staffScope`). The platform snapshot is limited to ops admins. Without proof, chat works but the data tools return nothing. |
| Parent OTP | A real OTP is sent when an `llm_config` row `feature='sms-otp'` is enabled (twilio/msg91). Without SMS, the fixed code `1234` is issued only to numbers in the `PARENT_DEMO_OTP_MOBILES` functions env var. On UAT that list is 8 QA/demo numbers in `~/eduspeak-sb/functions-secrets.env`, and the container must be recreated after editing it (`docker compose up -d --no-deps functions`; a restart is not enough). Other numbers get "We couldn't send the OTP by SMS…". Never set the variable on PROD. UAT has no SMS gateway, so a new parent number cannot sign in until it is added to the list or SMS is configured. The sign-in page gives demo instructions only when the server identifies pilot delivery. A returning parent keeps the school-verified link when their child uses the same mobile number. |

## Open gaps (audit 2026-11-17)

1. **No privacy notice or consent** on student, parent or staff sign-in, and no privacy-policy page (DPDP s.5, Rule 3).
2. **No verifiable parental consent** per child (s.9, Rule 10). `parent_consents` holds only notification preferences.
3. **Consent withdrawal is not wired.** `ai-consent-gate` fails to boot (it is on the hold list) and has no caller check. The `consent_change` request type has no handler.
4. **Erasure is incomplete.** `admin_privacy_erase` does not clear storage files, voice notes, wellbeing logs, chat-simulation transcripts, admission/SIS records (DOB, medical notes), proctoring data or AI-pool served rows. `data-subject-request` "delete" marks requests completed without erasing; it should be removed.
5. **Retention.** `data_retention_policies` covers only telemetry, and `retention_runs` is empty, so no purge has ever run. Student data is not deleted after exit.
6. **No breach (72 h) runbook** and no grievance officer published (s.8(6), s.8(10), Rules 7 and 14).
7. **AI providers.** `progress-report-generate` sends the student's name, marks and attendance to the LLM gateway, whose providers may be outside India. Use a placeholder instead of the name, and get processor terms with no training on our data.
8. **School scoping.** Staff-gated functions accept any staff member, not only the student's own school. Add school checks where a function takes a student, assessment or school id.
9. `parent-invite-co-parent` always issues `1234` for the invite. Only a signed-in parent can trigger it, but it should use the SMS path.

## Checks

- `~/pilvidya-checks/dpdp/guards.cjs`: anonymous callers refused on 20 functions; teacher, internal, parent and student allowed; parent cannot export another child; no credentials in the export; OTP limits; Nova. 31/31 on `adc2e83f`.
- `frontend/src/test/dpdpCallerChecks.regression.test.ts`: source-level guard contracts.

Related: [Platform admin](pilvidya-platform-admin.md) (Data requests), [Parent experience](pilvidya-parent-experience.md).
