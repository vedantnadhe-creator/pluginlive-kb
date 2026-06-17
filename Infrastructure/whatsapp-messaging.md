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
