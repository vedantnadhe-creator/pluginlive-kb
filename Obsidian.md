# Obsidian — Knowledge Base Tool

> **Website:** [obsidian.md](https://obsidian.md/)
> **Type:** Local-first, Markdown-based knowledge management app
> **Core Concept:** Linked thinking — bi-directional links + visual knowledge graphs
> **Privacy:** All notes stored as plain `.md` files on your device, not in a cloud service

---

## What is Obsidian?

Obsidian is a powerful knowledge management tool that stores notes as plain Markdown files locally on your device. It's built around the concept of "linked thinking" — connecting notes using `[[bi-directional links]]` to create a personal or team knowledge graph. Unlike Notion or Confluence, your data never lives on someone else's server unless you choose to sync it.

---

## Why Obsidian for Our Knowledge Base?

Our existing `pluginlive-kb` repo is already Markdown files. **Migration is essentially zero-effort** — just open the repo folder as an Obsidian "vault."

### Benefits
- **No vendor lock-in** — plain `.md` files, works with Git
- **Offline-first** — works without internet
- **Fast search** — instant full-text search across all notes
- **Visual connections** — graph view shows how notes relate
- **Plugin ecosystem** — 1000+ community plugins
- **Free for personal & commercial use** (no license required since 2025)

---

## Core Features

### Bi-Directional Links
- Use `[[note-name]]` to link between notes
- Backlinks panel shows every note that links TO the current note
- Unlinked mentions detect references even without explicit links

### Graph View
- Visual map of how all notes connect
- Filter by tags, folders, or link depth
- Useful for spotting isolated notes or discovering unexpected connections

### Bases (New — 2025/2026)
- Core plugin for database-like views of notes
- Table view, gallery view, map view
- Powered by note properties (YAML frontmatter)
- Similar to Notion databases but backed by Markdown files

### Canvas
- Freeform infinite 2D space
- Arrange notes, images, web pages, and cards visually
- Great for brainstorming, architecture diagrams, and mapping flows

### Templates
- Create reusable note templates (e.g., meeting notes, decision records)
- Store in a designated `_templates/` folder
- Insert via hotkey or command palette

### Tags & Properties
- Tag notes with `#tag-name` inline
- Add structured metadata via YAML frontmatter:
  ```yaml
  ---
  type: decision
  date: 2026-03-27
  status: approved
  ---
  ```

---

## Pricing (as of March 2026)

| Plan | Cost | What You Get |
|------|------|---------------|
| **Personal** | **Free** | All features, plugins, themes — personal & commercial use |
| **Sync** | $4/mo (annual) or $5/mo | End-to-end encrypted sync across devices |
| **Publish** | $8/mo (annual) or $10/mo | Turn notes into a public website / wiki |
| **Catalyst** | $25 one-time | Early access to features, support development |

- **Students/Faculty/Nonprofits:** 40% discount on Sync & Publish
- **Commercial license:** No longer required (removed early 2025)

---

## Setting Up as a Team Knowledge Base

### Option 1: Git-Based (Recommended for Us)

Since `pluginlive-kb` is already a Git repo, this is the most natural approach:

1. Each team member installs [Obsidian](https://obsidian.md/) (free)
2. Clone the `pluginlive-kb` repo locally
3. Open the cloned folder as an Obsidian vault (`Open folder as vault`)
4. Install the **Obsidian Git** community plugin for auto-pull/push
5. Version history, branching, and PR reviews come free with Git

**Pros:** Free, familiar workflow, full version history, works with existing CI/CD
**Cons:** Merge conflicts possible on simultaneous edits, no real-time collaboration

### Option 2: Obsidian Sync

1. Each team member creates an Obsidian account
2. Enable Sync ($4-5/mo per user)
3. Share specific folders or entire vault
4. Real-time collaboration with live cursors (via Relay plugin)

**Pros:** Seamless, end-to-end encrypted, works across devices
**Cons:** Monthly cost, less control over version history

### Option 3: Cloud Drive (Google Drive / OneDrive / Dropbox)

1. Place the vault folder in a shared cloud drive
2. Each team member opens it as an Obsidian vault

**Pros:** Simple, no extra cost if you already have cloud storage
**Cons:** Sync conflicts possible, no real-time collaboration, less reliable than Sync

---

## Recommended Folder Structure

For our knowledge base, a structure like this works well:

```
pluginlive-kb/
├── _templates/           # Note templates
│   ├── decision.md
│   ├── meeting.md
│   └── module-doc.md
├── _attachments/          # Images, PDFs, etc.
├── Assessment/            # Assessment module docs (existing)
│   ├── README.md
│   ├── aptitude.md
│   ├── communication.md
│   ├── custom.md
│   ├── rolebased.md
│   ├── schedule.md
│   ├── admin.md
│   ├── admin-frontend.md
│   └── institute.md
├── ATS/                   # ATS module docs (existing)
├── Architecture/          # System architecture, tech decisions
├── Runbooks/              # Deployment, incident response
├── Decisions/             # ADRs (Architecture Decision Records)
├── pluginlive.md          # Company overview (existing)
├── CLAUDE.md              # Claude Code instructions (existing)
└── README.md
```

### Organization Best Practices
- **Prefer links over folders** — Obsidian works best with many small, richly-linked notes
- **Use tags for cross-cutting concerns** — `#api`, `#frontend`, `#database`, `#deployment`
- **Use YYYY-MM-DD dates** everywhere for consistency
- **One concept per note** — easier to link and find
- **Link liberally** — wrap any reference to another concept in `[[double brackets]]`

---

## Essential Plugins for Knowledge Base Use

### Collaboration
| Plugin | Description |
|--------|-------------|
| **Obsidian Git** | Auto-commit, pull, push from within Obsidian — perfect for Git-based KB |
| **Relay** | Real-time collaboration with live cursors, folder-level sharing |
| **Peerdraft** | Real-time and async editing with end-to-end encryption |

### Knowledge Management
| Plugin | Description |
|--------|-------------|
| **Dataview** | Query notes like a database — dynamic lists, tables, task views |
| **Bases** (core) | Database-like views of notes (table, gallery, map) |
| **Templater** | Advanced templates with dynamic content and scripts |
| **Calendar** | Daily notes calendar view |
| **Kanban** | Kanban boards backed by Markdown |

### Navigation & Search
| Plugin | Description |
|--------|-------------|
| **Quick Switcher++** | Enhanced file switching with symbol search |
| **Graph Analysis** | Advanced graph metrics and pathfinding |
| **Omnisearch** | Full-text search across notes, PDFs, and images (OCR) |

---

## Limitations to Know

- **Team size:** Works best for small teams (3-5 people). Not a Confluence replacement for large orgs
- **No real-time co-editing built-in** — requires plugins (Relay, Peerdraft) or Sync
- **No web access by default** — notes are local-only unless you use Sync or Publish
- **No permissions/roles** — everyone with vault access can edit everything
- **Learning curve** — Markdown + linking mental model takes some getting used to

---

## Quick Start Checklist

- [ ] Download Obsidian from [obsidian.md](https://obsidian.md/)
- [ ] Clone `pluginlive-kb` repo locally
- [ ] Open the cloned folder as a vault in Obsidian
- [ ] Go to Settings → Community Plugins → Enable
- [ ] Install **Obsidian Git** plugin
- [ ] Install **Dataview** plugin
- [ ] Set `_templates/` as the template folder in Settings → Templates
- [ ] Start adding `[[links]]` between existing notes
- [ ] Explore the Graph View to see connections

---

## Resources & References

- [Obsidian Official Site](https://obsidian.md/)
- [Obsidian Help Docs](https://help.obsidian.md/)
- [Obsidian Pricing](https://obsidian.md/pricing)
- [Obsidian 2026 Features](https://eathealthy365.com/obsidian-2026-all-the-new-features-you-need-to-know/)
- [Obsidian Tips 2026](https://www.geeky-gadgets.com/obsidian-tips-tricks-2026/)
- [Best Plugins 2026](https://www.dsebastien.net/the-must-have-obsidian-plugins-for-2026/)
- [PKM with Obsidian & AI](https://ericmjl.github.io/blog/2026/3/6/mastering-personal-knowledge-management-with-obsidian-and-ai/)
- [Using Obsidian for Teams](https://medium.com/@ensleytan/using-obsidian-for-group-km-145646068cd7)
- [Vault Structure Guide (Steph Ango / kepano)](https://stephango.com/vault)
- [Vault Template (GitHub)](https://github.com/kepano/kepano-obsidian)
- [Relay — Team Collaboration Plugin](https://relay.md/)
