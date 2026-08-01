"""
analysis.py
The actual "detector" logic. Everything here operates on a pandas
DataFrame of one product's price_history rows, ordered by date.

Four signals feed a single 0-100 Trust Score:

1. MRP inflation      - is today's MRP a statistical outlier vs. the
                         product's own MRP history? (z-score + IQR)
                         Classic dark pattern: quietly raise the "before"
                         price right before a "sale" so the discount % lies.
2. Shrinkflation       - is price-per-gram/ml trending up over time even
                         if the sticker price looks flat or lower?
3. Review-count spikes - sudden jumps in review count far outside the
                         rolling norm (possible review bombing/buying).
4. Discount mismatch   - advertised discount (vs current MRP) vs the
                         product's real historical discount (vs its own
                         median price) — flags "fake 70% off" claims.
"""

import numpy as np
import pandas as pd


def _iqr_outlier(series: pd.Series, value: float) -> bool:
    if len(series) < 4:
        return False
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return False
    return value > q3 + 1.5 * iqr or value < q1 - 1.5 * iqr


def _zscore(series: pd.Series, value: float) -> float:
    if len(series) < 4 or series.std(ddof=0) == 0:
        return 0.0
    return (value - series.mean()) / series.std(ddof=0)


def detect_mrp_inflation(history: pd.DataFrame) -> dict:
    """Flags whether the most recent MRP looks artificially inflated
    compared to the product's own MRP history."""
    if history.empty or history["mrp"].dropna().empty:
        return {"flagged": False, "z_score": 0.0, "reason": "insufficient data"}

    hist_mrp = history["mrp"].dropna()
    latest_mrp = hist_mrp.iloc[-1]
    baseline = hist_mrp.iloc[:-1] if len(hist_mrp) > 1 else hist_mrp

    z = _zscore(baseline, latest_mrp)
    is_outlier = _iqr_outlier(baseline, latest_mrp) or abs(z) > 2.0

    return {
        "flagged": bool(is_outlier and z > 0),  # only care about inflation, not drops
        "z_score": round(float(z), 2),
        "latest_mrp": float(latest_mrp),
        "historical_median_mrp": float(baseline.median()) if len(baseline) else None,
    }


def detect_shrinkflation(history: pd.DataFrame, lookback_days: int = 90) -> dict:
    """Tracks price-per-unit-weight trend. Flags if price-per-gram/ml has
    risen meaningfully even if weight or price alone look unremarkable."""
    df = history.dropna(subset=["price", "weight_value"]).copy()
    if len(df) < 2:
        return {"flagged": False, "pct_change": 0.0, "reason": "insufficient data"}

    df = df.tail(lookback_days)
    df["price_per_unit"] = df["price"] / df["weight_value"]

    first, last = df["price_per_unit"].iloc[0], df["price_per_unit"].iloc[-1]
    if first == 0:
        return {"flagged": False, "pct_change": 0.0}

    pct_change = (last - first) / first * 100
    weight_shrank = df["weight_value"].iloc[-1] < df["weight_value"].iloc[0]

    # Only call it "shrinkflation" if the pack actually got smaller — a price-per-unit
    # rise driven purely by a price hike (weight unchanged) is a price increase, not
    # shrinkflation, and shouldn't be conflated with it.
    flagged = bool(pct_change > 8.0 and weight_shrank)

    return {
        "flagged": flagged,
        "pct_change": round(float(pct_change), 2),
        "weight_shrank": bool(weight_shrank),
        "first_price_per_unit": round(float(first), 4),
        "last_price_per_unit": round(float(last), 4),
    }


def detect_review_spike(history: pd.DataFrame, recent_window: int = 10) -> dict:
    """Flags sudden jumps in review count far outside the rolling trend —
    a signal of possible review manipulation. Checks every day in the last
    `recent_window` days against the longer-run baseline that precedes it,
    not just the single most recent day, since a spike a few days ago is
    just as meaningful as one that happened yesterday."""
    df = history.dropna(subset=["review_count"]).copy()
    if len(df) < recent_window + 5:
        return {"flagged": False, "z_score": 0.0, "reason": "insufficient data"}

    df["daily_diff"] = df["review_count"].diff()
    diffs = df["daily_diff"].dropna().reset_index(drop=True)
    if len(diffs) < recent_window + 3:
        return {"flagged": False, "z_score": 0.0}

    baseline = diffs.iloc[: -recent_window]
    recent = diffs.iloc[-recent_window:]

    best_z, best_diff = 0.0, 0
    for diff_val in recent:
        z = _zscore(baseline, diff_val)
        if z > best_z:
            best_z, best_diff = z, diff_val

    return {
        "flagged": bool(best_z > 2.5),
        "z_score": round(float(best_z), 2),
        "latest_daily_increase": int(best_diff),
    }


def detect_discount_mismatch(history: pd.DataFrame) -> dict:
    """Compares the discount the listing currently advertises (vs its
    current MRP) against the product's real long-run discount (vs its own
    median historical price)."""
    df = history.dropna(subset=["price", "mrp"])
    if df.empty:
        return {"flagged": False, "advertised_discount_pct": 0.0,
                "real_discount_pct": 0.0}

    latest = df.iloc[-1]
    advertised_discount = (latest["mrp"] - latest["price"]) / latest["mrp"] * 100

    historical_median_price = df["price"].median()
    real_baseline = df["mrp"].median()  # best available proxy for "true" price level
    real_discount = (real_baseline - historical_median_price) / real_baseline * 100 \
        if real_baseline else 0.0

    gap = advertised_discount - real_discount

    return {
        "flagged": bool(gap > 15.0),  # advertised discount overstates real one by 15pp+
        "advertised_discount_pct": round(float(advertised_discount), 1),
        "real_discount_pct": round(float(real_discount), 1),
        "gap_pct_points": round(float(gap), 1),
    }


def compute_trust_score(history: pd.DataFrame) -> dict:
    """Combines all four signals into one 0-100 Trust Score.
    100 = no deceptive signals detected. Lower = more red flags."""
    mrp_result = detect_mrp_inflation(history)
    shrink_result = detect_shrinkflation(history)
    review_result = detect_review_spike(history)
    discount_result = detect_discount_mismatch(history)

    score = 100.0

    if mrp_result["flagged"]:
        # scale penalty by how extreme the z-score is
        score -= min(35, 15 + abs(mrp_result["z_score"]) * 5)

    if shrink_result["flagged"]:
        score -= min(30, shrink_result["pct_change"] * 1.5)

    if review_result["flagged"]:
        score -= min(15, 5 + review_result["z_score"] * 2)

    if discount_result["flagged"]:
        score -= min(25, discount_result["gap_pct_points"])

    score = max(0.0, min(100.0, round(score, 1)))

    return {
        "trust_score": score,
        "mrp_inflation": mrp_result,
        "shrinkflation": shrink_result,
        "review_spike": review_result,
        "discount_mismatch": discount_result,
    }


def score_to_label(score: float) -> str:
    if score >= 80:
        return "Trustworthy"
    if score >= 55:
        return "Caution"
    if score >= 30:
        return "Likely Deceptive"
    return "Highly Deceptive"
