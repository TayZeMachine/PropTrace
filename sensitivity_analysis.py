"""
PropTech- CPSI Weight Sensitivity Analysis Engine
===================================================

Purpose
-------
Systematically evaluates the mathematical robustness of the Composite Property 
Suitability Index (CPSI) framework under user weight adjustments across 5 angles:
1. One-at-a-time (OAT) sensitivity sweeps
2. Global Monte Carlo simulation (full simplex)
3. Local Monte Carlo simulation (realistic slider range)
4. Threshold-proximity analysis (+/- 0.05 margin around 0.40 and 0.75 RAG cut-offs)
5. Named strategy scenario comparison
"""

import argparse
import random
import sys
from collections import namedtuple
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Headless mode for clean chart exports
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RAG_ORDER = ["GREEN", "AMBER", "RED"]
RAG_COLORS = {"GREEN": "#10b981", "AMBER": "#f59e0b", "RED": "#ef4444"}

Property = namedtuple(
    "Property",
    ["uprn", "epc_rating", "dominant_building_era", "tenure",
     "has_recorded_covenant", "in_flood_zone_3"],
)


# ---------------------------------------------------------------------------
# 1. Loading the real scoring function — guarantees formula parity
# ---------------------------------------------------------------------------
def load_real_scoring_function():
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from app import calculate_cpsi_score
        print("[ok] Imported calculate_cpsi_score directly from app.py.")
        return calculate_cpsi_score
    except Exception as exc:
        print(f"[warn] Could not import from app.py ({exc}). Using local fallback mirror.")
        return _fallback_calculate_cpsi_score


def _fallback_calculate_cpsi_score(prop, legal_weight=0.4, env_weight=0.3, econ_weight=0.3):
    if getattr(prop, "has_recorded_covenant", False):
        return 1.00, "RED", "CRITICAL OVERRIDE: Active restrictive covenant detected on Land Registry title."
    if getattr(prop, "in_flood_zone_3", False):
        return 1.00, "RED", "CRITICAL OVERRIDE: Property intersects EA Flood Zone 3 (High Risk)."

    epc_map = {"A": 0.0, "B": 0.1, "C": 0.3, "D": 0.5, "E": 0.7, "F": 0.9, "G": 1.0}
    env_sub_score = epc_map.get((prop.epc_rating or "").upper(), 0.5)

    era_code = (prop.dominant_building_era or "").upper().strip()
    era_score = 0.2
    if era_code == "A":
        era_score = 1.00
    elif era_code in ["B", "C", "D"]:
        era_score = 0.75
    elif era_code in ["E", "F", "G"]:
        era_score = 0.50
    elif era_code in ["H", "I", "J"]:
        era_score = 0.25
    elif era_code in ["K", "L"]:
        era_score = 0.00
    econ_sub_score = min(era_score, 1.0)

    legal_sub_score = 0.4 if prop.tenure == "LH" else 0.1

    composite_risk = (legal_weight * legal_sub_score) + (env_weight * env_sub_score) + (econ_weight * econ_sub_score)
    composite_risk = round(max(0.0, min(composite_risk, 1.0)), 3)

    if composite_risk >= 0.75:
        rag = "RED"
    elif composite_risk >= 0.40:
        rag = "AMBER"
    else:
        rag = "GREEN"
    return composite_risk, rag, "Index metrics derived via standard compensatory WLC matrix models."


# ---------------------------------------------------------------------------
# 2. Data Loading Engine
# ---------------------------------------------------------------------------
def load_from_db(limit=2000):
    from app import app, db, BirminghamProperty

    with app.app_context():
        rows = db.session.query(
            BirminghamProperty.uprn,
            BirminghamProperty.epc_rating,
            BirminghamProperty.dominant_building_era,
            BirminghamProperty.tenure,
            BirminghamProperty.has_recorded_covenant,
            BirminghamProperty.in_flood_zone_3,
        ).limit(limit).all()

    properties = [Property(*row) for row in rows]
    print(f"[ok] Loaded {len(properties)} properties from the database.")
    return properties


def generate_synthetic(n=1500, seed=42):
    rng = random.Random(seed)
    epc_choices = list("ABCDEFG")
    epc_weights = [0.03, 0.10, 0.22, 0.30, 0.20, 0.10, 0.05]
    era_choices = list("ABCDEFGHIJKL")
    era_weights = [0.04, 0.06, 0.05, 0.05, 0.06, 0.08, 0.14, 0.12, 0.11, 0.10, 0.10, 0.09]

    properties = []
    for i in range(n):
        epc = rng.choices(epc_choices, weights=epc_weights, k=1)[0]
        era = rng.choices(era_choices, weights=era_weights, k=1)[0]
        tenure = rng.choices(["FH", "LH"], weights=[0.72, 0.28], k=1)[0]
        covenant = rng.choices([True, False, None], weights=[0.06, 0.64, 0.30], k=1)[0]
        flood = rng.choices([True, False, None], weights=[0.04, 0.71, 0.25], k=1)[0]
        properties.append(Property(f"SYNTH{i:06d}", epc, era, tenure, covenant, flood))

    print(f"[demo] Generated {n} synthetic properties (seed={seed}).")
    return properties


# ---------------------------------------------------------------------------
# 3. Calculation Mechanics
# ---------------------------------------------------------------------------
def score_dataset(score_fn, properties, legal_w, env_w, econ_w):
    records = []
    for p in properties:
        score, rag, _ = score_fn(p, legal_weight=legal_w, env_weight=env_w, econ_weight=econ_w)
        records.append({"uprn": p.uprn, "score": score, "rag": rag})
    return pd.DataFrame.from_records(records)


def rag_distribution_pct(df):
    counts = df["rag"].value_counts(normalize=True) * 100
    return {k: counts.get(k, 0.0) for k in RAG_ORDER}


# ---------------------------------------------------------------------------
# 4. One-at-a-Time (OAT) Sweeps
# ---------------------------------------------------------------------------
def oat_sensitivity(score_fn, properties, baseline=(0.4, 0.3, 0.3), steps=21):
    names = ["legal_weight", "env_weight", "econ_weight"]
    results = {name: [] for name in names}
    sweep_values = np.linspace(0.0, 1.0, steps)

    for idx, name in enumerate(names):
        other_idx = [j for j in range(3) if j != idx]
        other_ratio = baseline[other_idx[0]] / (baseline[other_idx[0]] + baseline[other_idx[1]] + 1e-9)

        for v in sweep_values:
            remaining = 1.0 - v
            w = [0.0, 0.0, 0.0]
            w[idx] = v
            w[other_idx[0]] = remaining * other_ratio
            w[other_idx[1]] = remaining * (1 - other_ratio)

            df = score_dataset(score_fn, properties, *w)
            dist = rag_distribution_pct(df)
            results[name].append({"weight_value": v, **dist, "mean_score": df["score"].mean()})

    return {name: pd.DataFrame(rows) for name, rows in results.items()}


def plot_oat(oat_results, out_dir):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)
    titles = {"legal_weight": "Legal weight varied", "env_weight": "Environmental weight varied", "econ_weight": "Economic weight varied"}

    for ax, (name, df) in zip(axes, oat_results.items()):
        ax.stackplot(
            df["weight_value"],
            [df[c] for c in RAG_ORDER],
            colors=[RAG_COLORS[c] for c in RAG_ORDER],
            labels=RAG_ORDER,
            alpha=0.9,
        )
        ax.set_title(titles[name], fontsize=11)
        ax.set_xlabel(name.replace("_", " "))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 100)

    axes[0].set_ylabel("% of properties in each RAG class")
    axes[0].legend(loc="upper left", fontsize=9, framealpha=0.9)
    fig.suptitle("One-at-a-time sensitivity: RAG classification mix vs each weight", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_dir / "oat_sensitivity.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 5. Global & Local Monte Carlo Volatility Engine
# ---------------------------------------------------------------------------
def monte_carlo_sensitivity(score_fn, properties, n_draws=500, mode="global", baseline=(0.4, 0.3, 0.3), seed=1):
    rng = np.random.default_rng(seed)

    if mode == "global":
        alpha = np.array([1.0, 1.0, 1.0])
    elif mode == "local":
        concentration = 20.0
        alpha = np.array(baseline) * concentration
    else:
        raise ValueError("mode must be 'global' or 'local'")

    weight_draws = rng.dirichlet(alpha, size=n_draws)

    class_counts = {p.uprn: {"GREEN": 0, "AMBER": 0, "RED": 0} for p in properties}
    score_sums = {p.uprn: 0.0 for p in properties}

    for legal_w, env_w, econ_w in weight_draws:
        for p in properties:
            score, rag, _ = score_fn(p, legal_weight=legal_w, env_weight=env_w, econ_weight=econ_w)
            class_counts[p.uprn][rag] += 1
            score_sums[p.uprn] += score

    records = []
    for p in properties:
        counts = class_counts[p.uprn]
        total = sum(counts.values())
        max_share = max(counts.values()) / total
        records.append({
            "uprn": p.uprn,
            "green_pct": 100 * counts["GREEN"] / total,
            "amber_pct": 100 * counts["AMBER"] / total,
            "red_pct": 100 * counts["RED"] / total,
            "mean_score": score_sums[p.uprn] / total,
            "volatility": round(1 - max_share, 4),
        })

    df = pd.DataFrame.from_records(records).sort_values("volatility", ascending=False).reset_index(drop=True)
    return df


def plot_volatility(global_df, local_df, out_dir):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    for ax, df, title in zip(axes, [global_df, local_df], ["Global (any weighting)", "Local (realistic slider range)"]):
        ax.hist(df["volatility"], bins=20, color="#3b82f6", edgecolor="white")
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Volatility (0 = always same RAG class, higher = unstable)")
        ax.set_xlim(0, max(0.7, df["volatility"].max() * 1.05))
    axes[0].set_ylabel("Number of properties")
    fig.suptitle("Per-property classification volatility under weight uncertainty", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_dir / "volatility_histogram.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 6. Threshold-Proximity Analysis
# ---------------------------------------------------------------------------
def threshold_proximity(score_fn, properties, baseline=(0.4, 0.3, 0.3), eps=0.05):
    df = score_dataset(score_fn, properties, *baseline)
    near_amber_cut = ((df["score"] - 0.40).abs() <= eps).sum()
    near_red_cut = ((df["score"] - 0.75).abs() <= eps).sum()
    total = len(df)
    summary = {
        "total_properties": total,
        "within_eps_of_amber_cutoff_0.40": int(near_amber_cut),
        "pct_within_eps_of_amber_cutoff": round(100 * near_amber_cut / total, 2),
        "within_eps_of_red_cutoff_0.75": int(near_red_cut),
        "pct_within_eps_of_red_cutoff": round(100 * near_red_cut / total, 2),
        "epsilon": eps,
    }
    return df, summary


def plot_threshold_proximity(df, eps, out_dir):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(df["score"], bins=40, color="#64748b", edgecolor="white")
    for cutoff, label in [(0.40, "AMBER cutoff (0.40)"), (0.75, "RED cutoff (0.75)")]:
        ax.axvline(cutoff, color="#0f172a", linestyle="--", linewidth=1.5)
        ax.axvspan(cutoff - eps, cutoff + eps, color="#f59e0b", alpha=0.15)
        ax.text(cutoff, ax.get_ylim()[1] * 0.95, label, rotation=90, va="top", ha="right", fontsize=8)
    ax.set_xlabel("Composite CPSI score (default weights)")
    ax.set_ylabel("Number of properties")
    ax.set_title("Score distribution vs RAG thresholds (shaded = within +/-%.2f of a cutoff)" % eps)
    fig.tight_layout()
    fig.savefig(out_dir / "threshold_proximity.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 7. Named Strategy Scenarios
# ---------------------------------------------------------------------------
SCENARIOS = {
    "Default (0.4/0.3/0.3)": (0.4, 0.3, 0.3),
    "Legal-First": (0.6, 0.2, 0.2),
    "Environment-First": (0.2, 0.6, 0.2),
    "Economic-First": (0.2, 0.2, 0.6),
    "Equal-Weight": (1/3, 1/3, 1/3),
}


def scenario_comparison(score_fn, properties):
    baseline_df = score_dataset(score_fn, properties, *SCENARIOS["Default (0.4/0.3/0.3)"])
    baseline_labels = dict(zip(baseline_df["uprn"], baseline_df["rag"]))

    rows = []
    for name, weights in SCENARIOS.items():
        df = score_dataset(score_fn, properties, *weights)
        dist = rag_distribution_pct(df)
        changed = sum(1 for u, r in zip(df["uprn"], df["rag"]) if baseline_labels[u] != r)
        rows.append({
            "scenario": name,
            "legal_weight": weights[0], "env_weight": weights[1], "econ_weight": weights[2],
            **dist,
            "mean_score": df["score"].mean(),
            "pct_changed_vs_default": round(100 * changed / len(df), 2),
        })
    return pd.DataFrame(rows)


def plot_scenarios(scenario_df, out_dir):
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(scenario_df))
    bottom = np.zeros(len(scenario_df))
    for rag in RAG_ORDER:
        ax.bar(x, scenario_df[rag], bottom=bottom, label=rag, color=RAG_COLORS[rag])
        bottom += scenario_df[rag].values
    ax.set_xticks(x)
    ax.set_xticklabels(scenario_df["scenario"], rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("% of properties in each RAG class")
    ax.set_title("RAG classification mix under named weight scenarios")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "scenario_comparison.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 8. Main Execution Entry Point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="CPSI weight sensitivity analysis")
    parser.add_argument("--source", choices=["db", "demo"], default="demo",
                        help="'db' pulls real data via app.py's models; 'demo' generates synthetic data")
    parser.add_argument("--limit", type=int, default=2000, help="max properties to pull from the DB")
    parser.add_argument("--n", type=int, default=1500, help="synthetic dataset size (--source demo only)")
    parser.add_argument("--draws", type=int, default=500, help="Monte Carlo draws per mode")
    parser.add_argument("--eps", type=float, default=0.05, help="threshold-proximity margin")
    parser.add_argument("--out-dir", type=str, default="./sensitivity_output")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    score_fn = load_real_scoring_function()
    properties = load_from_db(args.limit) if args.source == "db" else generate_synthetic(args.n)

    print("\n[1/5] Running One-at-a-time (OAT) sensitivity...")
    oat_results = oat_sensitivity(score_fn, properties)
    plot_oat(oat_results, out_dir)

    print(f"[2/5] Running Global Monte Carlo sensitivity ({args.draws} draws)...")
    global_df = monte_carlo_sensitivity(score_fn, properties, n_draws=args.draws, mode="global")

    print(f"[3/5] Running Local Monte Carlo sensitivity ({args.draws} draws)...")
    local_df = monte_carlo_sensitivity(score_fn, properties, n_draws=args.draws, mode="local")
    plot_volatility(global_df, local_df, out_dir)

    combined_volatility = global_df[["uprn", "mean_score", "volatility"]].rename(columns={"volatility": "volatility_global"})
    combined_volatility["volatility_local"] = local_df.set_index("uprn").loc[combined_volatility["uprn"], "volatility"].values
    combined_volatility = combined_volatility.sort_values("volatility_global", ascending=False)
    combined_volatility.to_csv(out_dir / "volatility_scores.csv", index=False)

    print("[4/5] Running Threshold-proximity analysis...")
    thresh_df, thresh_summary = threshold_proximity(score_fn, properties, eps=args.eps)
    plot_threshold_proximity(thresh_df, args.eps, out_dir)

    print("[5/5] Running Named-scenario comparison...")
    scenario_df = scenario_comparison(score_fn, properties)
    scenario_df.to_csv(out_dir / "scenario_summary.csv", index=False)
    plot_scenarios(scenario_df, out_dir)

    print("\n======================================================================")
    print("SENSITIVITY ANALYSIS COMPLETE")
    print("======================================================================")
    print(f"Generated graphics and CSV tables in: {out_dir.resolve()}")


if __name__ == "__main__":
    main()