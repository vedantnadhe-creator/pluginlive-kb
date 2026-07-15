# WhatsApp Messaging (WABA + MSG91)

How PluginLive sends WhatsApp template messages, and why the sending path changed in June 2026.

## Two WABAs

PluginLive owns two WhatsApp Business Accounts (both under business "PluginLive Technologies"):

| | Legacy WABA | Current WABA |
|---|---|---|
| WABA ID | `114696961548335` | `36136604129316933` |
| Phone | `102162976151114` | `1207566512435100` (`+91 63804 85173`) |
| Connected Meta app | `PluginLive_Technologies` (`800145154548623`) — our own app | `Interakt ISV` (`256725303808337`), webhook → `whatsapp.phone91.com` |
| Sending path | Direct Graph API with our token | **MSG91 BSP API** |
| Template namespace | — | `ab150d99_86d0_4d64_a278_7f77da79ec0b` |

The current WABA was onboarded through **MSG91** (Walkover; its WhatsApp infra runs on `phone91.com`), which connects numbers via the "Interakt ISV" Meta tech-provider app. Because messaging on that number is owned by the MSG91/Interakt app — not our own Meta app — **our Graph API token cannot send from it** (returns `(#200) You do not have the necessary permissions to send messages on behalf of this WhatsApp Business Account`). Our token can still *manage* templates (business-asset permission), which is how all templates were migrated onto the current WABA via Meta's `migrate_message_templates` endpoint.

## Sending: MSG91

To deliver from the current WABA, send through MSG91's v5 outbound API instead of Graph API:

```
POST https://control.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/
headers: { authkey: <MSG91_AUTHKEY>, Content-Type: application/json }
{
  "integrated_number": "916380485173",
  "content_type": "template",
  "payload": { "type": "template", "template": {
    "name": "<template_name>",
    "language": { "code": "en", "policy": "deterministic" },
    "namespace": "ab150d99_86d0_4d64_a278_7f77da79ec0b",
    "to_and_components": [
      { "to": ["91XXXXXXXXXX"], "components": { "body_1": {"type":"text","value":"..."}, ... } }
    ]
  }}
}
```
Recipient numbers must include the country code (`91…`). Body variables `{{1}}…{{n}}` map to `body_1…body_n` in order.

### Recipient number normalization (country code)

A bare 10-digit recipient (no `91`) makes Meta reject the send with **error `131026` "Message undeliverable"** — its first listed reason ("the recipient phone number is not a WhatsApp phone number") is the one that actually fires, because Meta can't resolve a number without a country code to a WhatsApp account. The other `131026` reasons (India authentication-template block, ToS not accepted, old client version) are boilerplate and do **not** apply to utility templates like `tpo_application_create`.

Frontend flows were inconsistent: TPORequests / ATS sent the full `91…` number and worked, while the job-role-creation flows (`institute-react` `JobRoles/NewJobRole/RolesForm` and `JobPreview`) used `.slice(-10)` and stripped the country code, so every `tpo_application_create` / `tpo_application_updated` send failed `131026`.

Fix (June 2026): `user-management-node` `app/helpers/whatsapp.js` now normalizes the recipient at the single shared `sendWAmessage` chokepoint (covers both the MSG91 and Meta paths, so all callers are protected regardless of how the frontend formats the number):

```js
const normalizeRecipient = (to) => {
  let digits = String(to ?? "").replace(/\D/g, "");
  if (digits.length > 10 && digits.startsWith("0")) digits = digits.replace(/^0+/, "");
  if (digits.length === 10) digits = `91${digits}`; // default India country code
  return digits;
};
```

Numbers that already carry the country code pass through unchanged; a leading `0` is dropped before the check. The `91` default assumes Indian recipients — revisit if international numbers are onboarded.

## Where this is wired

- **WhatsApp Portal** (`~/tools/whatsapp-portal`, dev.pluginlive.com/whatsapp): template listing/create still use Meta Graph API (works with our token); **sending** goes through MSG91 (`src/lib/msg91.ts`, selected by `WA_PROVIDER`).
- **user-management-node** (PROD = `auth-node`): `app/helpers/whatsapp.js` has both a Meta and an MSG91 send path, selected by `WA_PROVIDER`. No caller changes; template-vs-text branching preserved.

## Config (env)

Provider switch is env-driven; `meta` (default) keeps the legacy Graph API path, `msg91` uses MSG91.

```
WA_PROVIDER=msg91
MSG91_AUTHKEY=<from MSG91 dashboard → Settings/API>
MSG91_BASE_URL=https://control.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/
MSG91_INTEGRATED_NUMBER=916380485173
WA_TEMPLATE_NAMESPACE=ab150d99_86d0_4d64_a278_7f77da79ec0b
```

In PROD these live in the `auth-api-config` ConfigMap (mounted at `/app/.env` on `auth-node`, namespace `api`); in DEV/UAT they are in the service's `.env`/`.env.<env>` (untracked, per-environment).

## Gotcha

Do **not** "just swap `WA_PHONE_ID`" to the current WABA in a Graph-API sender — sends fail `#200`. The current number can only be sent to through MSG91 (or by moving the number's Cloud API registration onto our own Meta app, which would disconnect MSG91).

### Template param values must be single-line (no `\n` / tab / 4+ spaces)

WhatsApp/Meta reject any **template variable value** that contains a newline, tab, or more than 4 consecutive spaces. Via MSG91 this surfaces as a **synchronous HTTP 400** (`ERR_BAD_REQUEST`) on `POST …/whatsapp-outbound-message/bulk/` — the whole bulk call fails, not just one recipient. (This is distinct from the **async** `132000` "localizable_params (N) does not match expected (M)" placeholder-count error, which returns a `{status:"success", …"in process"}` synchronously and only fails later in the delivery report.)

This bit the corporate Schedule drawer: the recruiter's multi-line **Note/Instructions** (a textarea) is sent as the last body param of `corporate_online` / `corporate_offline`, so any note with line breaks 400'd the send. Fix (`user-management-node` `app/helpers/whatsapp.js`): `buildMsg91Components` runs every param through `sanitizeParamValue`, the single choke point every MSG91 template send flows through, so all callers/templates are covered. Any new free-text template param is safe by default — don't re-add newlines downstream.

`sanitizeParamValue` splits on `\r?\n`, squeezes tabs/4+ spaces and trims **per line**, drops blank lines, then joins the surviving lines with a bullet separator `" • "` (`LINE_SEPARATOR`). So a 3-line note renders as `Line1 • Line2 • Line3` — each item stays visually distinct instead of collapsing into one run-on paragraph (the earlier fix joined with a plain space). A single-line note is unchanged (no stray bullet).

**True per-line stacking is impossible inside a template variable.** Meta's block is on `\n`/`\r`/`\t` specifically; the `U+2028` LINE SEPARATOR char passes the 400 check but renders as a broken glyph (`�`) on WhatsApp clients, so it's not a usable substitute — verified on UAT. The only way to get real line breaks is to bake them into the **static** template body text in Meta Business Manager (static text may contain newlines; `{{n}}` values may not) using a fixed number of separate variables, which requires a template edit + Meta re-approval. Bullet-separator is the shipped approach.
