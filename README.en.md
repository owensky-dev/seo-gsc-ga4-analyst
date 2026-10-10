# SEO GSC GA4 Analyst

[![CI](https://github.com/owensky-dev/seo-gsc-ga4-analyst/actions/workflows/ci.yml/badge.svg)](https://github.com/owensky-dev/seo-gsc-ga4-analyst/actions/workflows/ci.yml)

Codex skill for building a local SEO data analysis workflow with Google Search Console API and GA4 Data API.

中文说明（默认）请见 [README.md](README.md)。

It helps Codex scaffold a Python project, fetch GSC and GA4 Organic Search data, merge both sources by landing page, diagnose SEO opportunities, and generate execution-focused SEO reports.

## What It Does

### Content Decay Radar (GSC-only)

[Free browser tool](https://owensky-dev.github.io/seo-gsc-ga4-analyst/). Import a UTF-8 CSV with `date,page,clicks,impressions` and optional `ctr,position`; ordinary GSC page-total exports are not sufficient. The tool provides twelve complete calendar months of per-page heatmaps, equal 28-day click comparisons, four metric trends, investigation checklists, CSV export, and a self-contained private HTML report. Data stays in the browser; no login, telemetry, external CDN, or upload endpoint. Limits: 20 MB / 200,000 rows.

The Skill uses the same engine. After scaffolding, run `scripts/fetch_content_decay.py` (only GSC settings required), then `python3 scripts/content_decay_report.py --csv data/raw/gsc_content_decay.csv --manifest data/raw/gsc_content_decay.manifest.json --out reports/content-decay.html`. Inspect the report in a browser to verify analysis. API requests are paginated daily and tracked with a hash-bound manifest; completed requests are not a promise of exhaustive GSC rows. Missing dates remain unknown without coverage evidence, and capped days disable complete comparisons. Never publish private reports to `docs/`.

- Fetches separate 90-day GSC property-daily, page-daily, and query-detail tables so anonymized queries do not understate KPIs.
- Fetches 90-day GA4 Organic Search landing page data.
- Uses one shared 90-day GSC/GA4 window ending three days ago and validates request contracts, file hashes, and returned dates with sidecar manifests.
- Fetches date-level Organic Search `add_to_cart` and `begin_checkout` events in a separate GA4 query.
- Joins GSC pages and GA4 landing pages with normalized URLs.
- Identifies high-impact SEO opportunities:
  - High impressions and low CTR
  - Average position 8-20 keyword opportunities
  - Recent 28-day click declines
  - Organic traffic high but conversion low
  - Query/page mismatch and content gaps
- Produces Markdown and CSV reports for weekly SEO execution.
- Guides advanced GSC diagnosis with trend charts, query intent clustering, page priority, and action plans.

## Included Files

```text
SKILL.md
agents/openai.yaml
references/gsc_ga4_workflow.md
scripts/scaffold_seo_project.py
assets/project-template/
  .env.example
  .gitignore
  requirements.txt
  scripts/
    analysis_contract.py
    config.py
    ga4_contract.py
    gsc_contract.py
    fetch_gsc.py
    fetch_ga4.py
    analyze_seo.py
    weekly_report.py
```

## Install In Codex

Clone this repository into your Codex skills directory:

```bash
cd ~/.codex/skills
git clone git@github.com:owensky-dev/seo-gsc-ga4-analyst.git
```

Then start a new Codex thread and invoke:

```text
$seo-gsc-ga4-analyst
```

## Scaffold A New SEO Project

From any local project folder:

```bash
python3 ~/.codex/skills/seo-gsc-ga4-analyst/scripts/scaffold_seo_project.py --target .
```

Create `.env` from `.env.example`:

```env
SITE_NAME=example
GSC_SITE_URL=sc-domain:example.com
SITE_BASE_URL=https://www.example.com/
GA4_PROPERTY_ID=123456789
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service_account.json
```

Install dependencies and run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/fetch_gsc.py
.venv/bin/python scripts/fetch_ga4.py
.venv/bin/python scripts/analyze_seo.py
.venv/bin/python scripts/weekly_report.py
```

## Outputs

```text
data/raw/gsc_90d.csv
data/raw/gsc_daily_90d.csv
data/raw/gsc_page_daily_90d.csv
data/raw/gsc_fetch_manifest.json
data/raw/ga4_organic_landing_pages_90d.csv
data/raw/ga4_organic_funnel_90d.csv
data/raw/ga4_fetch_manifest.json
data/processed/gsc_pages_90d.csv
data/processed/gsc_keywords_90d.csv
data/processed/seo_merged_pages_90d.csv
data/processed/seo_analysis_manifest.json
reports/seo_opportunities.md
reports/seo_opportunities.csv
reports/seo_weekly_report.md
```

Site KPIs use only `gsc_daily_90d.csv`; page totals and click-decline analysis use only `gsc_page_daily_90d.csv`; query detail remains limited to keyword, intent, and content-gap analysis. GSC may legitimately omit zero-data dates, so coverage is proven by the completed fetch manifest rather than consecutive CSV rows. Header-only zero-row CSVs are also valid when the complete window has no GSC data; site KPIs become zero/no data and GSC page/keyword opportunities remain empty. A stale 14-day manifest cannot satisfy the default 90-day run, and the 28-day comparison requires a manifest-proven 56-day window.

Each validator reads a file once as bytes, verifies the hash, and parses that same snapshot; callers do not pre-read or reread validated CSV paths. `analyze_seo.py` atomically writes `seo_analysis_manifest.json`, binding the exact GSC/GA4 manifest bytes used to the processed and opportunity outputs. `weekly_report.py` fails closed if raw data was refreshed without rerunning analysis. For a historical run, pass the same `--start-date` and `--end-date` to all four commands.

## Security Notes

Keep all credentials local. Do not commit:

- `.env`
- `service_account.json`
- `private_key`
- `client_email`
- `refresh_token`
- raw GSC/GA4 exports
- generated reports with private site performance data

The project template `.gitignore` excludes these files by default.

## Recommended GitHub Topics

`codex-skill`, `seo`, `google-search-console`, `ga4`, `data-analysis`, `python`, `search-console-api`, `analytics`
