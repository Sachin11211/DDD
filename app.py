"""
app.py
Streamlit dashboard for the Discount Deception Detector.

Two views:
  1. Product Report Card - paste/select a product, see its Trust Score
     and the evidence behind it (MRP history, price-per-unit timeline,
     review-count timeline).
  2. Leaderboard - every tracked product ranked by Trust Score, plus a
     per-brand rollup ("most deceptive brands this month").
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from datetime import date

import db
import scraper
from analysis import compute_trust_score, score_to_label

st.set_page_config(page_title="Discount Deception Detector", page_icon="🔍",
                    layout="wide")

db.init_db()

ALERT_THRESHOLD = 55  # Trust Score below this triggers a dashboard banner
MIN_DAYS_FOR_RELIABLE_SCORE = 7


@st.cache_data(ttl=300)
def load_products():
    with db.get_conn() as conn:
        return [dict(r) for r in db.get_all_products(conn)]


@st.cache_data(ttl=300)
def load_history(product_id):
    with db.get_conn() as conn:
        rows = db.get_history(conn, product_id)
    df = pd.DataFrame([dict(r) for r in rows])
    if not df.empty:
        df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df


def compute_all_scores(products: list) -> pd.DataFrame:
    """One pass over every tracked product's Trust Score, reused by the
    alert banner, leaderboard, and comparison view so it's only computed
    once per page load rather than three times."""
    rows = []
    for p in products:
        history = load_history(p["id"])
        if history.empty:
            continue
        result = compute_trust_score(history)
        days_tracked = len(history)
        rows.append({
            "id": p["id"], "Brand": p["brand"], "Product": p["name"],
            "Category": p["category"], "Days Tracked": days_tracked,
            "Trust Score": result["trust_score"],
            "Verdict": score_to_label(result["trust_score"])
                       if days_tracked >= MIN_DAYS_FOR_RELIABLE_SCORE else "Building history",
            "MRP Inflated": "🚩" if result["mrp_inflation"]["flagged"] else "—",
            "Shrinkflation": "🚩" if result["shrinkflation"]["flagged"] else "—",
            "Review Spike": "🚩" if result["review_spike"]["flagged"] else "—",
        })
    return pd.DataFrame(rows)


def render_alert_banner(scores_df: pd.DataFrame):
    """Surfaces any product whose Trust Score has dropped into risky
    territory, but only once it has enough tracked days for that score to
    actually mean something — otherwise a brand-new product would falsely
    trigger an alert on day one."""
    if scores_df.empty:
        return
    reliable = scores_df[scores_df["Days Tracked"] >= MIN_DAYS_FOR_RELIABLE_SCORE]
    risky = reliable[reliable["Trust Score"] < ALERT_THRESHOLD]
    if risky.empty:
        return
    names = ", ".join(f"**{row.Brand} {row.Product}** ({row['Trust Score']})"
                       for _, row in risky.iterrows())
    st.error(f"🚨 **{len(risky)} product(s) flagged below the trust threshold "
             f"({ALERT_THRESHOLD}):** {names}")


def trust_gauge(score: float, label: str):
    color = {"Trustworthy": "#2e7d32", "Caution": "#f9a825",
             "Likely Deceptive": "#ef6c00", "Highly Deceptive": "#c62828"}[label]
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={"text": f"Trust Score — {label}"},
        gauge={"axis": {"range": [0, 100]},
               "bar": {"color": color},
               "steps": [
                   {"range": [0, 30], "color": "#ffebee"},
                   {"range": [30, 55], "color": "#fff3e0"},
                   {"range": [55, 80], "color": "#fffde7"},
                   {"range": [80, 100], "color": "#e8f5e9"},
               ]},
    ))
    fig.update_layout(height=280, margin=dict(l=20, r=20, t=50, b=10))
    return fig


def price_mrp_chart(df: pd.DataFrame):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["snapshot_date"], y=df["mrp"], name="MRP",
                              line=dict(color="#c62828", dash="dot")))
    fig.add_trace(go.Scatter(x=df["snapshot_date"], y=df["price"], name="Selling Price",
                              line=dict(color="#1565c0"), fill="tonexty"))
    fig.update_layout(height=350, margin=dict(l=20, r=20, t=30, b=10),
                       legend=dict(orientation="h", y=1.1))
    return fig


def price_per_unit_chart(df: pd.DataFrame):
    d = df.dropna(subset=["price", "weight_value"]).copy()
    d["price_per_unit"] = d["price"] / d["weight_value"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["snapshot_date"], y=d["price_per_unit"],
                              name="Price per g/ml", line=dict(color="#6a1b9a")))
    fig.add_trace(go.Scatter(x=d["snapshot_date"], y=d["weight_value"],
                              name="Pack weight/volume", yaxis="y2",
                              line=dict(color="#00897b", dash="dash")))
    fig.update_layout(
        height=320, margin=dict(l=20, r=20, t=30, b=10),
        legend=dict(orientation="h", y=1.15),
        yaxis=dict(title="Price per unit"),
        yaxis2=dict(title="Weight/Volume", overlaying="y", side="right"),
    )
    return fig


def review_chart(df: pd.DataFrame):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["snapshot_date"], y=df["review_count"],
                              name="Review count", line=dict(color="#ef6c00")))
    fig.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=10))
    return fig


def render_report_card(product: dict, history: pd.DataFrame):
    result = compute_trust_score(history)
    label = score_to_label(result["trust_score"])
    days_tracked = len(history)

    col1, col2 = st.columns([1, 2])
    with col1:
        st.plotly_chart(trust_gauge(result["trust_score"], label), use_container_width=True)
        st.caption(f"**{product['name']}**  \n{product['brand']} · {product['category']} · "
                   f"sold by {product['seller']}")

    with col2:
        if days_tracked < 7:
            st.info(f"📅 **Building history: day {days_tracked} of ~7+ needed for reliable "
                    f"signals.** This product was recently added — deception patterns "
                    f"(fake discounts, shrinkflation) only show up by comparing a product "
                    f"against its *own* price history over time, so signals below will "
                    f"strengthen daily as more data comes in. This isn't a bug, it's how "
                    f"fraud detection has to work: you can't call something anomalous with "
                    f"nothing to compare it to yet.")
        else:
            st.caption(f"📅 Tracked for {days_tracked} days — signals below are based on "
                       f"this product's full tracked history.")

        d = result["discount_mismatch"]
        st.metric("Advertised discount", f"{d['advertised_discount_pct']}%",
                   help="Based on current listed MRP vs current price")
        st.metric("Estimated real discount", f"{d['real_discount_pct']}%",
                   help="Based on this product's own historical price/MRP baseline")
        if d["flagged"]:
            st.error(f"⚠️ Advertised discount overstates the real discount by "
                      f"~{d['gap_pct_points']} percentage points.")

        st.download_button(
            "⬇️ Download this product's tracked history (CSV)",
            data=history.to_csv(index=False),
            file_name=f"{product['brand'] or 'product'}_{product['id']}_history.csv",
            mime="text/csv",
        )

    st.divider()
    tabs = st.tabs(["💰 Price vs MRP", "📦 Shrinkflation", "⭐ Reviews"])

    with tabs[0]:
        st.plotly_chart(price_mrp_chart(history), use_container_width=True)
        m = result["mrp_inflation"]
        if m.get("reason") == "insufficient data":
            st.info("📅 Not enough tracked days yet to check for MRP inflation.")
        elif m["flagged"]:
            st.warning(f"🚩 MRP inflation detected — current MRP is a statistical "
                       f"outlier vs. this product's own history (z-score {m['z_score']}).")
        else:
            st.success("✅ No MRP inflation pattern detected.")

    with tabs[1]:
        st.plotly_chart(price_per_unit_chart(history), use_container_width=True)
        s = result["shrinkflation"]
        if s.get("reason") == "insufficient data":
            st.info("📅 Not enough tracked days yet to check for shrinkflation.")
        elif s["flagged"]:
            st.warning(f"🚩 Shrinkflation detected — price per gram/ml rose "
                       f"{s['pct_change']}% over the tracked period"
                       + (" while pack size shrank." if s.get("weight_shrank") else "."))
        else:
            st.success("✅ No shrinkflation pattern detected.")

    with tabs[2]:
        st.plotly_chart(review_chart(history), use_container_width=True)
        r = result["review_spike"]
        if r.get("reason") == "insufficient data":
            st.info("📅 Not enough tracked days yet to check for review spikes.")
        elif r["flagged"]:
            st.warning(f"🚩 Unusual review-count spike detected "
                       f"(z-score {r['z_score']}, +{r['latest_daily_increase']} in one day).")
        else:
            st.success("✅ No abnormal review-count spikes detected.")


def render_leaderboard(products: list, scores_df: pd.DataFrame):
    if scores_df.empty:
        st.info("No tracked products with history yet. Run generate_demo_data.py "
                "or scraper.py first.")
        return

    st.subheader("📉 Most deceptive products right now")
    st.caption("Products with under 7 days of tracked history are marked 'Building history' — "
               "their score isn't reliable yet, just a placeholder until more days accumulate.")

    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        brand_filter = st.multiselect("Filter by brand", sorted(scores_df["Brand"].dropna().unique()))
    with fcol2:
        category_filter = st.multiselect("Filter by category", sorted(scores_df["Category"].dropna().unique()))
    with fcol3:
        sort_col = st.selectbox("Sort by", ["Trust Score", "Days Tracked", "Brand", "Product"])

    df = scores_df.drop(columns=["id"])
    if brand_filter:
        df = df[df["Brand"].isin(brand_filter)]
    if category_filter:
        df = df[df["Category"].isin(category_filter)]
    df = df.sort_values(sort_col, ascending=(sort_col != "Trust Score"))

    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Download leaderboard (CSV)", data=df.to_csv(index=False),
                        file_name="leaderboard.csv", mime="text/csv")

    st.subheader("🏷️ Brand rollup — average Trust Score")
    brand_df = df.groupby("Brand", as_index=False)["Trust Score"].mean().round(1)
    brand_df = brand_df.sort_values("Trust Score")
    st.bar_chart(brand_df.set_index("Brand"))


def render_comparison(products: list):
    st.subheader("⚖️ Compare products side by side")
    labels = {p["id"]: f"{p['brand']} — {p['name']}" for p in products}
    selected_ids = st.multiselect(
        "Pick 2–3 tracked products to compare", options=list(labels.keys()),
        format_func=lambda pid: labels[pid], max_selections=3,
    )

    if len(selected_ids) < 2:
        st.info("Pick at least 2 products above to compare them.")
        return

    cols = st.columns(len(selected_ids))
    for col, pid in zip(cols, selected_ids):
        product = next(p for p in products if p["id"] == pid)
        history = load_history(pid)
        if history.empty:
            col.warning(f"No history for {product['name']}")
            continue
        result = compute_trust_score(history)
        label = score_to_label(result["trust_score"])
        with col:
            st.plotly_chart(trust_gauge(result["trust_score"], label), use_container_width=True)
            st.caption(f"**{product['brand']} — {product['name']}**")
            st.metric("Days tracked", len(history))
            d = result["discount_mismatch"]
            st.metric("Advertised discount", f"{d['advertised_discount_pct']}%")
            st.metric("Real discount", f"{d['real_discount_pct']}%")
            flags = []
            if result["mrp_inflation"]["flagged"]:
                flags.append("🚩 MRP inflation")
            if result["shrinkflation"]["flagged"]:
                flags.append("🚩 Shrinkflation")
            if result["review_spike"]["flagged"]:
                flags.append("🚩 Review spike")
            st.write(", ".join(flags) if flags else "✅ No flags")


def render_trending(products: list):
    st.subheader("🔥 Trending Now")
    st.caption("Ranked using real signals only: Amazon's own 'bought in past month' badge "
               "(when shown), star rating, and review count. Nothing here is estimated or "
               "guessed — if a product has no 'bought in past month' badge on its page, it "
               "just won't have a number in that column.")

    rows = []
    for p in products:
        history = load_history(p["id"])
        if history.empty:
            continue
        latest = history.sort_values("snapshot_date").iloc[-1]
        rows.append({
            "Brand": p["brand"], "Product": p["name"], "Category": p["category"],
            "Bought in past month": (int(latest["bought_past_month"])
                                      if pd.notna(latest.get("bought_past_month")) else None),
            "Rating": latest.get("rating"),
            "Review Count": (int(latest["review_count"])
                              if pd.notna(latest.get("review_count")) else None),
        })

    if not rows:
        st.info("No tracked products yet.")
        return

    df = pd.DataFrame(rows)

    has_badge = df["Bought in past month"].notna().any()
    if has_badge:
        df_sorted = df.sort_values("Bought in past month", ascending=False, na_position="last")
    else:
        st.info("None of your currently tracked products have Amazon's 'bought in past "
                "month' badge visible right now — falling back to rating × review count "
                "as the popularity signal instead.")
        df_sorted = df.copy()
        df_sorted["popularity_proxy"] = df_sorted["Rating"].fillna(0) * df_sorted["Review Count"].fillna(0)
        df_sorted = df_sorted.sort_values("popularity_proxy", ascending=False).drop(columns="popularity_proxy")

    st.dataframe(df_sorted, use_container_width=True, hide_index=True)


def guess_platform(url: str):
    if "amazon." in url:
        return "amazon"
    if "flipkart." in url:
        return "flipkart"
    return None


def scrape_and_track_now(url: str):
    """Live-scrapes a URL the moment it's pasted and adds it to the tracked
    database as a new product with today's snapshot. Returns the product
    dict on success, or None if the scrape failed (blocked, invalid URL,
    unsupported site, etc.)."""
    platform = guess_platform(url)
    if platform is None:
        return None, "Only Amazon.in and Flipkart URLs are supported."

    data = scraper.scrape_product(url, platform)
    if data is None or data.get("price") is None:
        return None, ("Couldn't read this page — it may be blocking automated "
                       "requests, or the URL isn't a real product page.")

    with db.get_conn() as conn:
        product_id = db.upsert_product(
            conn, url=url, platform=platform, name=data["name"],
            category="Uncategorized", brand=None, seller=data.get("seller"),
            weight_value=data.get("weight_value"), weight_unit=data.get("weight_unit"),
        )
        db.insert_snapshot(
            conn, product_id=product_id, snapshot_date=date.today().isoformat(),
            price=data.get("price"), mrp=data.get("mrp"),
            weight_value=data.get("weight_value"), weight_unit=data.get("weight_unit"),
            rating=data.get("rating"), review_count=data.get("review_count"),
            bought_past_month=data.get("bought_past_month"),
        )
    return product_id, None


def main():
    st.title("🔍 Discount Deception Detector")
    st.caption("Catching fake discounts and shrinkflation on Indian e-commerce, one "
               "tracked product at a time.")

    products = load_products()

    view = st.sidebar.radio("View", ["Product Report Card", "Leaderboard", "Compare Products", "Trending Now"])

    if not products:
        st.warning("No products tracked yet. Run `python generate_demo_data.py` "
                   "to seed demo data, or `python scraper.py` to pull live data.")
        return

    scores_df = compute_all_scores(products)
    render_alert_banner(scores_df)

    if view == "Product Report Card":
        st.sidebar.subheader("Find a product")
        pasted_url = st.sidebar.text_input("Paste an Amazon/Flipkart URL")

        product = None
        if pasted_url:
            product = next((p for p in products if p["url"] == pasted_url), None)
            if product is None:
                with st.sidebar:
                    with st.spinner("Fetching this product now..."):
                        product_id, error = scrape_and_track_now(pasted_url)
                if error:
                    st.sidebar.error(error)
                else:
                    st.cache_data.clear()
                    products = load_products()
                    product = next(p for p in products if p["id"] == product_id)
                    st.sidebar.success("Fetched! Note: with only today's data, "
                                        "trend-based signals (MRP inflation, "
                                        "shrinkflation) need a few more days of "
                                        "history to say anything meaningful.")

        if product is None:
            labels = [f"{p['brand']} — {p['name']}" for p in products]
            idx = st.sidebar.selectbox("Or pick a tracked product", range(len(products)),
                                        format_func=lambda i: labels[i])
            product = products[idx]

        history = load_history(product["id"])
        if history.empty:
            st.warning("No history yet for this product.")
        else:
            render_report_card(product, history)

    elif view == "Leaderboard":
        render_leaderboard(products, scores_df)

    elif view == "Compare Products":
        render_comparison(products)

    else:
        render_trending(products)


if __name__ == "__main__":
    main()
