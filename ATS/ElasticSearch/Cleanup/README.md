# Cleanup Module

**Controller Prefix:** `/cleanup`
**Auth:** User (API key)
**Source:** `search-service-1/src/modules/cleanup/`

## Overview

The Cleanup module manages old ElasticSearch index cleanup. Since the Sync module creates timestamped indices (e.g., `events_degree_stream_specialisations_2024_01_01`), old indices accumulate over time. This module provides both an automated cron job and a manual HTTP endpoint to delete old indices, keeping only the most recent N.

---

## API Endpoints

| Method | Route | Parameters | Description |
|--------|-------|------------|-------------|
| GET | `/cleanup/run` | `prefix?` (index prefix), `keep?` (count to retain) | Manually trigger index cleanup. Defaults: prefix = `{INDEX_PREFIX}events_degree_stream_specialisations_`, keep = 10 |

---

## Cron Job (`IndexCleanupCron`)

| Schedule | Prefix | Keep Count | Description |
|----------|--------|------------|-------------|
| `0 0 * * *` (midnight daily) | `{INDEX_PREFIX}events_degree_stream_specialisations_` | `ES_CLEANUP_KEEP_COUNT` env (default: 30) | Deletes oldest indices exceeding keep count |

---

## Cleanup Logic (`CleanupService`)

1. Fetch all ES indices via `client.cat.indices`
2. Filter indices matching the given prefix
3. If count ≤ keepCount → do nothing
4. Sort alphabetically (oldest first due to timestamp naming)
5. Delete indices beyond the keep threshold
6. Log each deletion

---

## Key Features

- **Dual trigger:** Automated daily cron + manual HTTP endpoint
- **Configurable retention:** `ES_CLEANUP_KEEP_COUNT` env var controls how many indices to keep
- **Prefix-based:** Only targets indices matching a specific prefix pattern
- **Safe deletion:** Sorts alphabetically and deletes from oldest, keeping newest
- **Separate ES client:** Uses its own `Client` instance (not the shared `ClientServices`)
