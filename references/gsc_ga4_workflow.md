# GSC and GA4 SEO Workflow Reference

## Data Model

Keep three GSC raw tables because Search Analytics grains are not additive:

- `gsc_daily_90d.csv`: `date`, `type=web`, `aggregationType=byProperty`. This is the only source for site clicks, impressions, CTR, weighted position, coverage, and daily trend.
- `gsc_page_daily_90d.csv`: `date,page`, `type=web`, `aggregationType=byPage`. Use it for page totals, page opportunity scoring, and recent-vs-prior click decline.
- `gsc_90d.csv`: `date,page,query,country,device`, `type=web`. Use it only for query/page mapping, keyword opportunities, intent, themes, and content gaps.

All three tables use these metrics:

- `clicks`
- `impressions`
- `ctr`
- `position`

Do not sum the query-detail table into site or page KPIs. GSC omits anonymized queries from query-grain results, so those sums can be materially lower than Search Console's property totals. Fail closed when either daily table or its completed fetch manifest is missing or inconsistent; never substitute query detail. Header-only CSVs with `row_count=0` are valid when a completed request found no GSC data for the entire window.

GA4 Organic Search landing page data should use:

- `date`
- `landingPagePlusQueryString`
- `sessionDefaultChannelGroup`
- `sessions`
- `engagedSessions`
- `conversions`
- `totalRevenue`

GA4 Organic funnel events must use a separate query with:

- `date`
- `landingPagePlusQueryString`
- `eventName`, filtered to `add_to_cart` and `begin_checkout`
- `eventCount`

Do not add `eventName` to the landing-page Sessions query because it changes the aggregation grain. Strip the query string before persisting funnel landing-page values. Use the dated landing-page rows as coverage and the separate event rows for daily/weekly funnel totals.

Normalize URLs before joining. Strip query strings and fragments, lowercase hostnames, preserve the path, and remove trailing slashes except for the homepage.

## Window and Manifest Contract

Use one inclusive expected date window for all GSC and GA4 streams. The default workflow window is 90 days ending `today - 3 days`; GSC, GA4, `analyze_seo.py`, and `weekly_report.py` must calculate or receive the same start and end. Explicit historical runs must pass the same `--start-date` and `--end-date` to all four commands.

Successful fetches write `gsc_fetch_manifest.json` and `ga4_fetch_manifest.json`. Validate before analysis:

- `status=complete`, supported manifest version, and the exact expected start/end.
- Each stream's dimensions, filters, `type=web`, aggregation type, and page-size contract.
- CSV file name, SHA-256, and row count.
- Every returned date is inside the expected window.
- GSC site-daily and page-daily requests use the same expected window.

Search Analytics may omit a calendar date when it has no data. The completed sidecar manifest proves the full date range was requested, so missing natural-day rows are valid and must not be treated as a failed fetch. If detail, site-daily, and page-daily all contain only headers with matching zero row counts, report site KPIs as zero/no data and leave GSC page/keyword opportunities empty. Conversely, a short or stale CSV cannot prove coverage: a previous 14-day manifest must fail a current 90-day run even if its latest row looks fresh.

The recent-28-days versus prior-28-days calculation requires the manifest-proven expected window to cover at least 56 inclusive days. Anchor both periods to the expected end date, and treat omitted dates as zero only after the request contract passes.

Read each manifest or CSV once as bytes, verify its SHA-256, and parse the same bytes through an in-memory buffer. Do not read a CSV into a DataFrame before hashing its path, and do not reread a validated path later. This snapshot rule prevents a concurrent refresh from making validation describe different bytes from the DataFrame used in analysis.

After analysis succeeds, write `data/processed/seo_analysis_manifest.json` atomically. It binds the expected window, the exact source-manifest byte hashes used by analysis, and the hashes of processed page/keyword/merged tables plus opportunity outputs. The weekly report must obtain processed DataFrames from the analysis validator's verified bytes, then require the GSC/GA4 validators to match the bound source-manifest hashes. Use the returned GA4 DataFrames for funnel comparison rather than rereading paths. If raw data is refreshed without rerunning analysis, fail closed rather than mixing new source totals with stale processed rows.

## Opportunity Logic

Use these rules as defaults, then tune thresholds based on the site's data volume:

- High impressions, low CTR: page impressions above the 65th percentile and CTR below 70 percent of site average.
- Position 8-20: query has meaningful impressions and weighted average position between 8 and 20.
- Click decline: recent 28 days vs prior 28 days, with at least 10 prior clicks and either 20 percent decline or 10-click absolute decline.
- Traffic high, conversion low: sessions above the 65th percentile and conversion rate below half of site average.
- Query mismatch/content gap: high-impression query has no dedicated page or ranks beyond position 12.

Priority score should combine impact and feasibility:

- Impact: impressions, clicks lost, sessions, revenue, or conversion gap.
- Feasibility: current position, page type, whether the query already maps to a relevant page.
- Risk: avoid recommending major architecture changes before title/meta/content/internal-link fixes.

## Intent Clustering

Classify query intent with simple rules first:

- Brand: site name, brand variants, branded product names.
- Product: product nouns, collection names, SKU-like terms.
- Problem: how, what, why, guide, install, size, cost, cleaning, repair.
- Comparison: vs, versus, compare, best, alternative.
- Purchase: buy, sale, price, discount, near me, free shipping.
- Informational: definitions, ideas, inspiration, compatibility, care.

Keep the original English keywords unchanged in Chinese reports.

## Report Structure

Use this structure for advanced reports:

1. Executive summary with the top 3-5 findings.
2. KPI overview: clicks, impressions, CTR, average position, sessions, conversions, revenue.
3. Trend chart: daily clicks and impressions, with CTR/position commentary.
4. Query intent and theme diagnosis.
5. Page opportunity matrix.
6. Content gap table.
7. Conversion diagnosis from GA4.
8. P0/P1/P2 execution plan.
9. Measurement plan for the next 14 and 28 days.
10. Caveats: date range, API filters, missing data, attribution limitations.

GA4 Organic conversions and revenue are attribution/tracking signals in this two-source workflow; they are not reconciled Shopify order truth. GSC and GA4 also retain their source-native calendar dates, so call out date-boundary differences when comparing daily series.

## Execution Recommendations

For each page, include concrete actions:

- Title: 3-5 English options when the site targets the US.
- Meta Description: 3-5 English options.
- H1/H2: recommended structure.
- Content modules: buying guide, comparison, sizing, installation, FAQ, reviews, trust badges.
- Internal links: source pages and anchor text.
- CTA: above-fold offer, product grid, lead/cart path, reassurance copy.
- New page decision: create only when query intent is distinct enough that the current page cannot satisfy it.

## Data Analytics Fallback

If a hosted Data Analytics artifact renders blank:

1. Confirm the manifest and snapshot were validated.
2. Export the manifest/snapshot to files for debugging.
3. Create a static HTML report with local image or SVG charts.
4. Tell the user which file to open and continue using that as the reliable deliverable.
