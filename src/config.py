"""
Central configuration for AI-RETINA.

Reads settings from Streamlit secrets first (st.secrets), falling back to
OS environment variables, then to safe local-dev defaults. This lets the
same code run locally (with a .env-style setup or plain env vars) and on
Streamlit Community Cloud (with Advanced settings -> Secrets).
"""
import os

import streamlit as st


def _get(key: str, default=None):
    try:
        # st.secrets raises if no secrets.toml exists at all, so guard it.
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)


def _normalize_db_url(url: str) -> str:
    """Make sure SQLAlchemy uses the psycopg (v3) driver for Postgres.

    Supabase / most providers hand out plain `postgresql://...` URLs, which
    SQLAlchemy resolves to psycopg2 by default. This project ships
    psycopg[binary] (v3) in requirements.txt, so rewrite the scheme to be
    explicit and avoid a missing-driver error at deploy time.
    """
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):  # some providers use the short form
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url


# --- Core settings -----------------------------------------------------
_raw_db_url = _get("DATABASE_URL", "sqlite:///airetina_local.db")
DATABASE_URL = _normalize_db_url(_raw_db_url)

ADMIN_PASSWORD = _get("ADMIN_PASSWORD", "changeme")
APP_ENV = _get("APP_ENV", "development")

# --- Optional: Supabase Storage for real private OCT/fundus images -----
SUPABASE_URL = _get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = _get("SUPABASE_SERVICE_KEY")
SUPABASE_STORAGE_BUCKET = _get("SUPABASE_STORAGE_BUCKET", "oct-cases")
SIGNED_URL_TTL = int(_get("SIGNED_URL_TTL", 300) or 300)

STORAGE_ENABLED = bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)
