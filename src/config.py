"""Server-side settings. Never print credentials or connection strings."""

import os
import streamlit as st
from sqlalchemy.engine import make_url


def _get(key, default=None):
    try:
        if key in st.secrets:
            return st.secrets[key]
    except (FileNotFoundError, KeyError):
        pass
    return os.environ.get(key, default)


def _normalize_db_url(url):
    url = str(url or "").strip()
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


APP_ENV = str(_get("APP_ENV", "development")).lower()
DATABASE_URL = _normalize_db_url(_get("DATABASE_URL", "sqlite:///airetina_local.db"))
ADMIN_PASSWORD = str(_get("ADMIN_PASSWORD", ""))
APP_ACCESS_PASSWORD = str(_get("APP_ACCESS_PASSWORD", ""))
SUPABASE_URL = _get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = _get("SUPABASE_SERVICE_KEY")
SUPABASE_STORAGE_BUCKET = _get("SUPABASE_STORAGE_BUCKET", "oct-cases")
CASE_MANIFEST_PATH = _get("CASE_MANIFEST_PATH", "")
STORAGE_ENABLED = bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)
LEARNING_ENABLED = (
    str(
        _get("LEARNING_ENABLED", "false" if APP_ENV == "production" else "true")
    ).lower()
    == "true"
)


def configuration_errors():
    errors = []
    if CASE_MANIFEST_PATH and APP_ENV != "production":
        errors.append("Set APP_ENV=production before loading private case data.")
    try:
        url = make_url(DATABASE_URL)
    except Exception:
        return ["DATABASE_URL is invalid. Set it in the hosting secret manager."]
    if APP_ENV == "production":
        if url.drivername != "postgresql+psycopg" or not all(
            (url.host, url.username, url.password, url.database)
        ):
            errors.append(
                "Production requires a complete PostgreSQL DATABASE_URL; SQLite is disabled."
            )
        if url.query.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
            errors.append(
                "DATABASE_URL must require TLS with sslmode=require (or certificate verification)."
            )
        for key, value in [
            ("ADMIN_PASSWORD", ADMIN_PASSWORD),
            ("APP_ACCESS_PASSWORD", APP_ACCESS_PASSWORD),
        ]:
            if len(value) < 16 or value.lower().startswith(
                ("changeme", "change-me", "replace")
            ):
                errors.append(
                    f"{key} must be a unique secret of at least 16 characters."
                )
        if ADMIN_PASSWORD and ADMIN_PASSWORD == APP_ACCESS_PASSWORD:
            errors.append("Use different participant access and administrator secrets.")
        if not STORAGE_ENABLED or not CASE_MANIFEST_PATH:
            errors.append(
                "Production requires private Supabase Storage credentials and CASE_MANIFEST_PATH."
            )
        if not str(SUPABASE_URL or "").startswith("https://"):
            errors.append("SUPABASE_URL must use HTTPS.")
    return errors
