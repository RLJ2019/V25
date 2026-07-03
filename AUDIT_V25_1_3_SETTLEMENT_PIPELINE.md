# V25.1.3 Settlement Pipeline Audit

Dev-branch build for `dev/v25.1.3-settlement-pipeline`.

This release adds a manual-only settlement pipeline while preserving V25.1.2d pick generation. It must not be merged to `main` until V25.1.2d completes 5/5 valid shadow days.

## Added

- Settlement modules for 1X2, BTTS and totals.
- Conservative postponed/cancelled/abandoned policy.
- Profit calculator for WIN/LOSS/PUSH/VOID.
- No-vig CLV with same-bookmaker, benchmark and consensus fallback.
- API-Football fixture result reader.
- Supabase repository helpers for unsettled VALUE_PICK records and settlement upserts.
- Manual-only GitHub Actions workflow `.github/workflows/settlement-v25.yml`.
- V25.1.3 settlement hardening migration.
- Unit tests for split-line rejection, postponed transition, abandoned certainty and CLV fallbacks.

## Main safety

Do not upload this ZIP to `main`. Upload it only to `dev/v25.1.3-settlement-pipeline`.
