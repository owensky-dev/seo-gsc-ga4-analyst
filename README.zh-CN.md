# SEO GSC GA4 Analyst

[![CI](https://github.com/owensky-dev/seo-gsc-ga4-analyst/actions/workflows/ci.yml/badge.svg)](https://github.com/owensky-dev/seo-gsc-ga4-analyst/actions/workflows/ci.yml)

[English README](README.md)

一个给 Codex 使用的 SEO 数据分析 Skill：将 Google Search Console（GSC）的搜索表现与 Google Analytics 4（GA4）的自然流量和关键行为合并，产出可以直接进入运营排期的 SEO 周报和行动清单。

很多 SEO 复盘并不缺数据，缺的是从数据到决策的过程：这周该改哪个页面、先补哪类内容、流量问题究竟在搜索曝光还是站内承接。本 Skill 让 Codex 在本地自动完成取数、关联、诊断与报告，把 SEO 从“关键词排名汇总”变成与转化路径一起讨论的增长工作。

## 能解决什么问题

- 拉取近 90 天 GSC 的关键词、页面、点击、展示、CTR 和平均排名数据。
- 拉取近 90 天 GA4 Organic Search 落地页、Sessions、转化与收入数据。
- 单独保留按日期的 `add_to_cart` 和 `begin_checkout` 漏斗数据，避免用汇总数字掩盖漏斗变化。
- 按标准化 URL 合并 GSC 页面与 GA4 落地页，判断问题在搜索端还是页面承接端。
- 自动识别高展示低 CTR、排名 8–20 名、近期点击下滑、自然流量高但转化弱、关键词与页面不匹配及内容缺口。
- 输出 Markdown、CSV 周报与机会清单，并提供 P0 / P1 / P2 优先级行动建议。

## 适合谁

- 独立站老板：把“SEO 做得怎么样”变成清楚的经营判断。
- 运营负责人：少花时间导表、筛表，把精力放在页面优化、内容策划和项目推进。
- SEO 与内容团队：让标题、内容、内链等每一次优化都有前后数据可以追踪。

## 一次性准备：开通 Google Cloud API

> 只读分析时，服务账号只需要访问数据的权限；请始终把密钥留在本地，不要提交到 Git。

1. 打开 [Google Cloud Console](https://console.cloud.google.com/)，创建或选择一个项目。
2. 进入“API 和服务 → 库”，启用以下 API：
   - Google Search Console API
   - Google Analytics Data API
   - Google Analytics Admin API
3. 进入“API 和服务 → 凭据 → 创建凭据 → 服务账号”，创建服务账号。
4. 在该服务账号的“密钥”中，选择“添加密钥 → 创建新密钥 → JSON”，下载 JSON 文件并保存到本地安全位置。
5. 复制 JSON 文件中的 `client_email`，它通常类似：

   ```text
   your-service-account@your-project.iam.gserviceaccount.com
   ```

6. 用这个服务账号邮箱分别授权：
   - 在 GSC 对应资源的“用户和权限”中添加访问权限；只读分析可使用读取权限。
   - 在 GA4 对应媒体资源的“访问权限管理”中添加访问权限；可使用 Viewer 或 Analyst。

常见问题：GSC 若提示“找不到电子邮件地址”，先确认填写的是 JSON 内的 `client_email`；刚创建的服务账号有时需要等待几分钟后才可添加。GSC 中的资源地址必须与 `GSC_SITE_URL` 完全一致。

## 安装到 Codex

将仓库克隆到 Codex 的 skills 目录：

```bash
cd ~/.codex/skills
git clone git@github.com:owensky-dev/seo-gsc-ga4-analyst.git
```

然后开启新的 Codex 任务并调用：

```text
$seo-gsc-ga4-analyst
```

例如：

```text
为我的独立站创建 GSC + GA4 自然流量分析，拉取近 90 天数据，输出本周 SEO 优先级和可执行动作。
```

## 创建并运行分析项目

在任意本地项目目录执行：

```bash
python3 ~/.codex/skills/seo-gsc-ga4-analyst/scripts/scaffold_seo_project.py --target .
```

将 `.env.example` 复制为 `.env`，填写站点与本地凭证路径：

```env
SITE_NAME=example
GSC_SITE_URL=sc-domain:example.com
SITE_BASE_URL=https://www.example.com/
GA4_PROPERTY_ID=123456789
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service_account.json
```

安装依赖并依次运行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/fetch_gsc.py
.venv/bin/python scripts/fetch_ga4.py
.venv/bin/python scripts/analyze_seo.py
.venv/bin/python scripts/weekly_report.py
```

## 会得到什么

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

周报应优先回答这些实际问题：

| 信号 | 优先动作 |
| --- | --- |
| 高展示、低点击 | 重写 Title 和 Meta Description，改善搜索结果页吸引力。 |
| 排名 8–20 名 | 补充内容、增加内链、完善 FAQ，争取进入首页。 |
| 最近 28 天点击下滑 | 排查内容时效性、竞品覆盖、内链与页面体验。 |
| 自然流量高、加购或结账弱 | 检查首屏 CTA、商品卡、信任元素、速度及加购到结账路径。 |
| 关键词和页面不匹配 | 调整页面承接，或创建集合页、购买指南、对比页或新内容页。 |

最终目标不是一堆数字，而是一张行动表：本周先改什么、谁来做、改完观察什么指标，以及两周后如何复盘。

## 每周自动运行

首次跑通后，可以直接让 Codex 设置固定任务。例如：

```text
以后每周一上午 9 点，自动运行 GSC + GA4 SEO 分析，并生成本周 SEO 周报。
报告先给结论，再列出本周优先处理的页面、关键词和执行动作。
```

建议每周对比最近 28 天与前一个 28 天，优先查看：点击下滑页面、高展示低 CTR 关键词、排名 8–20 名机会，以及自然流量高但加购或结账弱的落地页。每次优化都记录 URL、改动日期、改动字段、假设与优化前后指标，形成可复盘的 SEO 实验台账。

## 安全说明

所有凭证与站点数据仅保留在本地。不要提交以下内容：

- `.env`
- `service_account.json`
- `private_key`
- `client_email`
- `refresh_token`
- 原始 GSC / GA4 导出数据
- 含私有站点表现的生成报告

项目模板的 `.gitignore` 已默认忽略这些本地敏感文件和数据目录。

## 常见排查

- **GSC 返回 403 或无数据：** 确认服务账号已被加入 Search Console，且 `GSC_SITE_URL` 与已验证资源完全一致。仅在同时拥有两个资源时，再尝试 `https://example.com/` 与 `sc-domain:example.com` 两种格式。
- **GA4 权限错误：** 将服务账号邮箱加入对应 GA4 Property，授予 Viewer 或 Analyst 权限。
- **GA4 收入为 0：** 这可能是电商事件埋点或归因设置问题，不必然代表 SEO 没有价值。
- **GA4 落地页为 `(not set)`：** 应将其单独处理或过滤，以保留可执行的页面级建议。

## 仓库结构

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

## 推荐 GitHub Topics

`codex-skill`, `seo`, `google-search-console`, `ga4`, `data-analysis`, `python`, `search-console-api`, `analytics`
