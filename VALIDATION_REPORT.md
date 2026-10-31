# AI-Retina V7 deployment validation

**Result: source fixes prepared; production deployment blocked. No private deployed URL exists from this task.**

Inspected repository: `hoagzitam/ai-retina`, base commit
`aec21282bcbb8d8e2d80e997ddc666b723bdd7fd`. Existing visibility: public.
No patient data was retrieved, uploaded or committed. No host audience or
repository visibility was changed, and no viewers were invited.

## Findings and changes

| Area | Finding | Change |
| --- | --- | --- |
| Configuration | Missing DATABASE_URL silently selected SQLite; admin defaulted to changeme | Production requires PostgreSQL, TLS, distinct strong admin/access secrets and configured private case storage |
| Transaction pooling | NullPool and prepare_threshold=None already present | Preserved both; added connection timeout and replaced session advisory lock with transaction-scoped locking |
| Initialization | DDL and singleton insertion swallowed arbitrary failures | One transaction covers DDL, additive migration and conflict-safe singleton insert; failures propagate |
| Real images | Renderer always generated synthetic scans | Private bucket/manifest loader; server-side image download, format checks and metadata stripping; missing images block case opening |
| Blinding | Participant card displayed disease module | Removed module label from participant card; production learning mode defaults off |
| Live voting | Read-then-write race; stale form could vote after close; repeated cases reused old votes | State row locked during submission; atomic ballot upsert; new round identity; old rounds preserved; revealed results are current-round aggregates only |
| Participant flow | Research reload lost session; repeated research submits could advance twice | Research code resume, serialized assignment/progress checks and agreement gate |
| Live identity | Reload generated a new code | Persistent random-code registry and resume form retain the same ballot across reloads |
| Privacy | Real data could be mixed with demo behavior | Private data requires production mode; no synthetic fallback in production; server error details and telemetry disabled |

## Completed checks

Command: `python -m pytest -q tests` with Python 3.12.
**12 passed; 7 PostgreSQL variants skipped** because this managed runner is root
and cannot create or switch to an unprivileged PostgreSQL service account.

- Streamlit AppTest: one moderator and two independent participant sessions,
  case opening, image rendering through the private-image code path, voting,
  count=2, ballot update without duplicate count, close, reveal and new round.
- Live-code resume recovers the existing ballot and keeps the count at one.
- 20 concurrent updates by one coded participant produce one ballot.
- 16 concurrent schema initializations leave one singleton row.
- Closed voting and stale round IDs reject submissions; results stay hidden
  until reveal; repeated rounds preserve history and start at zero votes.
- Duplicate concurrent research submissions save one response and increment
  progress once; research codes resume the same assignment.
- Missing/invalid images block moderator case opening. Extra patient fields,
  external asset URLs and traversal paths are rejected. Image metadata is stripped.
- Production misconfiguration and incorrect access passwords fail closed.
- Python compilation and Git whitespace checks completed.

All case metadata and image bytes used in these checks are **artificial fixtures**.
AppTest executes Streamlit application sessions but does not validate a real browser's
WebSocket/timer behavior, deployment access policy, Supabase network connection,
actual private storage policy or a real approved clinical case. The two-second
polling path is retained; real-time behavior must be verified on the private host.

## Deployment blockers

1. Streamlit Community Cloud currently displays its sign-in screen; there is no
   authenticated deployment session in this task.
2. Supabase is available as an integration but is not connected. No production
   DATABASE_URL, storage credentials or approved real-case manifest is available.
3. The repository contains only synthetic data. A real de-identified case must be
   supplied through private storage and reviewed for burned-in image identifiers.
4. The available Sites hosting runtime cannot run this Python Streamlit app or
   connect to PostgreSQL over raw TCP. A static mock would not validate V7.
5. Owner-only host access must be established before clinical data is enabled.
   A new Streamlit app from this public repository would default to public, so
   that path has not been used.

## Outstanding acceptance

After authenticated host/Supabase access and an approved private case are available,
follow DEPLOY_GITHUB_STREAMLIT.md. Validate through the actual transaction pooler,
check authorized and signed-out access, test two browser sessions with live polling,
and record the literal private production URL and deployed source revision.

Additional protocol limits: anonymous codes are bearer identifiers, not proof of
one unique human. Enrollment, exact consent language, reference-label approval and
who may receive the participant access secret remain investigator responsibilities.
The single live-session design supports one conference at a time.
