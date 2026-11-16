# aividya — School library management (UAT)

**Status:** live on UAT at `pilvidya.uat.pluginlive.com`, frontend commit `2c50808e` on
`feat/chat-simulations`. The database hardening migration is applied to `eduspeak_uat`.
PROD does not exist for aividya.

## User surfaces

- **School Operations → Library** (`LibraryPanel`): staff can search the school catalogue,
  create a title with an edition and physical copies, issue by title or copy, return or mark a
  copy lost/damaged, renew, cancel a hold, view overdue/fine totals, and record stocktake counts.
- **Student → Library** (`/student/library`): students browse available copies, search by title,
  author, ISBN or barcode, reserve/cancel a reservation, see current loans and projected fines,
  and renew eligible loans.
- **Platform Admin → Library administration** (`/admin/library-admin`): admins can inspect
  editions, copies, loans, reservations, vendors and fine policies for the selected school, and
  issue/return/cancel through the same guarded operations.

## Database boundary

The migration `20261118105000_library_operations_hardening.sql` adds the school owner to
`library_vendors`, keeps copy-level rows under the book's `school_id`, and replaces separate
browser writes with atomic, security-definer operations:

- `library_create_title`
- `library_issue_book` and `library_issue_copy`
- `library_return_loan`
- `library_renew_loan`
- `library_reserve_copy` and `library_cancel_reservation`
- `library_record_stocktake`

All staff operations use the current School Operations working school. Students can only reserve,
renew, or read their own loans; a staff member cannot issue a book to a student from another
school. Expired reservations are released while the copy row is locked, so concurrent counter
actions cannot issue the same copy twice.

Legacy catalogue rows with a null `school_id` need an explicit backfill before school staff can
see them. The first stocktake release records totals and notes; barcode-by-barcode reconciliation
is a later enhancement.

## Release record

- DB-Scripts: `EduSpeak Postgres Migration/20261116T101241Z__pilvidya_library_operations_hardening.sql`
  (`436cd4c`); DEV is `n/a` because PilVidya DEV is hosted Supabase, UAT is applied, PROD is
  pending.
- UAT image: `eduspeakreact:2c50808e`; edge functions were synced and restarted from the same
  checkout.
- Verification: 12 focused frontend regression tests passed; UAT root and chunk manifest returned
  HTTP 200; all eight library operation functions and `library_vendors.school_id` were present;
  the built image contained no DEV or `supabase.co` URLs.
