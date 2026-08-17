"""
UI building blocks + shared constants for AI-RETINA.

Everything here is imported with `from src.ui import *` in streamlit_app.py,
so DIAGNOSES / BIOMARKERS / MANAGEMENT / CONF live here as the single
source of truth for form options.
"""
import io

import numpy as np
import streamlit as st
from PIL import Image, ImageDraw

DIAGNOSES = ["Dry AMD", "nAMD", "PCV", "DME", "BRVO", "CRVO", "Other"]

BIOMARKERS = ["IRF", "SRF", "PED", "SHRM", "HRF"]

MANAGEMENT = [
    "Observe",
    "Anti-VEGF injection",
    "Switch anti-VEGF agent",
    "Laser (focal / PRP)",
    "Refer / extended workup",
]

CONF = [1, 2, 3, 4, 5]

_BIOMARKER_LABELS = {
    "IRF": "Intraretinal fluid",
    "SRF": "Subretinal fluid",
    "PED": "Pigment epithelial detachment",
    "SHRM": "Subretinal hyperreflective material",
    "HRF": "Hyperreflective foci",
}


def inject_css():
    st.markdown(
        """
        <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        .block-container {padding-top: 2rem; max-width: 1200px;}
        div[data-testid="stForm"] {
            border: 1px solid rgba(120,120,120,0.25);
            border-radius: 12px;
            padding: 1.25rem 1.25rem 0.5rem 1.25rem;
        }
        .case-card {
            border: 1px solid rgba(120,120,120,0.25);
            border-radius: 12px;
            padding: 1rem 1.25rem;
            margin-bottom: 0.75rem;
            background: rgba(120,120,120,0.04);
        }
        .ai, .expert {
            border-radius: 12px;
            padding: 1rem 1.25rem;
            margin: 0.75rem 0;
            line-height: 1.7;
        }
        .ai {
            background: rgba(66, 133, 244, 0.10);
            border: 1px solid rgba(66, 133, 244, 0.35);
        }
        .expert {
            background: rgba(52, 168, 83, 0.10);
            border: 1px solid rgba(52, 168, 83, 0.35);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _synthetic_oct_image(row, width=640, height=360) -> Image.Image:
    """Render a stylised, entirely synthetic OCT B-scan cross-section.

    This is NOT real patient imagery -- it's a deterministic procedural
    drawing (seeded from the case id) so the same case always looks the
    same, with a few visual cues nodded to the case's biomarker flags.
    Swap this out for real (de-identified, consented) OCT frames before
    running an actual study -- see README for the Supabase Storage option.
    """
    seed = int(getattr(row, "seed", 0)) or sum(ord(c) for c in str(row.case_id))
    rng = np.random.default_rng(seed)

    img = Image.new("L", (width, height), color=12)
    draw = ImageDraw.Draw(img)

    # Background speckle typical of OCT noise.
    noise = rng.integers(0, 35, size=(height, width), dtype=np.uint8)
    img = Image.fromarray(np.array(img) + noise, mode="L")
    draw = ImageDraw.Draw(img)

    # Retinal layers as a set of wavy horizontal bands.
    layer_ys = [height * f for f in (0.32, 0.42, 0.50, 0.58, 0.66, 0.74)]
    xs = np.linspace(0, width, 160)
    for li, base_y in enumerate(layer_ys):
        phase = rng.uniform(0, 2 * np.pi)
        amp = rng.uniform(3, 9)
        ys = base_y + amp * np.sin(xs / 55.0 + phase) + rng.normal(0, 1.2, size=xs.shape)
        pts = [(round(x), round(y)) for x, y in zip(xs.tolist(), ys.tolist())]
        shade = 90 + li * 22
        draw.line(pts, fill=min(shade, 235), width=2)

    ped = str(getattr(row, "tide_ped", "Absent")) == "Present" or str(getattr(row, "ped_current", "Absent")) == "Present"
    irf = str(getattr(row, "tide_irf", "Absent")) == "Present" or str(getattr(row, "irf_current", "Absent")) == "Present"
    srf = str(getattr(row, "tide_srf", "Absent")) == "Present" or str(getattr(row, "srf_current", "Absent")) == "Present"
    hrf = str(getattr(row, "tide_hrf", "Absent")) == "Present" or str(getattr(row, "hrf_current", "Absent")) == "Present"
    shrm = str(getattr(row, "tide_shrm", "Absent")) == "Present" or str(getattr(row, "shrm_current", "Absent")) == "Present"

    cx = width * rng.uniform(0.4, 0.6)
    if ped:
        w_, h_ = rng.uniform(70, 110), rng.uniform(18, 30)
        draw.ellipse([cx - w_ / 2, height * 0.62 - h_, cx + w_ / 2, height * 0.62 + h_ * 0.4], fill=170)
    if irf:
        for _ in range(int(rng.integers(2, 4))):
            ox = cx + rng.uniform(-60, 60)
            w_, h_ = rng.uniform(14, 26), rng.uniform(10, 18)
            draw.ellipse([ox - w_ / 2, height * 0.45, ox + w_ / 2, height * 0.45 + h_], fill=25)
    if srf:
        w_, h_ = rng.uniform(60, 100), rng.uniform(10, 16)
        draw.ellipse([cx - w_ / 2, height * 0.56, cx + w_ / 2, height * 0.56 + h_], fill=20)
    if hrf:
        for _ in range(int(rng.integers(6, 12))):
            px = cx + rng.uniform(-90, 90)
            py = height * rng.uniform(0.4, 0.62)
            draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=250)
    if shrm:
        gap_x = cx + rng.uniform(-20, 20)
        draw.rectangle([gap_x - 18, height * 0.58, gap_x + 18, height * 0.63], fill=60)

    draw.text((10, height - 18), "Synthetic demo scan \u2014 not real patient data", fill=180)
    return img.convert("RGB")


def show_case(row, interactive: bool = True):
    """Render a case: synthetic OCT image + vignette, and (only when
    interactive=False, i.e. the admin/moderator preview) the answer key.
    """
    left, right = st.columns([2, 1])
    with left:
        img = _synthetic_oct_image(row)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        st.image(buf.getvalue(), caption=f"Case {row.case_id} \u00b7 {row.disease_module}", width="stretch")
    with right:
        st.markdown(
            f"""
            <div class="case-card">
            <b>Case {row.case_id}</b><br>
            Module: {row.disease_module}<br>
            Age / sex: {row.age} / {row.sex}<br>
            Eye: {row.eye} &middot; VA: {row.visual_acuity}<br><br>
            {row.vignette}
            </div>
            """,
            unsafe_allow_html=True,
        )

    if not interactive:
        st.markdown("**Answer key (hidden from participants)**")
        c1, c2 = st.columns(2)
        with c1:
            st.write(f"Expert diagnosis: **{row.expert_diagnosis}**")
            st.write(f"Expert management: **{row.expert_management}**")
            bios = ", ".join(f"{b}: {getattr(row, b.lower() + '_current')}" for b in BIOMARKERS)
            st.caption(f"Current biomarkers \u2014 {bios}")
        with c2:
            st.write(f"TIDE AI diagnosis: **{row.tide_diagnosis}**")
            st.write(f"TIDE AI management: **{row.tide_management}**")
            bios_ai = ", ".join(f"{b}: {getattr(row, 'tide_' + b.lower())}" for b in BIOMARKERS)
            st.caption(f"AI-read biomarkers \u2014 {bios_ai}")
