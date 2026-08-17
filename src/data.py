"""
Case bank for AI-RETINA.

IMPORTANT: these are entirely SYNTHETIC demo cases (no real patient data or
real OCT images). They exist so the platform is runnable end-to-end out of
the box. Swap `case_bank()` for a loader over your real, de-identified
dataset (e.g. read from Supabase Storage / a private CSV) before running an
actual study.
"""
import pandas as pd
import streamlit as st

# Each row intentionally includes a few AI (TIDE) vs. expert mismatches so
# the "Human-AI safety" admin analytics (silent failures, override-needed,
# rescue opportunities) have something real to show on first run.
_RAW_CASES = [
    # case_id, disease_module, age, sex, eye, va, vignette,
    # expert_diagnosis, expert_management,
    # tide_diagnosis, tide_management,
    # tide_irf, tide_srf, tide_ped, tide_shrm, tide_hrf,
    # irf_current, srf_current, ped_current, shrm_current, hrf_current
    ("C001", "nAMD", 76, "F", "OD", "20/80", "New central distortion, 2 weeks.",
     "nAMD", "Anti-VEGF injection", "nAMD", "Anti-VEGF injection",
     "Present", "Present", "Present", "Absent", "Present",
     "Present", "Present", "Present", "Absent", "Present"),
    ("C002", "nAMD", 81, "M", "OS", "20/100", "Known nAMD, 3rd loading dose today.",
     "nAMD", "Anti-VEGF injection", "nAMD", "Anti-VEGF injection",
     "Absent", "Present", "Present", "Absent", "Absent",
     "Absent", "Present", "Present", "Absent", "Absent"),
    ("C003", "nAMD", 69, "F", "OD", "20/40", "Routine nAMD follow-up, dry on last 2 visits.",
     "Dry AMD", "Observe", "Dry AMD", "Observe",
     "Absent", "Absent", "Absent", "Absent", "Absent",
     "Absent", "Absent", "Absent", "Absent", "Absent"),
    ("C004", "nAMD", 74, "M", "OD", "20/200", "Poor response despite 4 injections.",
     "nAMD", "Switch anti-VEGF agent", "nAMD", "Anti-VEGF injection",
     "Present", "Present", "Present", "Present", "Present",
     "Present", "Present", "Present", "Present", "Present"),
    ("C005", "PCV", 65, "M", "OS", "20/60", "Recurrent submacular hemorrhage.",
     "PCV", "Anti-VEGF injection", "nAMD", "Anti-VEGF injection",
     "Absent", "Present", "Present", "Absent", "Present",
     "Absent", "Present", "Present", "Absent", "Present"),
    ("C006", "PCV", 70, "F", "OD", "20/70", "Notched PED on prior imaging.",
     "PCV", "Anti-VEGF injection", "PCV", "Anti-VEGF injection",
     "Absent", "Absent", "Present", "Absent", "Absent",
     "Absent", "Absent", "Present", "Absent", "Absent"),
    ("C007", "PCV", 58, "M", "OD", "20/50", "Asian male, recurrent PED, good VA.",
     "PCV", "Observe", "PCV", "Anti-VEGF injection",
     "Absent", "Absent", "Present", "Absent", "Absent",
     "Absent", "Absent", "Present", "Absent", "Absent"),
    ("C008", "DME", 60, "F", "OS", "20/50", "Type 2 diabetic, HbA1c 8.9%.",
     "DME", "Anti-VEGF injection", "DME", "Anti-VEGF injection",
     "Present", "Present", "Absent", "Absent", "Absent",
     "Present", "Present", "Absent", "Absent", "Absent"),
    ("C009", "DME", 55, "M", "OD", "20/40", "Mild non-proliferative DR, incidental DME.",
     "DME", "Observe", "DME", "Anti-VEGF injection",
     "Present", "Absent", "Absent", "Absent", "Absent",
     "Present", "Absent", "Absent", "Absent", "Absent"),
    ("C010", "DME", 63, "F", "OS", "20/100", "Chronic DME, multiple prior injections.",
     "DME", "Switch anti-VEGF agent", "DME", "Anti-VEGF injection",
     "Present", "Present", "Absent", "Present", "Present",
     "Present", "Present", "Absent", "Present", "Present"),
    ("C011", "DME", 67, "M", "OD", "20/60", "New DME, treatment-naive, good glycemic control.",
     "DME", "Anti-VEGF injection", "DME", "Anti-VEGF injection",
     "Present", "Absent", "Absent", "Absent", "Absent",
     "Present", "Absent", "Absent", "Absent", "Absent"),
    ("C012", "RVO", 72, "F", "OD", "20/80", "Sudden painless vision loss, 1 week, quadrant hemorrhages.",
     "BRVO", "Anti-VEGF injection", "BRVO", "Anti-VEGF injection",
     "Present", "Present", "Absent", "Absent", "Present",
     "Present", "Present", "Absent", "Absent", "Present"),
    ("C013", "RVO", 78, "M", "OS", "20/200", "Sudden painless vision loss, diffuse hemorrhages all quadrants.",
     "CRVO", "Anti-VEGF injection", "BRVO", "Anti-VEGF injection",
     "Present", "Present", "Absent", "Absent", "Present",
     "Present", "Present", "Absent", "Absent", "Present"),
    ("C014", "RVO", 66, "F", "OD", "20/50", "BRVO 6 months ago, macula dry on last visit.",
     "BRVO", "Observe", "BRVO", "Observe",
     "Absent", "Absent", "Absent", "Absent", "Absent",
     "Absent", "Absent", "Absent", "Absent", "Absent"),
    ("C015", "RVO", 74, "M", "OS", "20/100", "CRVO 3 months, persistent macular edema.",
     "CRVO", "Anti-VEGF injection", "CRVO", "Anti-VEGF injection",
     "Present", "Present", "Absent", "Present", "Present",
     "Present", "Present", "Absent", "Present", "Present"),
]

_COLUMNS = [
    "case_id", "disease_module", "age", "sex", "eye", "visual_acuity", "vignette",
    "expert_diagnosis", "expert_management",
    "tide_diagnosis", "tide_management",
    "tide_irf", "tide_srf", "tide_ped", "tide_shrm", "tide_hrf",
    "irf_current", "srf_current", "ped_current", "shrm_current", "hrf_current",
]


@st.cache_data(show_spinner=False)
def case_bank() -> pd.DataFrame:
    df = pd.DataFrame(_RAW_CASES, columns=_COLUMNS)
    df["seed"] = df["case_id"].apply(lambda c: sum(ord(ch) for ch in c))
    return df
