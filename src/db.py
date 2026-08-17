"""
Persistence layer for AI-RETINA.

Works against Postgres (Supabase, via DATABASE_URL) or, for local
development with no DATABASE_URL configured, a local SQLite file. All
public functions used by streamlit_app.py live here:

    init_db, create_user, assign_cases, next_research_case, save_research,
    new_code, get_live_session, update_live, get_live_vote, save_live_vote,
    live_vote_count, save_learning, frames
"""
import json
import secrets as pysecrets
import string
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    insert,
    select,
    text,
    update,
)

from src.config import DATABASE_URL

BIOMARKER_COLS = ["irf", "srf", "ped", "shrm", "hrf"]

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("user_id", String(32), primary_key=True),
    Column("role", String(16), nullable=False),  # 'research' | 'learning'
    Column("years_experience", Integer, nullable=False, default=0),
    Column("specialty", String(64), nullable=False, default=""),
    Column("frequency", String(64), nullable=False, default=""),
    Column("study", String(32), nullable=True),
    Column("assigned_cases", Text, nullable=True),  # JSON list of case_ids
    Column("progress", Integer, nullable=False, default=0),
    Column("created_at", DateTime, nullable=False),
)

research_responses = Table(
    "research_responses",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(32), nullable=False),
    Column("case_id", String(32), nullable=False),
    Column("seq", Integer, nullable=False, default=0),
    Column("diagnosis", String(64), nullable=False),
    Column("management", String(64), nullable=False),
    Column("confidence", Integer, nullable=False),
    *[Column(c, String(16), nullable=True) for c in BIOMARKER_COLS],
    Column("duration_sec", Integer, nullable=True),
    Column("created_at", DateTime, nullable=False),
)

learning_responses = Table(
    "learning_responses",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(32), nullable=False),
    Column("case_id", String(32), nullable=False),
    Column("stage_num", Integer, nullable=False, default=1),
    Column("stage", String(16), nullable=False),  # 'human' | 'ai' | 'expert'
    Column("diagnosis", String(64), nullable=True),
    Column("management", String(64), nullable=True),
    Column("confidence", Integer, nullable=True),
    *[Column(c, String(16), nullable=True) for c in BIOMARKER_COLS],
    Column("created_at", DateTime, nullable=False),
)

live_session = Table(
    "live_session",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("active_case_id", String(32), nullable=True),
    Column("voting_open", Boolean, nullable=False, default=False),
    Column("reveal_results", Boolean, nullable=False, default=False),
    Column("updated_at", DateTime, nullable=True),
)

live_votes = Table(
    "live_votes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("code", String(32), nullable=False),
    Column("case_id", String(32), nullable=False),
    Column("diagnosis", String(64), nullable=False),
    Column("management", String(64), nullable=False),
    Column("confidence", Integer, nullable=False),
    Column("created_at", DateTime, nullable=False),
    UniqueConstraint("code", "case_id", name="uq_live_vote_code_case"),
)


@st.cache_resource(show_spinner=False)
def _engine():
    connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    return create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)


def _now():
    return datetime.now(timezone.utc)


# Arbitrary constant used as a Postgres advisory lock key, just to serialize
# schema creation if two processes ever call init_db() at nearly the same
# moment (e.g. a Streamlit Cloud redeploy overlap).
_ADVISORY_LOCK_KEY = 785421


@st.cache_resource(show_spinner=False)
def init_db():
    """Create tables if needed, and ensure the singleton live_session row exists.

    Cached with st.cache_resource so this body runs at most once per running
    app process -- Streamlit reruns the whole script on every interaction
    and every new browser session, so without this, many concurrent first
    page-loads could all race to CREATE TABLE at once and collide. The
    Postgres advisory lock is a second layer of protection across process
    boundaries; any duplicate-object error is swallowed since it only means
    another process already finished the same setup.
    """
    eng = _engine()
    is_pg = eng.dialect.name == "postgresql"
    conn = eng.connect()
    try:
        if is_pg:
            conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})
        try:
            metadata.create_all(conn)
            conn.commit()
        except Exception:
            conn.rollback()  # tables already exist (created by a concurrent process) -- fine
        finally:
            if is_pg:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _ADVISORY_LOCK_KEY})
                conn.commit()
    finally:
        conn.close()

    # Make sure the singleton live_session row (id=1) always exists.
    with eng.begin() as conn2:
        row = conn2.execute(select(live_session).where(live_session.c.id == 1)).mappings().first()
        if row is None:
            try:
                conn2.execute(
                    insert(live_session).values(
                        id=1, active_case_id=None, voting_open=False, reveal_results=False, updated_at=_now()
                    )
                )
            except Exception:
                pass  # another process already inserted it -- fine


def new_code(prefix: str = "USR") -> str:
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(pysecrets.choice(alphabet) for _ in range(6))
    return f"{prefix}-{suffix}"


# --- Users / research / learning ---------------------------------------

def create_user(role: str, years: int, specialty: str, frequency: str) -> str:
    uid = new_code("RES" if role == "research" else "LRN")
    with _engine().begin() as conn:
        conn.execute(
            insert(users).values(
                user_id=uid,
                role=role,
                years_experience=int(years),
                specialty=specialty,
                frequency=frequency,
                study=None,
                assigned_cases=None,
                progress=0,
                created_at=_now(),
            )
        )
    return uid


def assign_cases(uid: str, cases_df: pd.DataFrame, study: str):
    if study == "RANDOM10":
        pool = cases_df.sample(n=min(10, len(cases_df)), random_state=None)
    elif study == "ALL":
        pool = cases_df
    else:
        pool = cases_df[cases_df.disease_module == study]
        if pool.empty:  # fall back so a bad/unknown filter never breaks the flow
            pool = cases_df
    case_ids = pool["case_id"].sample(frac=1).tolist()  # shuffle
    with _engine().begin() as conn:
        conn.execute(
            update(users)
            .where(users.c.user_id == uid)
            .values(study=study, assigned_cases=json.dumps(case_ids), progress=0)
        )


def next_research_case(uid: str, cases_df: pd.DataFrame):
    with _engine().begin() as conn:
        row = conn.execute(select(users).where(users.c.user_id == uid)).mappings().first()
    if row is None or not row["assigned_cases"]:
        return None, 0
    case_ids = json.loads(row["assigned_cases"])
    progress = row["progress"]
    if progress >= len(case_ids):
        return None, progress
    case_id = case_ids[progress]
    match = cases_df[cases_df.case_id == case_id]
    if match.empty:
        return None, progress
    return match.iloc[0], progress + 1


def save_research(uid, row, diag, mgmt, cf, bio, duration_sec):
    with _engine().begin() as conn:
        urow = conn.execute(select(users).where(users.c.user_id == uid)).mappings().first()
        seq = (urow["progress"] if urow else 0) + 1
        values = dict(
            user_id=uid,
            case_id=row.case_id,
            seq=seq,
            diagnosis=diag,
            management=mgmt,
            confidence=int(cf),
            duration_sec=int(duration_sec) if duration_sec is not None else None,
            created_at=_now(),
        )
        for b in BIOMARKER_COLS:
            values[b] = bio.get(b.upper(), bio.get(b))
        conn.execute(insert(research_responses).values(**values))
        conn.execute(update(users).where(users.c.user_id == uid).values(progress=seq))


def save_learning(uid, row, stage_num, stage, diag, mgmt, cf, bio):
    with _engine().begin() as conn:
        values = dict(
            user_id=uid,
            case_id=row.case_id,
            stage_num=int(stage_num),
            stage=stage,
            diagnosis=diag,
            management=mgmt,
            confidence=int(cf) if cf is not None else None,
            created_at=_now(),
        )
        for b in BIOMARKER_COLS:
            values[b] = bio.get(b.upper(), bio.get(b)) if bio else None
        conn.execute(insert(learning_responses).values(**values))


# --- Live conference -----------------------------------------------------

def get_live_session() -> dict:
    with _engine().begin() as conn:
        row = conn.execute(select(live_session).where(live_session.c.id == 1)).mappings().first()
    if row is None:
        return {"active_case_id": None, "voting_open": False, "reveal_results": False}
    return dict(row)


def update_live(**kwargs):
    kwargs["updated_at"] = _now()
    with _engine().begin() as conn:
        conn.execute(update(live_session).where(live_session.c.id == 1).values(**kwargs))


def get_live_vote(code: str, case_id: str):
    with _engine().begin() as conn:
        row = (
            conn.execute(
                select(live_votes).where(live_votes.c.code == code, live_votes.c.case_id == case_id)
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None


def save_live_vote(code: str, case_id: str, diag: str, mgmt: str, cf: int):
    with _engine().begin() as conn:
        existing = (
            conn.execute(
                select(live_votes).where(live_votes.c.code == code, live_votes.c.case_id == case_id)
            )
            .mappings()
            .first()
        )
        if existing:
            conn.execute(
                update(live_votes)
                .where(live_votes.c.code == code, live_votes.c.case_id == case_id)
                .values(diagnosis=diag, management=mgmt, confidence=int(cf), created_at=_now())
            )
        else:
            conn.execute(
                insert(live_votes).values(
                    code=code,
                    case_id=case_id,
                    diagnosis=diag,
                    management=mgmt,
                    confidence=int(cf),
                    created_at=_now(),
                )
            )


def live_vote_count(case_id: str) -> int:
    with _engine().begin() as conn:
        rows = conn.execute(select(live_votes.c.code).where(live_votes.c.case_id == case_id)).all()
    return len({r[0] for r in rows})


# --- Bulk read for analytics / admin -------------------------------------

def frames() -> dict:
    eng = _engine()
    with eng.begin() as conn:
        u = pd.read_sql(select(users), conn)
        r = pd.read_sql(select(research_responses), conn)
        l = pd.read_sql(select(learning_responses), conn)
        v = pd.read_sql(select(live_votes), conn)
    return {"users": u, "research": r, "learning": l, "live": v}
