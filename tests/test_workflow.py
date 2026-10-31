"""All case metadata and image bytes here are artificial QA fixtures."""

import io
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pytest
from PIL import Image, PngImagePlugin
from sqlalchemy import create_engine, select, text
from sqlalchemy.pool import NullPool
from streamlit.testing.v1 import AppTest

from src import config, data, db, private_cases


@pytest.fixture(scope="session")
def postgres_server(tmp_path_factory):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip(
            "Embedded PostgreSQL needs an unprivileged test runner; production Supabase is not accessed by these tests."
        )
    pgserver = pytest.importorskip("pgserver")
    server = pgserver.get_server(
        tmp_path_factory.mktemp("postgres") / "data", cleanup_mode="delete"
    )
    yield server
    server.cleanup()


@pytest.fixture(params=["sqlite", "postgresql"])
def database(request, tmp_path, monkeypatch):
    if request.param == "sqlite":
        engine = create_engine(
            f"sqlite:///{tmp_path}/test.db",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
    else:
        server = request.getfixturevalue("postgres_server")
        engine = create_engine(
            config._normalize_db_url(server.get_uri()),
            poolclass=NullPool,
            connect_args={"prepare_threshold": None, "connect_timeout": 10},
        )
        db.metadata.drop_all(engine)
    monkeypatch.setattr(db, "_engine", lambda: engine)
    db.init_db.clear()
    db._initialize_schema()
    yield engine
    db.init_db.clear()
    db.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def approved_fixture(monkeypatch):
    row = dict(zip(data._COLUMNS, data._RAW_CASES[0]))
    row["case_id"] = "QA001"
    row["image_paths"] = ["qa/artificial.png"]
    manifest = {
        "deidentified_reviewed": True,
        "research_use_approved": True,
        "cases": [row],
    }
    case_bank = private_cases.validate_manifest(manifest)
    output = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "QA metadata must be removed")
    Image.new("RGB", (64, 48), (40, 50, 60)).save(
        output, format="PNG", pnginfo=metadata
    )
    raw = output.getvalue()
    monkeypatch.setattr(private_cases, "_download", lambda _: raw)
    private_cases.case_images.clear()
    data.case_bank.clear()
    monkeypatch.setattr(data, "case_bank", lambda: case_bank)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "qa-admin-secret-unique")
    monkeypatch.setattr(config, "APP_ACCESS_PASSWORD", "")
    monkeypatch.setattr(config, "APP_ENV", "development")
    return manifest, case_bank


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception


def test_moderator_two_participants_workflow(database, approved_fixture):
    moderator = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "streamlit_app.py"
    ).run()
    moderator.sidebar.radio[0].set_value("Investigator / Admin").run()
    moderator.text_input[0].set_value("qa-admin-secret-unique").run()
    assert not moderator.exception
    click(moderator, "1 · Open case")
    assert db.get_live_session()["active_case_id"] == "QA001"
    assert not db.get_live_session()["voting_open"]
    click(moderator, "2 · Open voting")
    first = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "streamlit_app.py"
    ).run()
    first.sidebar.radio[0].set_value("Live Conference").run()
    assert not first.exception
    assert not any("Answer key" in item.value for item in first.markdown)
    first.radio[0].set_value("nAMD")
    first.radio[1].set_value("Anti-VEGF injection")
    click(first, "Submit / update live vote")
    assert any("vote is recorded" in item.value for item in first.success)
    assert db.live_vote_count("QA001") == 1
    # Updating one's ballot remains one participant.
    first.radio[1].set_value("Observe")
    click(first, "Submit / update live vote")
    assert db.live_vote_count("QA001") == 1
    second = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "streamlit_app.py"
    ).run()
    second.sidebar.radio[0].set_value("Live Conference").run()
    second.radio[0].set_value("PCV")
    second.radio[1].set_value("Anti-VEGF injection")
    click(second, "Submit / update live vote")
    moderator.run()
    assert any(
        metric.label == "Votes received" and metric.value == "2"
        for metric in moderator.metric
    )
    round_id = db.get_live_session()["round_id"]
    click(moderator, "3 · Close voting")
    with pytest.raises(ValueError, match="Voting is closed"):
        db.save_live_vote("late", "QA001", "nAMD", "Observe", 3, round_id)
    click(moderator, "4 · Reveal results")
    first.run()
    assert not first.exception
    assert db.live_results("QA001").votes.sum() == 2
    assert any(
        metric.label == "Votes" and metric.value == "2" for metric in first.metric
    )
    click(moderator, "1 · Open case")
    assert db.live_vote_count("QA001") == 0
    with database.connect() as conn:
        assert len(conn.execute(select(db.live_round_votes)).all()) == 2


def test_live_resume_retains_vote(database, approved_fixture):
    db.update_live(active_case_id="QA001")
    db.update_live(voting_open=True)
    code = db.create_live_participant()
    db.save_live_vote(
        code, "QA001", "nAMD", "Observe", 3, db.get_live_session()["round_id"]
    )
    app = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "streamlit_app.py"
    ).run()
    app.sidebar.radio[0].set_value("Live Conference").run()
    app.text_input[0].set_value(code)
    click(app, "Resume live participant")
    assert app.session_state["live_code"] == code
    assert any("vote is recorded" in item.value for item in app.success)
    assert db.live_vote_count("QA001") == 1


def test_concurrent_initialization_and_error_propagation(database):
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: db._initialize_schema(), range(16)))
    with database.connect() as conn:
        assert len(conn.execute(select(db.live_session)).all()) == 1
    with database.begin() as conn:
        conn.execute(text("DROP TABLE live_session"))
        conn.execute(text("CREATE TABLE live_session (id INTEGER PRIMARY KEY)"))
    with pytest.raises(Exception):
        db._initialize_schema()


def test_live_races_and_stale_round(database):
    with pytest.raises(ValueError):
        db.update_live(voting_open=True)
    db.update_live(active_case_id="QA001")
    db.update_live(voting_open=True)
    old_round = db.get_live_session()["round_id"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda _: db.save_live_vote(
                    "same-code", "QA001", "nAMD", "Observe", 4, old_round
                ),
                range(20),
            )
        )
    assert db.live_vote_count("QA001") == 1
    assert db.live_results("QA001").empty
    with pytest.raises(ValueError, match="Close voting"):
        db.update_live(reveal_results=True)
    db.update_live(voting_open=False)
    db.update_live(reveal_results=True)
    with pytest.raises(ValueError):
        db.update_live(voting_open=True)
    db.update_live(active_case_id="QA001")
    db.update_live(voting_open=True)
    with pytest.raises(ValueError, match="moderator changed"):
        db.save_live_vote("same-code", "QA001", "nAMD", "Observe", 4, old_round)
    assert db.live_vote_count("QA001") == 0


def test_research_submit_resume_and_duplicate(database, approved_fixture):
    cases = approved_fixture[1]
    uid = db.create_user("research", 20, "Retina specialist", "Daily")
    db.assign_cases(uid, cases, "ALL")
    assert db.resume_research(uid)
    row, sequence = db.next_research_case(uid, cases)
    assert sequence == 1
    biomarkers = {key.upper(): "Absent" for key in db.BIOMARKER_COLS}

    def submit(_):
        try:
            db.save_research(uid, row, "nAMD", "Observe", 4, biomarkers, 10)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(submit, range(2))) == 1
    assert db.next_research_case(uid, cases)[0] is None
    assert len(db.frames()["research"]) == 1


def test_legacy_migration_preserves_votes(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/legacy.db")
    monkeypatch.setattr(db, "_engine", lambda: engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE live_session (id INTEGER PRIMARY KEY, active_case_id VARCHAR(32), voting_open BOOLEAN NOT NULL, reveal_results BOOLEAN NOT NULL, updated_at DATETIME)"
            )
        )
        conn.execute(text("INSERT INTO live_session VALUES (1, 'C001', 1, 0, NULL)"))
    db._initialize_schema()
    assert db.get_live_session()["round_id"] is None
    assert not db.get_live_session()["voting_open"]
    engine.dispose()


def test_private_assets_validation_and_scrubbing(approved_fixture, monkeypatch):
    manifest, cases = approved_fixture
    images = private_cases.case_images("QA001", tuple(cases.iloc[0].image_paths))
    assert Image.open(io.BytesIO(images[0])).info == {}
    manifest["cases"][0]["patient_name"] = "Forbidden extra field"
    with pytest.raises(private_cases.CaseDataError, match="extra patient fields"):
        private_cases.validate_manifest(manifest)
    for path in ["https://example.com/image.png", "../patient.png", "/tmp/image.png"]:
        with pytest.raises(private_cases.CaseDataError):
            private_cases._object_path(path)
    monkeypatch.setattr(private_cases, "_download", lambda _: b"not an image")
    private_cases.case_images.clear()
    with pytest.raises(private_cases.CaseDataError):
        private_cases.case_images("QA001", ("missing.png",))


def test_failed_image_does_not_open_case(database, approved_fixture, monkeypatch):
    monkeypatch.setattr(private_cases, "_download", lambda _: b"invalid image")
    private_cases.case_images.clear()
    moderator = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "streamlit_app.py"
    ).run()
    moderator.sidebar.radio[0].set_value("Investigator / Admin").run()
    moderator.text_input[0].set_value("qa-admin-secret-unique").run()
    click(moderator, "1 · Open case")
    assert db.get_live_session()["active_case_id"] is None
    assert moderator.error


def test_production_fails_closed(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "DATABASE_URL", "sqlite:///local.db")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "changeme")
    monkeypatch.setattr(config, "APP_ACCESS_PASSWORD", "")
    monkeypatch.setattr(config, "STORAGE_ENABLED", False)
    errors = config.configuration_errors()
    assert any("SQLite" in error for error in errors)
    assert any("ADMIN_PASSWORD" in error for error in errors)
    assert any("APP_ACCESS_PASSWORD" in error for error in errors)
    assert any("CASE_MANIFEST_PATH" in error for error in errors)
    app = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "streamlit_app.py"
    ).run()
    assert not app.exception
    assert app.error
    assert not app.sidebar.radio


def test_private_gate_precedes_case_or_db_access(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "development")
    monkeypatch.setattr(config, "APP_ACCESS_PASSWORD", "qa-access-secret-unique")
    monkeypatch.setattr(
        db,
        "init_db",
        lambda: pytest.fail("Access gate must run before database access"),
    )
    app = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "streamlit_app.py"
    ).run()
    assert app.title[0].value == "AI-RETINA · Private access"
    app.text_input[0].set_value("incorrect")
    click(app, "Enter private workspace")
    assert app.error[0].value == "Access denied."


def test_private_gate_authorized(database, approved_fixture, monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_PASSWORD", "qa-access-secret-unique")
    app = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "streamlit_app.py"
    ).run()
    app.text_input[0].set_value("qa-access-secret-unique")
    click(app, "Enter private workspace")
    assert app.session_state["access_granted"] is True
    assert app.sidebar.radio[0].label == "Platform mode"


def test_public_bucket_is_rejected(monkeypatch):
    class PublicStorage:
        def get_bucket(self, name):
            return {"public": True}

        def from_(self, name):
            pytest.fail(
                "No asset bytes may be downloaded from a public clinical bucket"
            )

    monkeypatch.setattr(private_cases, "_storage", lambda: PublicStorage())
    with pytest.raises(private_cases.CaseDataError, match="must be private"):
        private_cases._download("approved/image.png")
