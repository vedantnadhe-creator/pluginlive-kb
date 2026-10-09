# Tester S3 download access

Added 2026-10-09. Tester sessions use the existing `s3-upload` MCP server,
configured in `/home/ubuntu/.olibot-codex/config.toml` and `/home/ubuntu/.claude.json`.
The server implementation is `/home/ubuntu/s3-mcp-server/index.js`.

## Download a file

1. Call `list_files` with the relevant prefix to find the exact object key.
2. Call `download_file` with `key` and, if required, `bucket`.
3. Read the local path returned by the tool to inspect the file.

The default bucket is `pl-uat-public-docs`. Downloads use authenticated
`GetObject`, so an object need not have a public URL. Access remains bounded by
the existing MCP storage credentials; this change adds no IAM grants.

The tool writes only to a newly created `/tmp/s3-download-*/` directory, with
private file permissions. It accepts no destination path, cannot overwrite
repository files, and changes no storage objects. Read-only testers can inspect
the resulting path without receiving code-edit permission. Existing upload and
listing tools retain their behavior.

The maximum download size is 100 MiB, enforced both from the object metadata
and while streaming. Folder keys, unavailable objects, permission errors, and
oversized downloads return tool errors. Failed downloads are removed; successful
files remain temporarily available for inspection and may be removed when done.

New MCP connections load the tool on the next tester turn. A currently running
turn retains its already discovered tool list. No dashboard restart is needed.

## Verification

`node --test /home/ubuntu/s3-mcp-server/download.test.js` checks binary integrity,
destination containment and permissions, folder rejection, both size-limit
paths, and storage-error propagation.

On 2026-10-09, a fresh MCP client discovered `download_file`, downloaded a real
14,237-byte object with the existing configured credentials, confirmed its size
against the storage listing, and verified that a missing object returns an error.
The verification file was removed after inspection.
