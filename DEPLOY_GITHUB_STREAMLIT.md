# Owner-private V7 deployment

## Current state

Source has been inspected and patched. No deployment or clinical data access has
been completed in this task. The Streamlit dashboard requires sign-in; Supabase
is not connected. Do not interpret a development smoke test as production approval.

## Deployment sequence

1. Sign in to the existing Streamlit Community Cloud account and select the
   intended app or a new owner-private app. Do not add viewers or send invitations.
2. The existing GitHub repository is public. Streamlit apps deployed from public
   repositories default to public. **Do not create a publicly accessible clinical
   app and then change it to private.** Use a private source repository or an
   existing app whose owner-only policy has already been verified. Preserve the
   existing repository visibility unless the owner requests a change. The patched
   source branch can be copied privately without credentials or clinical assets.
3. Use Python 3.12 and `streamlit_app.py` as the entry point. Install
   `requirements.txt`. Keep all secrets in the hosting secret manager using the
   key names in `.streamlit/secrets.toml.example`; never paste secrets in chat,
   GitHub, logs or the deployment report.
4. Configure the real Supabase transaction-pooler DATABASE_URL with TLS. Use a
   dedicated application role scoped to its research tables, not a general
   organization administrator. Initial deployment needs CREATE/ALTER access for
   the additive schema setup. Confirm this on a disposable staging database first.
5. Configure a private storage bucket and `CASE_MANIFEST_PATH`. Review the schema
   and de-identification requirements in README before enabling any real case.
   Restrict the storage credential to the smallest supported access. The existing
   V7 service key remains server-side; never publish it as a frontend key.
6. Deploy privately. Verify host access from both an authorized owner session
   and a signed-out session **before loading clinical assets**. An unauthorized
   visitor must not receive case metadata, image bytes or research exports.
7. Validate on an isolated research test database and approved de-identified
   case. The workflow writes coded votes and research responses; keep validation
   records isolated from the actual study, and do not erase production data.

## Smallest acceptance workflow

- Moderator signs in, selects an approved real case and sees every required image.
- Moderator opens the case; participant sees the same images without reference
  labels and sees voting closed.
- Moderator opens voting; participant status changes within the two-second poll.
- Two separate authorized participant sessions each submit diagnosis, management
  and confidence. Moderator count becomes two. Updating one ballot keeps count two.
- Close voting; a stale form submission is rejected at the database boundary.
- Reveal results; participants see current-round aggregates and reference labels.
- Open the same case again; count is zero and the previous round remains stored.
- Start a research assignment, submit once, reload/resume with its code, and verify
  exactly one progress increment and a single response.
- Restart the app and confirm persistence, initialization success, and absence of
  prepared-statement errors. Repeat concurrent initialization on staging through
  the actual Supabase transaction pooler before calling that configuration validated.
- Record the literal returned production URL, owner-only access result, source
  commit, configuration key presence (never values), case pseudonym, vote counts,
  and any remaining verification limits.

## Rollback

Redeploy the prior source revision while keeping access owner-private. Additive
`live_rounds`, `live_round_votes` and `live_session.round_id` preserve historical
records. The old application does not understand new-round ballots and should not
be used to continue the same conference. Close the conference before rollback;
never drop the study database as a rollback step.

## Primary references

- https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app
- https://supabase.com/docs/guides/database/connecting-to-postgres
- https://supabase.com/kb/troubleshooting/disabling-prepared-statements-qL8lEL
- https://www.postgresql.org/docs/15/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS
