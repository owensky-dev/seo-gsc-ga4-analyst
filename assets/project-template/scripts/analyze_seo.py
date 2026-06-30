from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from config import (
    DATA_PROCESSED_DIR,
    DATA_RAW_DIR,
    REPORTS_DIR,
    ensure_dirs,
    load_settings,
    normalize_url,
)


QUESTION_MODIFIERS = (
    "how",
    "what",
    "why",
    "best",
    "vs",
    "versus",
    "ideas",
    "guide",
    "size",
    "sizes",
    "install",
    "installation",
    "review",
    "reviews",
    "compare",
    "cost",
    "benefits",
    "bathroom",
    "kitchen",
)


@dataclass(frozen=True)
class Opportunity:
    type: str
    priority_score: float
    page: str
    query: str
    clicks: float
    impressions: float
    ctr: float
    position: float
    sessions: float
    conversions: float
    revenue: float
    recommendation: str


def weighted_average(values: pd.Series, weights: pd.Series) -> float:
    valid = weights.fillna(0) > 0
    if not valid.any():
        return float(values.fillna(0).mean() or 0)
    return float((values[valid] * weights[valid]).sum() / weights[valid].sum())


def load_inputs(gsc_path: Path, ga4_path: Path, site_url: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    gsc = pd.read_csv(gsc_path) if gsc_path.exists() else pd.DataFrame()
    ga4 = pd.read_csv(ga4_path) if ga4_path.exists() else pd.DataFrame()

    if gsc.empty:
        raise RuntimeError(f"GSC CSV is empty or missing: {gsc_path}")
    if ga4.empty:
        raise RuntimeError(f"GA4 CSV is empty or missing: {ga4_path}")

    gsc["page_url"] = gsc["page"].map(lambda value: normalize_url(str(value), site_url))
    gsc["date"] = pd.to_datetime(gsc["date"], errors="coerce")
    for column in ["clicks", "impressions", "ctr", "position"]:
        gsc[column] = pd.to_numeric(gsc[column], errors="coerce").fillna(0)

    ga4["landing_page_url"] = ga4["landingPagePlusQueryString"].fillna("").map(
        lambda value: normalize_url(str(value), site_url)
    )
    ga4 = ga4[ga4["landing_page_url"] != ""].copy()
    for column in ["sessions", "engagedSessions", "conversions", "totalRevenue"]:
        ga4[column] = pd.to_numeric(ga4[column], errors="coerce").fillna(0)

    return gsc, ga4


def build_aggregates(gsc: pd.DataFrame, ga4: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    gsc_pages = (
        gsc.groupby("page_url", dropna=False)
        .apply(
            lambda group: pd.Series(
                {
                    "clicks": group["clicks"].sum(),
                    "impressions": group["impressions"].sum(),
                    "ctr": group["clicks"].sum() / group["impressions"].sum() if group["impressions"].sum() else 0,
                    "position": weighted_average(group["position"], group["impressions"]),
                    "query_count": group["query"].nunique(),
                }
            )
        )
        .reset_index()
    )

    gsc_keywords = (
        gsc.groupby(["page_url", "query"], dropna=False)
        .apply(
            lambda group: pd.Series(
                {
                    "clicks": group["clicks"].sum(),
                    "impressions": group["impressions"].sum(),
                    "ctr": group["clicks"].sum() / group["impressions"].sum() if group["impressions"].sum() else 0,
                    "position": weighted_average(group["position"], group["impressions"]),
                }
            )
        )
        .reset_index()
    )

    ga4_pages = (
        ga4.groupby("landing_page_url", dropna=False)
        .agg(
            sessions=("sessions", "sum"),
            engagedSessions=("engagedSessions", "sum"),
            conversions=("conversions", "sum"),
            totalRevenue=("totalRevenue", "sum"),
        )
        .reset_index()
    )
    ga4_pages["conversion_rate"] = ga4_pages.apply(
        lambda row: row["conversions"] / row["sessions"] if row["sessions"] else 0,
        axis=1,
    )

    merged = gsc_pages.merge(
        ga4_pages,
        left_on="page_url",
        right_on="landing_page_url",
        how="outer",
    )
    merged["page_url"] = merged["page_url"].fillna(merged["landing_page_url"])
    for column in [
        "clicks",
        "impressions",
        "ctr",
        "position",
        "query_count",
        "sessions",
        "engagedSessions",
        "conversions",
        "totalRevenue",
        "conversion_rate",
    ]:
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0)
    merged = merged.drop(columns=["landing_page_url"])
    return gsc_pages, gsc_keywords, merged


def click_drop_opportunities(gsc: pd.DataFrame, merged_by_page: pd.DataFrame) -> list[Opportunity]:
    max_date = gsc["date"].max()
    if pd.isna(max_date):
        return []

    current_start = max_date - pd.Timedelta(days=27)
    previous_start = current_start - pd.Timedelta(days=28)
    previous_end = current_start - pd.Timedelta(days=1)
    current = gsc[gsc["date"].between(current_start, max_date)]
    previous = gsc[gsc["date"].between(previous_start, previous_end)]
    current_clicks = current.groupby("page_url")["clicks"].sum().rename("current_clicks")
    previous_clicks = previous.groupby("page_url")["clicks"].sum().rename("previous_clicks")
    comparison = pd.concat([current_clicks, previous_clicks], axis=1).fillna(0).reset_index()
    comparison["click_delta"] = comparison["current_clicks"] - comparison["previous_clicks"]
    comparison["drop_rate"] = comparison.apply(
        lambda row: row["click_delta"] / row["previous_clicks"] if row["previous_clicks"] else 0,
        axis=1,
    )
    comparison = comparison[
        (comparison["previous_clicks"] >= 10)
        & ((comparison["drop_rate"] <= -0.2) | (comparison["click_delta"] <= -10))
    ]
    enriched = comparison.merge(merged_by_page, on="page_url", how="left")

    results = []
    for _, row in enriched.sort_values(["click_delta", "previous_clicks"]).head(30).iterrows():
        results.append(
            Opportunity(
                type="点击下滑页面",
                priority_score=abs(float(row["click_delta"])) + float(row.get("impressions", 0)) * 0.001,
                page=row["page_url"],
                query="",
                clicks=float(row.get("clicks", 0)),
                impressions=float(row.get("impressions", 0)),
                ctr=float(row.get("ctr", 0)),
                position=float(row.get("position", 0)),
                sessions=float(row.get("sessions", 0)),
                conversions=float(row.get("conversions", 0)),
                revenue=float(row.get("totalRevenue", 0)),
                recommendation=(
                    f"最近28天点击 {row['current_clicks']:.0f}，前28天 {row['previous_clicks']:.0f}。"
                    "优先检查排名变化、Title/Meta 改动、索引状态、竞品新增内容和页面可用性。"
                ),
            )
        )
    return results


def build_opportunities(gsc: pd.DataFrame, gsc_keywords: pd.DataFrame, merged: pd.DataFrame) -> list[Opportunity]:
    opportunities: list[Opportunity] = []
    site_ctr = gsc["clicks"].sum() / gsc["impressions"].sum() if gsc["impressions"].sum() else 0
    min_page_impressions = max(100, float(merged["impressions"].quantile(0.65)))
    min_query_impressions = max(20, float(gsc_keywords["impressions"].quantile(0.60)))

    high_ctr_gap = merged[
        (merged["impressions"] >= min_page_impressions)
        & (merged["ctr"] < max(site_ctr * 0.7, 0.01))
    ].copy()
    high_ctr_gap["priority_score"] = high_ctr_gap["impressions"] * (max(site_ctr, 0.01) - high_ctr_gap["ctr"]).clip(lower=0)
    for _, row in high_ctr_gap.sort_values("priority_score", ascending=False).head(30).iterrows():
        opportunities.append(
            Opportunity(
                type="高曝光低CTR页面",
                priority_score=float(row["priority_score"]),
                page=row["page_url"],
                query="",
                clicks=float(row["clicks"]),
                impressions=float(row["impressions"]),
                ctr=float(row["ctr"]),
                position=float(row["position"]),
                sessions=float(row["sessions"]),
                conversions=float(row["conversions"]),
                revenue=float(row["totalRevenue"]),
                recommendation="优先重写 Title 和 Meta Description，让主关键词、卖点、尺寸/场景和信任信号更靠前；同步检查搜索结果页是否被竞品价格、评论或图片吸走点击。",
            )
        )

    keyword_near_page_one = gsc_keywords[
        (gsc_keywords["impressions"] >= min_query_impressions)
        & (gsc_keywords["position"].between(8, 20))
    ].copy()
    keyword_near_page_one["priority_score"] = keyword_near_page_one["impressions"] / keyword_near_page_one["position"].clip(lower=1)
    for _, row in keyword_near_page_one.sort_values("priority_score", ascending=False).head(50).iterrows():
        opportunities.append(
            Opportunity(
                type="排名8-20位关键词",
                priority_score=float(row["priority_score"]),
                page=row["page_url"],
                query=row["query"],
                clicks=float(row["clicks"]),
                impressions=float(row["impressions"]),
                ctr=float(row["ctr"]),
                position=float(row["position"]),
                sessions=0,
                conversions=0,
                revenue=0,
                recommendation="这个词已经接近首页可见区。建议补充对应内容模块、FAQ、对比表或购买指南，并从相关产品页/分类页增加内链。",
            )
        )

    opportunities.extend(click_drop_opportunities(gsc, merged))

    session_threshold = max(20, float(merged["sessions"].quantile(0.65)))
    positive_rates = merged.loc[merged["sessions"] > 0, "conversion_rate"]
    low_conversion_threshold = float(positive_rates.quantile(0.35)) if not positive_rates.empty else 0
    low_conversion = merged[
        (merged["sessions"] >= session_threshold)
        & ((merged["conversions"] <= 0) | (merged["conversion_rate"] <= low_conversion_threshold))
    ].copy()
    low_conversion["priority_score"] = low_conversion["sessions"] * (1 - low_conversion["conversion_rate"].clip(upper=1))
    for _, row in low_conversion.sort_values("priority_score", ascending=False).head(30).iterrows():
        opportunities.append(
            Opportunity(
                type="Organic流量高但转化低页面",
                priority_score=float(row["priority_score"]),
                page=row["page_url"],
                query="",
                clicks=float(row["clicks"]),
                impressions=float(row["impressions"]),
                ctr=float(row["ctr"]),
                position=float(row["position"]),
                sessions=float(row["sessions"]),
                conversions=float(row["conversions"]),
                revenue=float(row["totalRevenue"]),
                recommendation="先检查首屏 CTA、价格/促销露出、配送退换承诺、评论信任元素、移动端表单/加购路径；如果页面承接的是信息型搜索，应增加清晰的下一步购买入口。",
            )
        )

    query_gap = gsc_keywords[
        (gsc_keywords["impressions"] >= min_query_impressions)
        & (gsc_keywords["query"].str.lower().str.contains("|".join(QUESTION_MODIFIERS), regex=True, na=False))
        & (~gsc_keywords["page_url"].str.contains("/blog|/blogs|/pages|/guide|/guides", case=False, na=False))
    ].copy()
    query_gap["priority_score"] = query_gap["impressions"] / query_gap["position"].clip(lower=1)
    for _, row in query_gap.sort_values("priority_score", ascending=False).head(30).iterrows():
        opportunities.append(
            Opportunity(
                type="查询与页面不匹配/内容缺口",
                priority_score=float(row["priority_score"]),
                page=row["page_url"],
                query=row["query"],
                clicks=float(row["clicks"]),
                impressions=float(row["impressions"]),
                ctr=float(row["ctr"]),
                position=float(row["position"]),
                sessions=0,
                conversions=0,
                revenue=0,
                recommendation="这个查询可能需要更明确的内容承接。建议在当前页面增加问题解答模块，或新建指南/集合页后用当前页面做内链分发。",
            )
        )

    deduped: dict[tuple[str, str, str], Opportunity] = {}
    for item in opportunities:
        key = (item.type, item.page, item.query)
        if key not in deduped or item.priority_score > deduped[key].priority_score:
            deduped[key] = item
    return sorted(deduped.values(), key=lambda item: item.priority_score, reverse=True)


def write_outputs(
    site_name: str,
    gsc_pages: pd.DataFrame,
    gsc_keywords: pd.DataFrame,
    merged: pd.DataFrame,
    opportunities: list[Opportunity],
) -> None:
    DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    gsc_pages.to_csv(DATA_PROCESSED_DIR / "gsc_pages_90d.csv", index=False)
    gsc_keywords.to_csv(DATA_PROCESSED_DIR / "gsc_keywords_90d.csv", index=False)
    merged.sort_values("clicks", ascending=False).to_csv(DATA_PROCESSED_DIR / "seo_merged_pages_90d.csv", index=False)

    opportunity_rows = [item.__dict__ for item in opportunities]
    opportunities_df = pd.DataFrame(opportunity_rows)
    opportunities_df.to_csv(REPORTS_DIR / "seo_opportunities.csv", index=False)

    total_clicks = gsc_pages["clicks"].sum()
    total_impressions = gsc_pages["impressions"].sum()
    avg_ctr = total_clicks / total_impressions if total_impressions else 0
    avg_position = weighted_average(gsc_pages["position"], gsc_pages["impressions"])
    total_sessions = merged["sessions"].sum()
    total_conversions = merged["conversions"].sum()
    total_revenue = merged["totalRevenue"].sum()

    lines = [
        f"# {site_name} SEO 机会报告",
        "",
        "## 90天总览",
        "",
        f"- GSC Clicks: {total_clicks:,.0f}",
        f"- GSC Impressions: {total_impressions:,.0f}",
        f"- GSC CTR: {avg_ctr:.2%}",
        f"- GSC Avg Position: {avg_position:.2f}",
        f"- GA4 Organic Sessions: {total_sessions:,.0f}",
        f"- GA4 Organic Conversions: {total_conversions:,.2f}",
        f"- GA4 Organic Revenue: ${total_revenue:,.2f}",
        "",
        "## 优先行动清单",
        "",
    ]

    if not opportunities:
        lines.append("当前 CSV 没有识别到符合阈值的机会项。可以降低阈值或扩大时间范围后重跑。")
    else:
        for index, item in enumerate(opportunities[:40], start=1):
            query_text = f" | Query: `{item.query}`" if item.query else ""
            lines.extend(
                [
                    f"### {index}. {item.type}",
                    "",
                    f"- Page: {item.page}{query_text}",
                    f"- Clicks / Impressions / CTR / Position: {item.clicks:,.0f} / {item.impressions:,.0f} / {item.ctr:.2%} / {item.position:.2f}",
                    f"- Sessions / Conversions / Revenue: {item.sessions:,.0f} / {item.conversions:,.2f} / ${item.revenue:,.2f}",
                    f"- 建议: {item.recommendation}",
                    "",
                ]
            )

    (REPORTS_DIR / "seo_opportunities.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge GSC and GA4 data and build SEO opportunity reports.")
    parser.add_argument("--gsc", default=str(DATA_RAW_DIR / "gsc_90d.csv"))
    parser.add_argument("--ga4", default=str(DATA_RAW_DIR / "ga4_organic_landing_pages_90d.csv"))
    args = parser.parse_args()

    settings = load_settings()
    ensure_dirs()
    gsc, ga4 = load_inputs(Path(args.gsc), Path(args.ga4), settings["SITE_BASE_URL"])
    gsc_pages, gsc_keywords, merged = build_aggregates(gsc, ga4)
    opportunities = build_opportunities(gsc, gsc_keywords, merged)
    write_outputs(settings["SITE_NAME"], gsc_pages, gsc_keywords, merged, opportunities)
    print(
        "SEO analysis complete "
        f"pages={len(gsc_pages)} keywords={len(gsc_keywords)} opportunities={len(opportunities)}"
    )


if __name__ == "__main__":
    main()
