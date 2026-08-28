# Meraaj — Documents Multi-Upload Port (Option B patch)

Patch file: `meraaj_documents_multi_upload.patch`
Generated with: `git diff 10afcb2 891d9a9 -- <5 code files>` (scoped, no artifacts).

## Source commits (main)
- `e8a47c9` — Meraaj multi-upload: multiple traveler docs, types (passport/visa/photo/ticket/other),
  metadata (registrant linkage, passport_no, filename, type), pre-upload staging (select/preview/list/remove),
  sequential upload with progress, TravelerDocs viewer (image + PDF preview, print, download, permission-aware delete).
- `bd361b0` — Upload size rule: 10MB per individual file + 20MB per selected batch (frontend + backend).
- `891d9a9` — auto snapshot of the above (no extra logic).

Base of the diff: `10afcb2` (state immediately BEFORE the documents/upload work).

## Files changed (5 code files ONLY)
| File | +/- | Purpose |
|------|-----|---------|
| backend/storage.py | +1 | `MAX_FILE_BYTES` = 10MB, add `MAX_BATCH_BYTES` = 20MB |
| backend/documents.py | +9 / -3 | add `ticket` type, `passport_no`, `batch_total_bytes`; enforce per-file 10MB + batch 20MB; carry passport_no in Rahal doc sync payload |
| frontend/src/components/TravelerDocs.js | +53 / -20 | multiple upload, per-file 10MB + batch 20MB validation, image/PDF preview, print, download, permission-aware delete, doc types + passport_no display; exports `DOC_TYPES`, `docLabel` |
| frontend/src/pages/PackageDetail.js | +69 / -6 | per-traveler pre-upload staging (select/preview/list/remove), sequential upload with progress after booking creation, 10MB/20MB validation |
| frontend/src/pages/Wallet.js | +1 / -1 | wallet receipt single-file 10MB rule |

EXCLUDED (intentionally not in patch): `backend/_storage/*`, generated artifacts, local test files.

## NOT touched (approved Live behavior preserved — verified: 0 hunks)
`backend/integration.py`, `backend/market.py`, SSO, HMAC, package/inventory sync,
cancellation policy, escrow, passport-uniqueness business rule.

## Dependencies (respect these when applying)
- `backend/documents.py` imports `MAX_FILE_BYTES`, `MAX_BATCH_BYTES`, `ALLOWED_MIME` from `backend/storage.py`
  → apply `storage.py` before/with `documents.py`.
- `frontend/src/pages/PackageDetail.js` imports `{ DOC_TYPES, docLabel }` from `frontend/src/components/TravelerDocs.js`
  → apply `TravelerDocs.js` before/with `PackageDetail.js`.
- Backend `documents.py` expects an existing document storage layer + `/api/bookings/{id}/documents`
  routes and `traveler_documents` collection already present on the recovery base. If the recovery base
  predates the documents subsystem entirely, port the base documents infrastructure FIRST (out of scope of this patch).

## Exact apply order (on branch `recovery/live-approved-20260828`)
```
git checkout recovery/live-approved-20260828
git apply --check memory/recovery_patches/meraaj_documents_multi_upload.patch   # dry-run
git apply memory/recovery_patches/meraaj_documents_multi_upload.patch
# (or) patch -p1 < memory/recovery_patches/meraaj_documents_multi_upload.patch
```
If applying file-by-file: 1) storage.py 2) documents.py 3) TravelerDocs.js 4) PackageDetail.js 5) Wallet.js

## Expected conflicts
Likely only where the approved-Live base already has an OLDER version of the same regions:
- `backend/documents.py`: `DOC_TYPES` set, `DocIn` model, the size-check block, and the `_notify_docs`
  `by_idx.append({...})` block — if the base differs here, resolve by KEEPING the new fields
  (`ticket`, `passport_no`, `batch_total_bytes`, 10MB/20MB checks) while preserving base ownership/audit/signed-delivery.
- `backend/storage.py`: the `MAX_FILE_BYTES` line — if the base value differs, keep 10MB and add `MAX_BATCH_BYTES`.
- `frontend/src/components/TravelerDocs.js` & `PackageDetail.js`: context-heavy; if the base has a simpler
  uploader, prefer the new component logic but re-check any base-specific data-testids / props.
- `frontend/src/pages/Wallet.js`: trivial one-line size change; conflict only if base uses a different limit constant.

No conflicts expected in SSO / HMAC / market / integration (not in patch).
