from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import DATA_PROCESSED_DIR, DATA_RAW_DIR, REPORTS_DIR, ensure_dirs, load_settings


def money(value: float) -> str:
    return f"${value:,.2f}"


def organic_funnel_comparison(landing_path: Path, funnel_path: Path) -> dict | None:
    if not landing_path.exists() or not funnel_path.exists():
        return None
    landing = pd.read_csv(landing_path)
    funnel = pd.read_csv(funnel_path)
    if landing.empty or "date" not in landing.columns:
        return None
    landing["date"] = pd.to_datetime(landing["date"], errors="coerce")
    funnel["date"] = pd.to_datetime(funnel.get("date"), errors="coerce")
    latest = landing["date"].max()
    if pd.isna(latest):
        return None

    def summarize(start: pd.Timestamp, end: pd.Timestamp) -> dict:
        landing_slice = landing[landing["date"].between(start, end)]
        funnel_slice = funnel[funnel["date"].between(start, end)]
        sessions = pd.to_numeric(landing_slice["sessions"], errors="coerce").fillna(0).sum()
        event_counts = (
            funnel_slice.assign(
                eventCount=pd.to_numeric(funnel_slice["eventCount"], errors="coerce").fillna(0)
            )
            .groupby("eventName")["eventCount"]
            .sum()
        )
        add_to_cart = float(event_counts.get("add_to_cart", 0))
        begin_checkout = float(event_counts.get("begin_checkout", 0))
        return {
            "start": start.date().isoformat(),
            "end": end.date().isoformat(),
            "sessions": float(sessions),
            "add_to_cart": add_to_cart,
            "begin_checkout": begin_checkout,
            "add_to_cart_rate": add_to_cart / sessions if sessions else 0,
            "cart_to_checkout_rate": begin_checkout / add_to_cart if add_to_cart else 0,
        }

    current_start = latest - pd.Timedelta(days=6)
    previous_end = current_start - pd.Timedelta(days=1)
    previous_start = previous_end - pd.Timedelta(days=6)
    return {
        "current": summarize(current_start, latest),
        "previous": summarize(previous_start, previous_end),
    }


def main() -> None:
    settings = load_settings()
    ensure_dirs()
    merged_path = DATA_PROCESSED_DIR / "seo_merged_pages_90d.csv"
    keywords_path = DATA_PROCESSED_DIR / "gsc_keywords_90d.csv"
    opportunities_path = REPORTS_DIR / "seo_opportunities.csv"

    if not merged_path.exists() or not keywords_path.exists() or not opportunities_path.exists():
        raise RuntimeError("请先运行 python3 scripts/analyze_seo.py 生成 processed 数据和机会报告。")

    merged = pd.read_csv(merged_path)
    keywords = pd.read_csv(keywords_path)
    opportunities = pd.read_csv(opportunities_path)

    clicks = merged["clicks"].sum()
    impressions = merged["impressions"].sum()
    ctr = clicks / impressions if impressions else 0
    avg_position = (
        (merged["position"] * merged["impressions"]).sum() / impressions
        if impressions
        else 0
    )
    sessions = merged["sessions"].sum()
    conversions = merged["conversions"].sum()
    revenue = merged["totalRevenue"].sum()
    funnel = organic_funnel_comparison(
        DATA_RAW_DIR / "ga4_organic_landing_pages_90d.csv",
        DATA_RAW_DIR / "ga4_organic_funnel_90d.csv",
    )

    top_pages = merged.sort_values("clicks", ascending=False).head(10)
    low_ctr_keywords = keywords[
        (keywords["impressions"] >= max(20, keywords["impressions"].quantile(0.60)))
        & (keywords["ctr"] < ctr)
    ].sort_values("impressions", ascending=False).head(10)
    ranking_opportunities = keywords[
        (keywords["position"].between(8, 20))
        & (keywords["impressions"] >= max(20, keywords["impressions"].quantile(0.60)))
    ].sort_values(["impressions", "position"], ascending=[False, True]).head(10)

    lines = [
        f"# {settings['SITE_NAME']} SEO 周报",
        "",
        "## 1. Organic Search 总览",
        "",
        f"- Clicks: {clicks:,.0f}",
        f"- Impressions: {impressions:,.0f}",
        f"- CTR: {ctr:.2%}",
        f"- Avg Position: {avg_position:.2f}",
        f"- Organic Sessions: {sessions:,.0f}",
        f"- Conversions: {conversions:,.2f}",
        f"- Revenue / Leads: {money(revenue)}",
        "",
    ]
    if funnel:
        current, previous = funnel["current"], funnel["previous"]
        lines.extend(
            [
                "## 2. Organic GA4 漏斗：最近7天 vs 前7天",
                "",
                f"- 周期: {current['start']} 至 {current['end']}；对比 {previous['start']} 至 {previous['end']}",
                f"- Sessions: {current['sessions']:,.0f} vs {previous['sessions']:,.0f}",
                f"- Add to cart: {current['add_to_cart']:,.0f} vs {previous['add_to_cart']:,.0f}；ATC rate {current['add_to_cart_rate']:.2%} vs {previous['add_to_cart_rate']:.2%}",
                f"- Begin checkout: {current['begin_checkout']:,.0f} vs {previous['begin_checkout']:,.0f}；Cart-to-checkout {current['cart_to_checkout_rate']:.2%} vs {previous['cart_to_checkout_rate']:.2%}",
                "",
            ]
        )
    else:
        lines.extend(["## 2. Organic GA4 漏斗", "", "- 日期级漏斗数据不可用；请重新运行 scripts/fetch_ga4.py。", ""])
    lines.extend([
        "## 3. 表现最强页面",
        "",
    ])

    for _, row in top_pages.iterrows():
        lines.append(f"- {row['page_url']} | Clicks {row['clicks']:.0f} | Sessions {row['sessions']:.0f} | Revenue {money(row['totalRevenue'])}")

    lines.extend(["", "## 4. 高曝光低CTR关键词", ""])
    for _, row in low_ctr_keywords.iterrows():
        lines.append(f"- `{row['query']}` | {row['page_url']} | Impressions {row['impressions']:.0f} | CTR {row['ctr']:.2%} | Position {row['position']:.2f}")

    lines.extend(["", "## 5. 排名8-20位关键词机会", ""])
    for _, row in ranking_opportunities.iterrows():
        lines.append(f"- `{row['query']}` | {row['page_url']} | Impressions {row['impressions']:.0f} | Position {row['position']:.2f}")

    lines.extend(["", "## 6. 下周SEO行动清单", ""])
    for _, row in opportunities.head(12).iterrows():
        query = f" | Query `{row['query']}`" if isinstance(row.get("query"), str) and row.get("query") else ""
        lines.append(f"- [{row['type']}] {row['page']}{query}: {row['recommendation']}")

    (REPORTS_DIR / "seo_weekly_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Weekly report written to {REPORTS_DIR / 'seo_weekly_report.md'}")


if __name__ == "__main__":
    main()
