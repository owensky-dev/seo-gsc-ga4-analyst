from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import DATA_PROCESSED_DIR, REPORTS_DIR, ensure_dirs, load_settings


def money(value: float) -> str:
    return f"${value:,.2f}"


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
        "## 2. 表现最强页面",
        "",
    ]

    for _, row in top_pages.iterrows():
        lines.append(f"- {row['page_url']} | Clicks {row['clicks']:.0f} | Sessions {row['sessions']:.0f} | Revenue {money(row['totalRevenue'])}")

    lines.extend(["", "## 3. 高曝光低CTR关键词", ""])
    for _, row in low_ctr_keywords.iterrows():
        lines.append(f"- `{row['query']}` | {row['page_url']} | Impressions {row['impressions']:.0f} | CTR {row['ctr']:.2%} | Position {row['position']:.2f}")

    lines.extend(["", "## 4. 排名8-20位关键词机会", ""])
    for _, row in ranking_opportunities.iterrows():
        lines.append(f"- `{row['query']}` | {row['page_url']} | Impressions {row['impressions']:.0f} | Position {row['position']:.2f}")

    lines.extend(["", "## 5. 下周SEO行动清单", ""])
    for _, row in opportunities.head(12).iterrows():
        query = f" | Query `{row['query']}`" if isinstance(row.get("query"), str) and row.get("query") else ""
        lines.append(f"- [{row['type']}] {row['page']}{query}: {row['recommendation']}")

    (REPORTS_DIR / "seo_weekly_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Weekly report written to {REPORTS_DIR / 'seo_weekly_report.md'}")


if __name__ == "__main__":
    main()

