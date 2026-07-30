# GitHub Access — credentials for every PluginLive checkout

How the DEV / UAT / PROD boxes authenticate to `github.com/PluginLive-Technologies/*`.
Read this when a `git pull`/`git push` on any box returns **403**, or when a deploy script fails
at its `git fetch` step.

## Current credential (as of 2026-07-30)

| | |
|---|---|
| Type | **Fine-grained** personal access token (`github_pat_…`) |
| GitHub account | **RajPluginLive** |
| Resource owner | `PluginLive-Technologies` (the org — *not* a personal account) |
| Permissions | `Contents: Read and write`, `Metadata: Read` |
| Expiry | ≤ 90 days — **it will expire and break every box** |
| Where the value lives | `~/.git-credentials` on each box (mode 600). Never committed here. |

Installed on **DEV**, **UAT** (`uat.pluginlive.com`) and **PROD** (`140.245.25.134`).

## Why classic PATs stopped working

On **2026-07-30** the org enabled a policy that rejects classic PATs with a lifetime > 90 days:

```
remote: The 'PluginLive-Technologies' organization forbids access via a personal access
tokens (classic) if the token's lifetime is greater than 90 days.
→ 403
```

The long-lived `Alex-PluginLive` classic PAT that every box had been using died instantly, and with
it **every** `git fetch` / `git push` on DEV, UAT and PROD — so no deploy script could run at all
(`deploy.sh` / `auto_deploy.sh` all start with `git fetch` + `git pull origin`). It also killed
read access, not just pushes.

Non-workarounds, for the record: the `gh` CLI and the GitHub MCP server are authenticated as
**vedantnadhe-creator**, which has no access to org repos (404, not 403); the SSH keys on the boxes
(`id_rsa`, `id_rsa_alex`, `id_rsa_mari`) are not registered with GitHub.

## Rotating the token (do this before it expires)

1. Sign in as an account with write access to the org repos → https://github.com/settings/personal-access-tokens/new
2. **Resource owner: `PluginLive-Technologies`**, expiry ≤ 90 days, repository access = All repositories,
   **Repository permissions → `Contents: Read and write`** (plus `Metadata: Read`, auto-added).
   Add `Workflows: Read and write` only if a push may touch `.github/workflows/*`.
   Skip `Administration` — nothing in the deploy flow needs it and the token sits in plaintext on three boxes.
3. If the org gates fine-grained tokens, an owner must approve it under
   *Org → Settings → Personal access tokens → Pending requests*; it 403s until then.
4. Install on **each** box — two places, both required:

```bash
TOKEN=<new github_pat_…>

# (a) the credential store
cp ~/.git-credentials ~/.git-credentials.bak.$(date +%s)
sed -i -E "s#^https://(Alex-PluginLive|x-access-token):[^@]*@github.com#https://\1:${TOKEN}@github.com#" ~/.git-credentials

# (b) the token baked into each checkout's origin URL — this OVERRIDES (a), so it must be done too
find ~ -maxdepth 5 -name .git -not -path "*/node_modules/*" | while read g; do
  d=$(dirname "$g"); u=$(git -C "$d" remote get-url origin 2>/dev/null) || continue
  case "$u" in *github.com/PluginLive-Technologies/*)
    git -C "$d" remote set-url origin \
      "$(echo "$u" | sed -E "s#https://([^@/]*@)?github.com/#https://x-access-token:${TOKEN}@github.com/#")"
    echo "updated: $d";;
  esac
done

git -C ~/api/student-node fetch origin --dry-run && echo OK    # verify
```

**Gotcha:** step (b) is the one people miss. Most checkouts have the old token embedded directly in
`origin` (`https://x-access-token:<token>@github.com/…`), and an embedded URL credential wins over
`~/.git-credentials` — fixing only the credential store leaves every repo still 403ing.

Coverage of the 2026-07-30 rotation: **63 checkouts on DEV** (`~/api`, `~/frontend`, plus
`Elastic-Search/search-service`, `Mail-Server`, `Resume_parser`, `assesment/*`, `pluginlive-designs`,
`projects/devops-control-center`, `resume-match{,-staging}`, and the `actions-runner/_work/*`
CI workspaces), **29 on UAT** (incl. `ucat-ai-prep`, `pil-ai-learning`, `banking-career-launchpad`),
**25 on PROD** (`~/repositories/{api,frontend}/*`, `builder-jenkins` workspaces, `medverse-build`).
Backups of the credential file: `~/.git-credentials.bak.<epoch>` on each box.

## Not covered by this token

- `vedantnadhe-creator/pluginlive-kb` (this repo) and `vedantnadhe-creator/whatsapp-engineer` — they
  use the separate **vedantnadhe-creator** credential and were never affected by the org policy.
- `PluginLive-Technologies/DB-Scripts` — pushed with the **vedantnadhe-creator** PAT (the MCP GitHub
  account does not have access); see the `db-script-push` skill.
