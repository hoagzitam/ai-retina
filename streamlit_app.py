from datetime import datetime, timezone
import streamlit as st
import pandas as pd
from src.config import (
    ADMIN_PASSWORD,
    APP_ENV,
    APP_ACCESS_PASSWORD,
    configuration_errors,
    LEARNING_ENABLED,
)
import hmac
from src.private_cases import CaseDataError, case_images
from src.db import *
from src.data import case_bank
from src.ui import *
from src.analytics import *

st.set_page_config(
    page_title="AI-RETINA Human–AI Platform", page_icon="👁️", layout="wide"
)
errors = configuration_errors()
if errors:
    st.error("Deployment configuration is incomplete. Contact the investigator.")
    for error in errors:
        st.caption(error)
    st.stop()
if APP_ACCESS_PASSWORD and not st.session_state.get("access_granted"):
    st.title("AI-RETINA · Private access")
    with st.form("private_access"):
        password = st.text_input(
            "Participant access password", type="password", key="access_password"
        )
        enter = st.form_submit_button("Enter private workspace", type="primary")
    if enter:
        if hmac.compare_digest(password.encode(), APP_ACCESS_PASSWORD.encode()):
            st.session_state.access_granted = True
            del st.session_state["access_password"]
            st.rerun()
        else:
            st.error("Access denied.")
    st.stop()
try:
    init_db()
    CASES = case_bank()
except CaseDataError as error:
    st.error(str(error))
    st.stop()
except Exception:
    st.error(
        "The private research service is unavailable. Ask the investigator to check database and case storage configuration."
    )
    st.stop()
inject_css()
if APP_ENV != "production":
    st.warning(
        "Development validation only · synthetic cases may be present · not a clinical study deployment."
    )
st.title("AI-RETINA Human–AI Learning & Decision Platform")
st.caption(f"Online edition · Research · Live · Learning · Admin · {APP_ENV}")
modes = ["Research Study", "Live Conference"]
if LEARNING_ENABLED:
    modes.append("Self-Learning")
modes.append("Investigator / Admin")
mode = st.sidebar.radio("Platform mode", modes)
if mode == "Research Study":
    st.header("Research Study")
    if "research_uid" not in st.session_state:
        with st.expander("Resume with your saved research code"):
            with st.form("resume_research"):
                resume_code = st.text_input("Research code", max_chars=32)
                resume = st.form_submit_button("Resume research")
            if resume:
                if resume_research(resume_code.strip().upper()):
                    st.session_state.research_uid = resume_code.strip().upper()
                    st.session_state.research_started = datetime.now(timezone.utc)
                    st.rerun()
                else:
                    st.error("Research code was not found.")
        with st.form("research_profile"):
            years = st.number_input("Years in ophthalmology", 0, 60, 5)
            spec = st.selectbox(
                "Clinical profile",
                [
                    "Retina specialist",
                    "General ophthalmologist",
                    "Resident/Fellow",
                    "Other",
                ],
            )
            freq = st.selectbox(
                "OCT reading frequency",
                ["Daily", "Several times/week", "Weekly", "Less than weekly"],
            )
            study = st.selectbox(
                "Case set",
                ["RANDOM10", "ALL"]
                + [
                    module
                    for module in ["nAMD", "RVO", "DME", "PCV"]
                    if module in set(CASES.disease_module)
                ],
            )
            consent = st.checkbox(
                "I agree to participate in this research session and the recording of my coded responses."
            )
            go = st.form_submit_button("Start research", type="primary")
        if go and not consent:
            st.error("Agreement is required before starting.")
        if go and consent:
            uid = create_user("research", years, spec, freq)
            assign_cases(uid, CASES, study)
            st.session_state.research_uid = uid
            st.session_state.research_started = datetime.now(timezone.utc)
            st.rerun()
    else:
        uid = st.session_state.research_uid
        row, seq = next_research_case(uid, CASES)
        st.success(f"Anonymous research code: **{uid}**")
        if row is None:
            st.success("Research case set completed.")
        else:
            st.subheader(f"Blinded Retina Case · {seq}")
            show_case(row, True)
            with st.form(f"research_{row.case_id}"):
                diag = st.radio("Diagnosis", DIAGNOSES, index=None, horizontal=True)
                bio = {
                    b: st.radio(
                        b,
                        ["Absent", "Present"],
                        horizontal=True,
                        key=f"r_{row.case_id}_{b}",
                    )
                    for b in BIOMARKERS
                }
                mgmt = st.radio("Management", MANAGEMENT, index=None, horizontal=True)
                cf = st.select_slider("Confidence", CONF, value=3)
                go = st.form_submit_button("Submit & next", type="primary")
            if go:
                if diag is None or mgmt is None:
                    st.error("Complete diagnosis and management.")
                else:
                    sec = (
                        datetime.now(timezone.utc) - st.session_state.research_started
                    ).total_seconds()
                    try:
                        save_research(uid, row, diag, mgmt, cf, bio, sec)
                        st.session_state.research_started = datetime.now(timezone.utc)
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
elif mode == "Live Conference":
    st.header("Live Conference")
    if "live_code" not in st.session_state:
        st.session_state.live_code = create_live_participant()
    with st.expander("Resume with your saved live participant code"):
        with st.form("resume_live"):
            saved_live_code = st.text_input("Saved live participant code", max_chars=32)
            resume_live = st.form_submit_button("Resume live participant")
        if resume_live:
            saved_live_code = saved_live_code.strip().upper()
            if resume_live_participant(saved_live_code):
                st.session_state.live_code = saved_live_code
                st.rerun()
            else:
                st.error("Participant code was not found.")
    code = st.session_state.live_code
    st.success(f"Participant Code: **{code}**")
    st.caption(
        "Save this code to resume after a reload. Use one code for this conference."
    )

    @st.fragment(run_every="2s")
    def live_watcher():
        s = get_live_session()
        sig = (
            s["active_case_id"],
            s.get("round_id"),
            s["voting_open"],
            s["reveal_results"],
        )
        if st.session_state.get("live_sig") != sig:
            st.session_state["live_sig"] = sig
            st.rerun()

    live_watcher()
    sess = get_live_session()
    st.session_state["live_sig"] = (
        sess["active_case_id"],
        sess.get("round_id"),
        sess["voting_open"],
        sess["reveal_results"],
    )
    st.caption(
        "Waiting for moderator"
        if not sess["active_case_id"]
        else (
            "VOTING OPEN"
            if sess["voting_open"]
            else ("RESULTS REVEALED" if sess["reveal_results"] else "CASE OPEN")
        )
    )
    if not sess["active_case_id"]:
        st.info("Moderator has not opened a case yet.")
    else:
        matches = CASES[CASES.case_id == sess["active_case_id"]]
        if matches.empty:
            st.error(
                "The active case is unavailable. The moderator must open an approved case."
            )
            st.stop()
        row = matches.iloc[0]
        show_case(row, True)
        existing = get_live_vote(code, row.case_id)
        if existing:
            st.success("Your vote is recorded for this round.")
        if sess["voting_open"]:
            with st.form(f"live_{sess['round_id']}_{code}"):
                diag = st.radio(
                    "Diagnosis",
                    DIAGNOSES,
                    index=(
                        DIAGNOSES.index(existing["diagnosis"])
                        if existing and existing["diagnosis"] in DIAGNOSES
                        else None
                    ),
                    horizontal=True,
                )
                mgmt = st.radio(
                    "Management",
                    MANAGEMENT,
                    index=(
                        MANAGEMENT.index(existing["management"])
                        if existing and existing["management"] in MANAGEMENT
                        else None
                    ),
                    horizontal=True,
                )
                cf = st.select_slider(
                    "Confidence",
                    CONF,
                    value=(int(existing["confidence"]) if existing else 3),
                )
                go = st.form_submit_button("Submit / update live vote", type="primary")
            if go:
                if diag is None or mgmt is None:
                    st.error("Complete diagnosis and management.")
                else:
                    try:
                        save_live_vote(
                            code, row.case_id, diag, mgmt, cf, sess.get("round_id")
                        )
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
        else:
            st.warning("Voting is closed.")
        if sess["reveal_results"]:
            v = live_results(row.case_id)
            st.subheader("Live results")
            st.metric("Votes", int(v.votes.sum()) if not v.empty else 0)
            if not v.empty:
                st.bar_chart(v.set_index("management")["votes"])
            st.write(
                f"Expert: **{row.expert_management}** · TIDE: **{row.tide_management}**"
            )
elif mode == "Self-Learning":
    st.header("Self-Learning")
    if "learning_uid" not in st.session_state:
        with st.form("learning_profile"):
            years = st.number_input("Years in ophthalmology", 0, 60, 2, key="ly")
            spec = st.selectbox(
                "Level",
                [
                    "Resident/Fellow",
                    "General ophthalmologist",
                    "Retina trainee",
                    "Retina specialist",
                ],
            )
            freq = st.selectbox(
                "OCT reading frequency",
                ["Daily", "Several times/week", "Weekly", "Less than weekly"],
                key="lf",
            )
            go = st.form_submit_button("Start learning", type="primary")
        if go:
            st.session_state.learning_uid = create_user("learning", years, spec, freq)
            st.session_state.learning_index = 0
            st.session_state.learning_stage = "human"
            st.rerun()
    else:
        uid = st.session_state.learning_uid
        i = st.session_state.learning_index % len(CASES)
        row = CASES.iloc[i]
        st.success(f"Learner code: **{uid}**")
        show_case(row, True)
        stage = st.session_state.learning_stage
        if stage == "human":
            with st.form(f"learn_h_{row.case_id}"):
                diag = st.radio("Diagnosis", DIAGNOSES, index=None, horizontal=True)
                bio = {
                    b: st.radio(
                        b,
                        ["Absent", "Present"],
                        horizontal=True,
                        key=f"lh_{row.case_id}_{b}",
                    )
                    for b in BIOMARKERS
                }
                mgmt = st.radio("Management", MANAGEMENT, index=None, horizontal=True)
                cf = st.select_slider("Confidence", CONF, value=3)
                go = st.form_submit_button("Commit human answer", type="primary")
            if go and diag and mgmt:
                save_learning(uid, row, 1, "human", diag, mgmt, cf, bio)
                st.session_state.learning_stage = "ai"
                st.rerun()
        elif stage == "ai":
            st.markdown(
                f"<div class='ai'><b>TIDE AI</b><br>Diagnosis: <b>{row.tide_diagnosis}</b><br>Management: <b>{row.tide_management}</b><br>IRF {row.tide_irf} · SRF {row.tide_srf} · PED {row.tide_ped} · SHRM {row.tide_shrm} · HRF {row.tide_hrf}</div>",
                unsafe_allow_html=True,
            )
            if st.button("Continue to expert reference", type="primary"):
                st.session_state.learning_stage = "expert"
                st.rerun()
        else:
            st.markdown(
                f"<div class='expert'><b>Expert reference</b><br>Diagnosis: <b>{row.expert_diagnosis}</b><br>Management: <b>{row.expert_management}</b><br>IRF {row.irf_current} · SRF {row.srf_current} · PED {row.ped_current} · SHRM {row.shrm_current} · HRF {row.hrf_current}</div>",
                unsafe_allow_html=True,
            )
            if st.button("Next case", type="primary"):
                st.session_state.learning_index += 1
                st.session_state.learning_stage = "human"
                st.rerun()
else:
    st.header("Investigator / Admin")
    pw = st.text_input("Admin password", type="password")
    if not ADMIN_PASSWORD or not hmac.compare_digest(
        pw.encode(), ADMIN_PASSWORD.encode()
    ):
        st.info("Enter admin password.")
        st.stop()
    F = frames()
    U, R, L, V = F["users"], F["research"], F["learning"], F["live"]
    t1, t2, t3, t4 = st.tabs(
        [
            "Research analytics",
            "Human–AI safety",
            "Learning analytics",
            "Live moderator",
        ]
    )
    with t1:
        a, b, c = st.columns(3)
        a.metric("Research doctors", int((U.role == "research").sum()) if len(U) else 0)
        b.metric("Research responses", len(R))
        c.metric("Fleiss κ", "—" if R.empty else f"{fleiss_kappa(R):.3f}")
        if not R.empty:
            st.dataframe(disagreement_table(R), width="stretch", hide_index=True)
            joined = R.merge(
                U[["user_id", "specialty", "years_experience"]],
                on="user_id",
                how="left",
            ).merge(
                CASES[["case_id", "disease_module", "expert_management"]],
                on="case_id",
                how="left",
            )
            joined["expert_concordance"] = joined.management == joined.expert_management
            st.dataframe(
                joined.groupby("specialty")
                .agg(
                    n=("user_id", "nunique"),
                    responses=("case_id", "count"),
                    expert_concordance=("expert_concordance", "mean"),
                    confidence=("confidence", "mean"),
                )
                .reset_index(),
                width="stretch",
                hide_index=True,
            )
            st.download_button(
                "Download research CSV",
                joined.to_csv(index=False).encode("utf-8-sig"),
                "research_analysis.csv",
                "text/csv",
            )
    with t2:
        S = human_ai_safety(R, CASES)
        if S.empty:
            st.info("No research responses.")
        else:
            st.dataframe(
                S.safety_class.value_counts()
                .rename_axis("class")
                .reset_index(name="n"),
                width="stretch",
                hide_index=True,
            )
            x, y, z = st.columns(3)
            x.metric(
                "Silent failure",
                f"{100*(S.safety_class=='Silent failure: Human + AI wrong').mean():.1f}%",
            )
            y.metric(
                "Human override needed",
                f"{100*(S.safety_class=='Human override needed').mean():.1f}%",
            )
            z.metric(
                "AI rescue opportunity",
                f"{100*(S.safety_class=='AI rescue opportunity').mean():.1f}%",
            )
    with t3:
        if L.empty:
            st.info("No learning attempts.")
        else:
            H = L[L.stage == "human"].merge(
                CASES[
                    ["case_id", "expert_management", "expert_diagnosis"]
                    + [b.lower() + "_current" for b in BIOMARKERS]
                ],
                on="case_id",
                how="left",
            )
            H["management_correct"] = H.management == H.expert_management
            H["diagnosis_correct"] = H.diagnosis == H.expert_diagnosis
            for b in BIOMARKERS:
                H[b + "_correct"] = (
                    H[b.lower()].astype(str).str.lower()
                    == H[b.lower() + "_current"].astype(str).str.lower()
                )
            st.dataframe(
                H.groupby("user_id")[
                    ["management_correct", "diagnosis_correct"]
                    + [b + "_correct" for b in BIOMARKERS]
                ]
                .mean()
                .reset_index(),
                width="stretch",
                hide_index=True,
            )
    with t4:
        sess = get_live_session()
        ids = CASES.case_id.tolist()
        sel = st.selectbox(
            "Select case",
            ids,
            index=(
                ids.index(sess["active_case_id"])
                if sess["active_case_id"] in ids
                else 0
            ),
        )
        preview = CASES[CASES.case_id == sel].iloc[0]
        votes_now = (
            live_vote_count(sess["active_case_id"]) if sess["active_case_id"] else 0
        )
        if not sess["active_case_id"]:
            phase = "none"
        elif sess["voting_open"]:
            phase = "voting"
        elif sess["reveal_results"]:
            phase = "revealed"
        elif votes_now > 0:
            phase = "closed_pending_reveal"
        else:
            phase = "case_open"
        phase_label = {
            "none": "Chưa mở ca nào",
            "case_open": "Ca đang mở · sẵn sàng mở bình chọn",
            "voting": "🔴 ĐANG MỞ BÌNH CHỌN",
            "closed_pending_reveal": "Đã đóng bình chọn · sẵn sàng công bố kết quả",
            "revealed": "✅ ĐÃ CÔNG BỐ KẾT QUẢ",
        }
        st.info(f"Trạng thái hiện tại: **{phase_label[phase]}**")
        c1, c2, c3, c4 = st.columns(4)
        if c1.button(
            "1 · Open case", type=("primary" if phase == "none" else "secondary")
        ):
            try:
                if getattr(preview, "is_real", False):
                    case_images(preview.case_id, tuple(preview.image_paths))
                update_live(active_case_id=sel)
                st.rerun()
            except (CaseDataError, ValueError) as error:
                st.error(str(error))
        if c2.button(
            "2 · Open voting",
            type=("primary" if phase == "case_open" else "secondary"),
            disabled=not sess.get("round_id") or sess["reveal_results"],
        ):
            update_live(voting_open=True, reveal_results=False)
            st.rerun()
        if c3.button(
            "3 · Close voting",
            type=("primary" if phase == "voting" else "secondary"),
            disabled=not sess.get("round_id"),
        ):
            update_live(voting_open=False, reveal_results=False)
            st.rerun()
        if c4.button(
            "4 · Reveal results",
            type=("primary" if phase == "closed_pending_reveal" else "secondary"),
            disabled=not sess.get("round_id") or sess["voting_open"],
        ):
            update_live(voting_open=False, reveal_results=True)
            st.rerun()

        @st.fragment(run_every="2s")
        def live_votes_panel():
            s = get_live_session()
            if s["active_case_id"]:
                st.metric("Votes received", live_vote_count(s["active_case_id"]))
                st.caption(
                    f"Active case: {s['active_case_id']} · "
                    + (
                        "VOTING OPEN"
                        if s["voting_open"]
                        else (
                            "RESULTS REVEALED"
                            if s["reveal_results"]
                            else "VOTING CLOSED"
                        )
                    )
                    + " · Auto-refresh 2 s"
                )
            else:
                st.info("No case is open yet.")

        live_votes_panel()
        st.subheader("Case Preview")
        show_case(preview, False)
