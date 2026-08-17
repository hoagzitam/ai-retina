# AI-RETINA Human–AI Platform V7 Online

One GitHub repository, one Streamlit app, four modes: Research, Live Conference, Self-Learning, Investigator/Admin.

For online multi-user use, configure a remote PostgreSQL `DATABASE_URL`. Streamlit Community Cloud deploys from GitHub and stores secrets separately from the repository.

## Project layout
```
streamlit_app.py        # entry point, all 4 modes
src/
  config.py              # secrets/env loading
  db.py                  # SQLAlchemy models + all persistence functions
  data.py                # case bank (synthetic demo cases by default)
  ui.py                  # constants (DIAGNOSES/BIOMARKERS/MANAGEMENT/CONF), CSS, case rendering
  analytics.py           # Fleiss' kappa, disagreement table, human-vs-AI safety classes
```

## Demo data
The 15 cases shipped in `src/data.py` are **entirely synthetic** — the "OCT scans" are
procedurally generated placeholder images, not real patient imagery. This keeps the
repo runnable and privacy-safe out of the box. Before running an actual study, replace
`case_bank()` with a loader over your real, de-identified dataset (e.g. read case
metadata from a private CSV/table and images from Supabase Storage).

## Local
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m streamlit run streamlit_app.py
```

## Production secrets
```toml
DATABASE_URL = "postgresql://..."
ADMIN_PASSWORD = "..."
APP_ENV = "production"
```

Optional private Supabase Storage:
```toml
SUPABASE_URL = "..."
SUPABASE_SERVICE_KEY = "sb_secret_..."
SUPABASE_STORAGE_BUCKET = "oct-cases"
SIGNED_URL_TTL = 300
```

Deploy `streamlit_app.py` on Streamlit Community Cloud.
