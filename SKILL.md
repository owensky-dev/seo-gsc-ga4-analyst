---
name: seo-gsc-ga4-analyst
description: >-
  Build and run local SEO data analysis workflows using Google Search Console API and GA4 Data API. Use when the user wants GSC content decay analysis, a 12-month page heatmap, declining-page prioritization, a private offline HTML report, GSC CSV analysis, a Python SEO project, GSC/GA4 data fetching, weekly SEO reports, or API troubleshooting while keeping credentials local.
---

# SEO GSC GA4 Analyst

Use this skill to turn GSC and GA4 into a local SEO analyst workflow. Keep secrets local, pull raw CSVs, produce opportunity tables, and write Chinese-first diagnostic reports unless the user asks otherwise.

## Content Decay / 内容衰退模式

For monthly heatmaps, traffic decay, declining pages, or standalone GSC CSV analysis, read [references/content_decay.md](references/content_decay.md) and use that route. It requires **GSC only**, not GA4. Reuse an existing page-daily CSV when appropriate; never use query-detail sums as page totals. The shared browser engine powers both private offline reports and the free public CSV tool. Do not upload private data or generated reports to GitHub/Red Skill. Only the data-free public bundle belongs in `docs/`.

## Workflow

1. Check the current folder. If no SEO project exists, scaffold one with:

```bash
python3 <skill-dir>/scripts/scaffold_seo_project.py --target .
```

2. Ask only for missing required config. Create `.env` from `.env.example` with:

```env
SITE_NAME=
GSC_SITE_URL=
SITE_BASE_URL=
GA4_PROPERTY_ID=
GOOGLE_APPLICATION_CREDENTIALS=
```

Never write `service_account.json`, `private_key`, `client_email`, `refresh_token`, or real credentials into code, reports, Git, or shared artifacts.

3. Install dependencies in a local virtual environment and run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/fetch_gsc.py
.venv/bin/python scripts/fetch_ga4.py
.venv/bin/python scripts/analyze_seo.py
.venv/bin/python scripts/weekly_report.py
```

The GA4 fetch must keep landing-page Sessions and ecommerce events in separate requests. Preserve `date` on the Organic landing-page rows, and fetch `add_to_cart` plus `begin_checkout` using `date`, `landingPagePlusQueryString`, and `eventName` with `eventCount`.

The GSC fetch must keep three grains in separate requests: `date` with `aggregationType=byProperty` for site KPIs, `date,page` with `aggregationType=byPage` for page totals and decline analysis, and `date,page,query,country,device` for query/intent detail. Use `type=web` for all three. Never sum query detail into site or page KPIs because anonymized queries make that detail non-additive.

Use one shared expected window for GSC, GA4, analysis, and the weekly report. The default is 90 inclusive days ending three days ago so the workflow avoids the usual GSC finalization lag. For an explicit historical run, pass the same `--start-date` and `--end-date` to all four commands.

4. When network access is restricted, retry API fetch commands with the appropriate approval path. Explain that GSC/GA4 calls require outbound network access.

5. Validate outputs before reporting success:

- `data/raw/gsc_90d.csv`
- `data/raw/gsc_daily_90d.csv`
- `data/raw/gsc_page_daily_90d.csv`
- `data/raw/gsc_fetch_manifest.json`
- `data/raw/ga4_organic_landing_pages_90d.csv`
- `data/raw/ga4_organic_funnel_90d.csv`
- `data/raw/ga4_fetch_manifest.json`
- `data/processed/gsc_pages_90d.csv`
- `data/processed/gsc_keywords_90d.csv`
- `data/processed/seo_merged_pages_90d.csv`
- `data/processed/seo_analysis_manifest.json`
- `reports/seo_opportunities.md`
- `reports/seo_opportunities.csv`
- `reports/seo_weekly_report.md`

Treat the two GSC daily tables and both fetch manifests as required inputs. GSC may omit dates with zero data, so do not require one row per calendar day. A completed request may also produce header-only detail, site, and page CSVs for an entirely zero-data window; report site KPIs as zero/no data and return no GSC page or keyword opportunities. Require completed manifests whose exact request window and parameters match the shared expected window, whose file hashes and row counts match, and whose returned dates stay inside that window. The site and page daily streams must share the same contract; never fall back to query detail.

Validators must read each manifest or CSV into bytes once, verify the hash, and parse that same byte snapshot. Calling code must not pre-read or reread validated CSV paths. The 28-day click-decline comparison requires a manifest-proven window of at least 56 days. Treat omitted dates as zero only after that request contract passes. `weekly_report.py` must also validate `seo_analysis_manifest.json`; if a fetch manifest or bound processed artifact changed after analysis, stop and rerun `analyze_seo.py` before writing the weekly report.

## Diagnosis Standards

Read [references/gsc_ga4_workflow.md](references/gsc_ga4_workflow.md) before writing advanced reports or changing the scoring logic.

Always cover:

- High impressions but low CTR: rewrite Title and Meta Description.
- Average position 8-20: expand content, add internal links, improve FAQs.
- Click decline: compare recent 28 days vs prior 28 days.
- Organic sessions high but conversions low: improve CTA, trust elements, product cards, page speed, and form/cart path.
- Query/page mismatch: adjust page content or create a new collection, product, guide, or comparison page.
- Content gaps: cluster queries by intent and theme, then propose pages or modules.
- SEO experiment tracking: record changed URL, date, field changed, hypothesis, and pre/post metrics.

## Advanced Report

For advanced GSC diagnosis, combine tables and charts:

- Daily clicks, impressions, CTR, and position trend.
- Query intent mix: brand, product, problem, comparison, purchase, informational.
- Theme clusters by impressions and clicks.
- Page opportunity matrix: impressions vs position, sized by sessions or revenue.
- Content gap table with page recommendation.
- Prioritized execution plan with P0/P1/P2.

Use a Data Analytics artifact when available. If the artifact opens blank, create a static HTML fallback with local PNG/SVG charts and link it in the final answer. Do not treat a blank hosted widget as a completed report.

## Common Fixes

- GSC 403 or no rows: confirm the service account has Search Console access and the `GSC_SITE_URL` exactly matches the verified property. Try both `https://example.com/` and `sc-domain:example.com` only when the user owns both.
- GA4 permission error: add the service account email to the GA4 property as Viewer or Analyst.
- GA4 revenue is zero: note this may reflect ecommerce event setup or attribution, not necessarily zero SEO value.
- GA4 landing page `(not set)`: filter or separate it so page-level SEO recommendations stay actionable.
- Python chart library crashes: use Pillow, SVG, or Data Analytics native charts instead of blocking on Matplotlib.
