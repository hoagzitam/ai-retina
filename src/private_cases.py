"""Private, investigator-reviewed case loading. No public image URLs."""

import io
import json
import re
from pathlib import PurePosixPath

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image
from supabase import create_client

from src import config

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024


class CaseDataError(ValueError):
    pass


def _object_path(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 240
        or value.startswith("/")
        or "\\" in value
        or ":" in value
        or "?" in value
        or "#" in value
        or ".." in PurePosixPath(value).parts
    ):
        raise CaseDataError(
            "Use private storage object paths, not URLs or local paths."
        )
    return value


@st.cache_resource(show_spinner=False)
def _storage():
    if not config.STORAGE_ENABLED:
        raise CaseDataError("Private case storage is not configured.")
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY).storage


def _download(path):
    try:
        storage = _storage()
        bucket = storage.get_bucket(config.SUPABASE_STORAGE_BUCKET)
        public = bucket.get("public") if isinstance(bucket, dict) else bucket.public
        if public is not False:
            raise CaseDataError("Case storage bucket must be private.")
        return storage.from_(config.SUPABASE_STORAGE_BUCKET).download(
            _object_path(path)
        )
    except CaseDataError:
        raise
    except Exception:
        raise CaseDataError(
            "Private case asset could not be loaded. Check storage permissions and object paths."
        ) from None


def validate_manifest(document):
    from src.data import _COLUMNS
    from src.ui import DIAGNOSES, MANAGEMENT

    if (
        not isinstance(document, dict)
        or document.get("deidentified_reviewed") is not True
        or document.get("research_use_approved") is not True
    ):
        raise CaseDataError(
            "An investigator must attest de-identification and approval for research use."
        )
    rows = document.get("cases")
    if not isinstance(rows, list) or not rows:
        raise CaseDataError("No approved real cases are available.")
    allowed = set(_COLUMNS) | {"image_paths"}
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != allowed:
            raise CaseDataError(
                "Case metadata must match the approved minimal schema; extra patient fields are rejected."
            )
        case_id = row["case_id"]
        if (
            not isinstance(case_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", case_id)
            or case_id in seen
        ):
            raise CaseDataError(
                "Case IDs must be unique pseudonyms of at most 32 characters."
            )
        seen.add(case_id)
        if row["disease_module"] not in {"nAMD", "PCV", "DME", "RVO"}:
            raise CaseDataError("Unknown disease module.")
        if not isinstance(row["age"], int) or not 18 <= row["age"] <= 110:
            raise CaseDataError("Use approved adult case ages only.")
        if row["sex"] not in {"M", "F", "Other", "Unknown"} or row["eye"] not in {
            "OD",
            "OS",
        }:
            raise CaseDataError("Invalid case demographics.")
        for key in ("expert_diagnosis", "tide_diagnosis"):
            if row[key] not in DIAGNOSES:
                raise CaseDataError("Invalid reference diagnosis.")
        for key in ("expert_management", "tide_management"):
            if row[key] not in MANAGEMENT:
                raise CaseDataError("Invalid reference management.")
        for biomarker in ("irf", "srf", "ped", "shrm", "hrf"):
            for key in (f"tide_{biomarker}", f"{biomarker}_current"):
                if row[key] not in {"Present", "Absent"}:
                    raise CaseDataError("Invalid biomarker reference.")
        for key in ("vignette", "visual_acuity"):
            if not isinstance(row[key], str) or not 0 < len(row[key]) <= (
                800 if key == "vignette" else 24
            ):
                raise CaseDataError("Invalid case narrative or visual acuity.")
        if (
            not isinstance(row["image_paths"], list)
            or not 1 <= len(row["image_paths"]) <= 8
        ):
            raise CaseDataError("Each real case requires one to eight image objects.")
        for path in row["image_paths"]:
            _object_path(path)
    return pd.DataFrame(rows).assign(is_real=True)


@st.cache_data(ttl=60, show_spinner=False)
def private_case_bank():
    raw = _download(config.CASE_MANIFEST_PATH)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise CaseDataError("Case manifest is too large.")
    try:
        document = json.loads(raw)
    except (ValueError, UnicodeError):
        raise CaseDataError("Case manifest must be valid JSON.") from None
    return validate_manifest(document)


def _clean_image(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_IMAGE_BYTES:
        raise CaseDataError("Image is missing or exceeds the supported size.")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if (
                image.format not in {"JPEG", "PNG"}
                or image.width * image.height > 25_000_000
            ):
                raise CaseDataError("Use PNG or JPEG images up to 25 megapixels.")
            image.load()
            # Rebuild pixels to remove EXIF, comments and file metadata.
            clean = Image.fromarray(np.array(image.convert("RGB")))
            output = io.BytesIO()
            clean.save(output, format="PNG")
            return output.getvalue()
    except CaseDataError:
        raise
    except Exception:
        raise CaseDataError(
            "Case image is unavailable or invalid; no synthetic image will be substituted."
        ) from None


@st.cache_data(ttl=60, max_entries=64, show_spinner=False)
def case_images(case_id, image_paths):
    return [_clean_image(_download(path)) for path in image_paths]
