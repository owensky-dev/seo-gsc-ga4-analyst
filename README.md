# SEO GSC GA4 Analyst

[![CI](https://github.com/owensky-dev/seo-gsc-ga4-analyst/actions/workflows/ci.yml/badge.svg)](https://github.com/owensky-dev/seo-gsc-ga4-analyst/actions/workflows/ci.yml)

Codex skill for building a local SEO data analysis workflow with Google Search Console API and GA4 Data API.

中文说明请见 [README.zh-CN.md](README.zh-CN.md)。

It helps Codex scaffold a Python project, fetch GSC and GA4 Organic Search data, merge both sources by landing page, diagnose SEO opportunities, and generate execution-focused SEO reports.

## What It Does

- Fetches 90-day Google Search Console search performance data.
- Fetches 90-day GA4 Organic Search landing page data.
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
    config.py
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
data/raw/ga4_organic_landing_pages_90d.csv
data/raw/ga4_organic_funnel_90d.csv
data/processed/gsc_pages_90d.csv
data/processed/gsc_keywords_90d.csv
data/processed/seo_merged_pages_90d.csv
reports/seo_opportunities.md
reports/seo_opportunities.csv
reports/seo_weekly_report.md
```

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
