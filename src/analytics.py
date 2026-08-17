"""
Analytics for AI-RETINA: inter-rater agreement, case-level disagreement,
and human-vs-AI safety classification for the Investigator/Admin tabs.
"""
import pandas as pd


def fleiss_kappa(R: pd.DataFrame) -> float:
    """Fleiss' kappa for diagnostic agreement across research responses.

    Uses the `diagnosis` column, grouping raters by case_id. Cases with
    fewer than 2 responses are excluded (kappa is undefined for n < 2).
    """
    if R.empty or "diagnosis" not in R.columns:
        return 0.0

    categories = sorted(R["diagnosis"].dropna().unique().tolist())
    if not categories:
        return 0.0

    table = R.pivot_table(index="case_id", columns="diagnosis", values="user_id", aggfunc="count", fill_value=0)
    table = table.reindex(columns=categories, fill_value=0)

    n_per_case = table.sum(axis=1)
    table = table[n_per_case >= 2]
    n_per_case = n_per_case[n_per_case >= 2]
    if table.empty:
        return 0.0

    n_ij = table.values.astype(float)
    n_i = n_per_case.values.astype(float)

    p_i = ((n_ij * (n_ij - 1)).sum(axis=1)) / (n_i * (n_i - 1))
    p_bar = p_i.mean()

    p_j = n_ij.sum(axis=0) / n_ij.sum()
    p_e = float((p_j ** 2).sum())

    if p_e >= 1.0:
        return 1.0
    return float((p_bar - p_e) / (1 - p_e))


def disagreement_table(R: pd.DataFrame) -> pd.DataFrame:
    """Rank cases by how much raters disagreed on diagnosis."""
    cols = ["case_id", "n_responses", "n_diagnoses", "top_diagnosis", "top_share", "disagreement"]
    if R.empty:
        return pd.DataFrame(columns=cols)

    rows = []
    for case_id, g in R.groupby("case_id"):
        vc = g["diagnosis"].value_counts()
        top_diag = vc.index[0]
        top_share = float(vc.iloc[0]) / len(g)
        rows.append(
            dict(
                case_id=case_id,
                n_responses=len(g),
                n_diagnoses=int(g["diagnosis"].nunique()),
                top_diagnosis=top_diag,
                top_share=round(top_share, 3),
                disagreement=round(1 - top_share, 3),
            )
        )
    return pd.DataFrame(rows, columns=cols).sort_values("disagreement", ascending=False).reset_index(drop=True)


def human_ai_safety(R: pd.DataFrame, CASES: pd.DataFrame) -> pd.DataFrame:
    """Classify each research response into a human-vs-AI safety bucket.

    - Concordant correct: human and AI both matched the expert management.
    - Human override needed: human was right, AI was wrong (human is the
      safety net -- shows why keeping a human in the loop matters).
    - AI rescue opportunity: human was wrong, AI was right (AI could have
      caught the human's error if surfaced at the point of decision).
    - Silent failure: Human + AI wrong: both missed the expert management
      -- the most dangerous, hardest-to-catch category.
    """
    if R.empty:
        return pd.DataFrame(columns=list(R.columns) + ["expert_management", "tide_management", "safety_class"])

    joined = R.merge(CASES[["case_id", "expert_management", "tide_management"]], on="case_id", how="left")
    human_correct = joined["management"] == joined["expert_management"]
    ai_correct = joined["tide_management"] == joined["expert_management"]

    def classify(hc, ac):
        if hc and ac:
            return "Concordant correct"
        if hc and not ac:
            return "Human override needed"
        if not hc and ac:
            return "AI rescue opportunity"
        return "Silent failure: Human + AI wrong"

    joined["safety_class"] = [classify(hc, ac) for hc, ac in zip(human_correct, ai_correct)]
    return joined
