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
    inspect,
    func,
    delete,
    insert,
    select,
    text,
    update,
)

from sqlalchemy.pool import NullPool

from src.config import DATABASE_URL
from contextlib import contextmanager
from uuid import uuid4
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

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
    Column("round_id", String(32), nullable=True),
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


# Keep historical live_votes unchanged. New rounds preserve repeated-case ballots.
live_participants = Table(
    "live_participants",
    metadata,
    Column("code", String(32), primary_key=True),
    Column("created_at", DateTime, nullable=False),
)


live_rounds = Table(
    "live_rounds",
    metadata,
    Column("round_id", String(32), primary_key=True),
    Column("case_id", String(32), nullable=False),
    Column("created_at", DateTime, nullable=False),
)
live_round_votes = Table(
    "live_round_votes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("round_id", String(32), nullable=False),
    Column("code", String(32), nullable=False),
    Column("case_id", String(32), nullable=False),
    Column("diagnosis", String(64), nullable=False),
    Column("management", String(64), nullable=False),
    Column("confidence", Integer, nullable=False),
    Column("created_at", DateTime, nullable=False),
    UniqueConstraint("round_id", "code", name="uq_live_round_code"),
)


@st.cache_resource(show_spinner=False)
def _engine():
    if DATABASE_URL.startswith("sqlite"):
        return create_engine(
            DATABASE_URL, pool_pre_ping=True, connect_args={"check_same_thread": False}
        )
    # Supabase's Transaction pooler (port 6543) already pools connections at
    # the PgBouncer/Supavisor layer, and rotates the physical backend
    # connection under each logical one. Layering SQLAlchemy's own
    # connection pool on top of that leads to stale server-side state
    # (prepared statements created against one backend connection, then
    # reused/looked up against a different one) -- surfacing as
    # DuplicatePreparedStatement / InvalidSqlStatementName errors. NullPool
    # opens a fresh DB connection for every checkout and closes it
    # afterwards, so there is nothing left to go stale between requests.
    # prepare_threshold=None additionally stops psycopg3 from creating any
    # server-side prepared statements at all, as a second layer of safety.
    return create_engine(
        DATABASE_URL,
        poolclass=NullPool,
        connect_args={"prepare_threshold": None, "connect_timeout": 10},
    )


def _now():
    return datetime.now(timezone.utc)


# Arbitrary constant used as a Postgres advisory lock key, just to serialize
# schema creation if two processes ever call init_db() at nearly the same
# moment (e.g. a Streamlit Cloud redeploy overlap).
_ADVISORY_LOCK_KEY = 785421


def _initialize_schema():
    """One transaction owns DDL, additive migration and singleton creation.

    Transaction-scoped locks stay on the same backend through Supavisor.
    Unexpected database/permission errors propagate; they are never success.
    """
    eng = _engine()
    with _write_connection() as conn:
        if eng.dialect.name == "postgresql":
            conn.execute(
                text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY}
            )
        metadata.create_all(conn)
        if "round_id" not in {
            c["name"] for c in inspect(conn).get_columns("live_session")
        }:
            conn.execute(
                text("ALTER TABLE live_session ADD COLUMN round_id VARCHAR(32)")
            )
        stmt = (
            _insert_for(conn, live_session)
            .values(
                id=1,
                active_case_id=None,
                round_id=None,
                voting_open=False,
                reveal_results=False,
                updated_at=_now(),
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        conn.execute(stmt)
        # A legacy open case is closed during migration, without deleting votes.
        conn.execute(
            update(live_session)
            .where(live_session.c.round_id.is_(None))
            .values(voting_open=False, reveal_results=False)
        )


@st.cache_resource(show_spinner=False)
def init_db():
    _initialize_schema()


@contextmanager
def _write_connection():
    eng = _engine()
    if eng.dialect.name == "sqlite":
        with eng.connect() as conn:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    else:
        with eng.begin() as conn:
            yield conn


def _insert_for(conn, table):
    return (pg_insert if conn.dialect.name == "postgresql" else sqlite_insert)(table)


def new_code(prefix: str = "USR") -> str:
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(pysecrets.choice(alphabet) for _ in range(12))
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
        if pool.empty:
            raise ValueError("No cases are available for that study.")
    case_ids = pool["case_id"].sample(frac=1).tolist()
    with _write_connection() as conn:
        user = (
            conn.execute(select(users).where(users.c.user_id == uid).with_for_update())
            .mappings()
            .first()
        )
        if not user or user["assigned_cases"]:
            raise ValueError("Participant is missing or already assigned.")
        conn.execute(
            update(users)
            .where(users.c.user_id == uid)
            .values(study=study, assigned_cases=json.dumps(case_ids), progress=0)
        )


def next_research_case(uid: str, cases_df: pd.DataFrame):
    with _engine().begin() as conn:
        row = (
            conn.execute(select(users).where(users.c.user_id == uid)).mappings().first()
        )
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


def resume_research(uid):
    with _engine().connect() as conn:
        row = (
            conn.execute(
                select(users).where(users.c.user_id == uid, users.c.role == "research")
            )
            .mappings()
            .first()
        )
    return bool(row and row["assigned_cases"])


def save_research(uid, row, diag, mgmt, cf, bio, duration_sec):
    _validate_answer(diag, mgmt, cf)
    with _write_connection() as conn:
        urow = (
            conn.execute(select(users).where(users.c.user_id == uid).with_for_update())
            .mappings()
            .first()
        )
        if not urow or urow["role"] != "research" or not urow["assigned_cases"]:
            raise ValueError("Research participant is not assigned.")
        case_ids = json.loads(urow["assigned_cases"])
        progress = urow["progress"]
        if progress >= len(case_ids) or case_ids[progress] != row.case_id:
            raise ValueError(
                "This case was already submitted or the assignment changed."
            )
        values = dict(
            user_id=uid,
            case_id=row.case_id,
            seq=progress + 1,
            diagnosis=diag,
            management=mgmt,
            confidence=int(cf),
            duration_sec=(
                max(0, int(duration_sec)) if duration_sec is not None else None
            ),
            created_at=_now(),
        )
        for biomarker in BIOMARKER_COLS:
            value = bio.get(biomarker.upper(), bio.get(biomarker))
            if value not in {"Absent", "Present"}:
                raise ValueError("Complete all biomarkers.")
            values[biomarker] = value
        conn.execute(insert(research_responses).values(**values))
        conn.execute(
            update(users).where(users.c.user_id == uid).values(progress=progress + 1)
        )


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
        row = (
            conn.execute(select(live_session).where(live_session.c.id == 1))
            .mappings()
            .first()
        )
    if row is None:
        return {"active_case_id": None, "voting_open": False, "reveal_results": False}
    return dict(row)


def update_live(**kwargs):
    allowed = {"active_case_id", "voting_open", "reveal_results"}
    if not kwargs or set(kwargs) - allowed:
        raise ValueError("Invalid moderator action.")
    with _write_connection() as conn:
        current = (
            conn.execute(
                select(live_session).where(live_session.c.id == 1).with_for_update()
            )
            .mappings()
            .one()
        )
        if "active_case_id" in kwargs:
            case_id = kwargs["active_case_id"]
            if not case_id or len(case_id) > 32:
                raise ValueError("Select a valid case first.")
            round_id = uuid4().hex
            conn.execute(
                insert(live_rounds).values(
                    round_id=round_id, case_id=case_id, created_at=_now()
                )
            )
            kwargs.update(round_id=round_id, voting_open=False, reveal_results=False)
        elif not current["active_case_id"] or not current["round_id"]:
            raise ValueError("Open a case before changing voting status.")
        if kwargs.get("voting_open") and current["reveal_results"]:
            raise ValueError("Open a new round before accepting votes after reveal.")
        if kwargs.get("reveal_results") and current["voting_open"]:
            raise ValueError("Close voting before revealing results.")
        kwargs["updated_at"] = _now()
        conn.execute(
            update(live_session).where(live_session.c.id == 1).values(**kwargs)
        )


def create_live_participant():
    code = new_code("LIVE")
    with _engine().begin() as conn:
        conn.execute(insert(live_participants).values(code=code, created_at=_now()))
    return code


def resume_live_participant(code):
    with _engine().connect() as conn:
        return (
            conn.execute(
                select(live_participants.c.code).where(live_participants.c.code == code)
            ).scalar_one_or_none()
            is not None
        )


def get_live_vote(code, case_id):
    with _engine().connect() as conn:
        round_id = conn.execute(
            select(live_session.c.round_id).where(live_session.c.id == 1)
        ).scalar()
        row = (
            conn.execute(
                select(live_round_votes).where(
                    live_round_votes.c.code == code,
                    live_round_votes.c.case_id == case_id,
                    live_round_votes.c.round_id == round_id,
                )
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None


def _validate_answer(diag, mgmt, cf):
    from src.ui import DIAGNOSES, MANAGEMENT, CONF

    if diag not in DIAGNOSES or mgmt not in MANAGEMENT or cf not in CONF:
        raise ValueError("Complete diagnosis, management and confidence.")


def save_live_vote(code, case_id, diag, mgmt, cf, expected_round_id):
    _validate_answer(diag, mgmt, cf)
    if not code or len(code) > 32:
        raise ValueError("Participant code is invalid.")
    with _write_connection() as conn:
        current = (
            conn.execute(
                select(live_session).where(live_session.c.id == 1).with_for_update()
            )
            .mappings()
            .one()
        )
        if (
            not current["voting_open"]
            or current["reveal_results"]
            or current["active_case_id"] != case_id
            or not expected_round_id
            or current["round_id"] != expected_round_id
        ):
            raise ValueError(
                "Voting is closed or the moderator changed the case. Refresh the page."
            )
        values = dict(
            code=code,
            case_id=case_id,
            round_id=expected_round_id,
            diagnosis=diag,
            management=mgmt,
            confidence=int(cf),
            created_at=_now(),
        )
        stmt = _insert_for(conn, live_round_votes).values(**values)
        conn.execute(
            stmt.on_conflict_do_update(
                index_elements=["round_id", "code"],
                set_={
                    key: value
                    for key, value in values.items()
                    if key not in {"round_id", "code"}
                },
            )
        )


def live_vote_count(case_id):
    with _engine().connect() as conn:
        return conn.execute(
            select(func.count())
            .select_from(live_round_votes)
            .where(
                live_round_votes.c.case_id == case_id,
                live_round_votes.c.round_id
                == select(live_session.c.round_id)
                .where(live_session.c.id == 1)
                .scalar_subquery(),
            )
        ).scalar_one()


def live_results(case_id):
    """Aggregate only the current revealed round; never export participant data."""
    with _engine().begin() as conn:
        current = (
            conn.execute(select(live_session).where(live_session.c.id == 1))
            .mappings()
            .one()
        )
        if not current["reveal_results"] or current["active_case_id"] != case_id:
            return pd.DataFrame(columns=["management", "votes"])
        return pd.read_sql(
            select(live_round_votes.c.management, func.count().label("votes"))
            .where(
                live_round_votes.c.case_id == case_id,
                live_round_votes.c.round_id == current["round_id"],
            )
            .group_by(live_round_votes.c.management),
            conn,
        )


# --- Bulk read for analytics / admin -------------------------------------


def frames() -> dict:
    eng = _engine()
    with eng.begin() as conn:
        u = pd.read_sql(select(users), conn)
        r = pd.read_sql(select(research_responses), conn)
        l = pd.read_sql(select(learning_responses), conn)
        legacy = pd.read_sql(select(live_votes), conn)
        current = pd.read_sql(select(live_round_votes), conn)
        v = (
            pd.concat([legacy, current], ignore_index=True)
            if not legacy.empty
            else current
        )
    return {"users": u, "research": r, "learning": l, "live": v}
