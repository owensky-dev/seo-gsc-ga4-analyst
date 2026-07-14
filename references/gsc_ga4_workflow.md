# GSC and GA4 SEO Workflow Reference

## Data Model

GSC raw data should use these dimensions:

- `date`
- `page`
- `query`
- `country`
- `device`

GSC metrics:

- `clicks`
- `impressions`
- `ctr`
- `position`

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
