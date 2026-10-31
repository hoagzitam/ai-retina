# AI-RETINA Human–AI Platform V7 Online

Streamlit research, live conference voting, investigator analytics and optional
self-learning, backed by PostgreSQL. Clinical case files stay in private storage.
The repository is public and must never contain patient files or real credentials.

## Local development

Use Python 3.12:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q tests
python -m streamlit run streamlit_app.py
```

Development uses SQLite and 15 clearly labeled **synthetic** cases. Set a local
`ADMIN_PASSWORD` to test moderator tools. Synthetic scans are procedural drawings,
not patient OCTs. Tests use artificial metadata and tiny generated image fixtures.
PostgreSQL tests use a disposable embedded server when the test runner is
unprivileged and `pgserver` is installed; they are explicitly skipped for root.
No tests connect to production databases or private patient storage.

## Private deployment

See [DEPLOY_GITHUB_STREAMLIT.md](DEPLOY_GITHUB_STREAMLIT.md) and the redacted
[secrets template](.streamlit/secrets.toml.example). Production refuses to start
without PostgreSQL, TLS, separate strong access/admin secrets, and private case
storage. A participant password is an extra gate; owner-only hosting access must
also be verified before enabling clinical assets.

- `DATABASE_URL`: Supabase **transaction pooler** URI, normally port 6543,
  with `sslmode=require` or certificate verification. Password URI characters
  must be percent-encoded. Plain `postgres://` and `postgresql://` normalize to
  the installed psycopg 3 driver.
- `APP_ENV=production`: disables SQLite and synthetic-case fallback.
- `ADMIN_PASSWORD` and `APP_ACCESS_PASSWORD`: distinct random secrets, at least
  16 characters. Actual values belong only in the hosting secret manager.
- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_STORAGE_BUCKET`,
  `CASE_MANIFEST_PATH`: server-only access to an investigator-approved manifest
  and PNG/JPEG images in a **private** Supabase bucket.
- `LEARNING_ENABLED`: defaults to false in production to avoid exposing reference
  answers before research participation. Enable learning on a separate training
  deployment, or only after the study protocol permits reference exposure.

## Real-case manifest

Upload a UTF-8 JSON manifest privately, never to GitHub. Top-level fields:
`deidentified_reviewed: true`, `research_use_approved: true`, and `cases: [...]`.
Each case must contain exactly the fields listed in `src/data.py::_COLUMNS`, plus
`image_paths`, an array of one to eight relative object paths in the same private
bucket. Use pseudonymous case IDs (1–32 ASCII letters, digits, `_` or `-`).

An investigator must review both free text and every image for identifiers,
including burned-in names, dates, record numbers and filenames, and confirm
permission for research use. The review flags are attestations, not an automated
privacy assessment. Do not use patient identifiers in case IDs or object paths.
The server rejects unexpected metadata fields, public buckets, external URLs,
invalid files and missing images. PNG/JPEG pixels are re-encoded without EXIF or
comments; that does **not** remove identifiers burned into pixels. Images are
fetched server-side; service keys and storage URLs are not sent to participants.
No synthetic image is substituted when an approved image fails to load.

## Multi-user behavior

- Schema creation, additive migration and singleton insertion are one transaction
  under `pg_advisory_xact_lock`. Errors propagate and roll back. Existing data is
  preserved. Legacy open voting is closed on migration and must be reopened.
- SQLAlchemy uses `NullPool`; psycopg has `prepare_threshold=None` and a connection
  timeout for compatibility with Supabase transaction pooling.
- Opening a case validates its images and creates a new round. Voting, closure
  and submission lock the singleton state row; stale-round and closed votes fail.
- Atomic upsert gives one ballot per participant code per round. Vote updates
  replace the ballot; opening the same case again preserves previous-round data.
- Participants see current-round aggregate results only after reveal. The
  investigator retains access to legacy votes and coded research exports.
- Live state and moderator counts poll every two seconds. Participants save their
  random live code and can resume it after a reload; resuming retains their ballot
  and avoids a second counted vote. Use distinct codes only for distinct test
  participants. Codes are bearer identifiers inside the private access boundary,
  not proof of unique human identity; study enrollment remains investigator-led.
- Research codes can resume saved assignments. Concurrent or duplicate research
  submissions cannot advance progress twice. Case module labels are hidden in
  participant views; investigator previews include the reference key.

See [VALIDATION_REPORT.md](VALIDATION_REPORT.md) for completed checks and outstanding
production validation. This is a research/education platform; protocol, privacy,
consent text and reference labels need investigator review before study use.
