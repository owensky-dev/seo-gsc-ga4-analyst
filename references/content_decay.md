# 内容衰退雷达

## 何时使用

用户想知道哪些页面正在掉流量、查看最近 12 个完整月的页面热力图，或优先安排旧内容更新时，使用此模式。它独立于原 GSC + GA4 周报，不要求 GA4 配置，也不更改原有三份 GSC 原始表。

## 最短流程

1. 用 `scripts/scaffold_seo_project.py --target <project>` 创建项目。已有项目只补充缺失文件；不要盲目 `--force` 覆盖用户脚本。
2. 有合适 CSV 就直接分析；没有时，在项目 `.env` 中使用已有 `GSC_SITE_URL` 与 `GOOGLE_APPLICATION_CREDENTIALS`。凭据只留本机，不读取或输出密钥正文。仅在用户授权的站点上取数。
3. 项目虚拟环境安装 `requirements.txt` 后运行：

```bash
.venv/bin/python scripts/fetch_content_decay.py
python3 scripts/content_decay_report.py \
  --csv data/raw/gsc_content_decay.csv \
  --manifest data/raw/gsc_content_decay.manifest.json \
  --out reports/content-decay.html
```

4. 用浏览器打开报告；确认显示“已在本机完成分析”，检查窗口、样本和页面详情。只生成文件不等于分析验收成功。数据不足时报告缺口，不称为没有衰退。
5. 交付本地 HTML 路径与 3–5 条优先排查建议。依据页面数据与用户经验解释，不自动修改文章、不认定算法惩罚、不把首次出现的页面视为新发布。

## CSV 和采集口径

- 必需 `date,page,clicks,impressions`；可选 `ctr,position`。UTF-8，日期 YYYY-MM-DD，每行一个日期 × 页面。
- 拒绝重复键、负值、非数值、未来日期、查询/国家/设备等混合明细。保留 URL 原样，不合并查询参数或尾斜杠不同的页面。
- 不接受 GSC 普通页面汇总重建按月趋势。已有 `gsc_page_daily_90d.csv` 可导入，但只有 90 天，就明确显示其余月份未知。
- 新取数按 PT 日期、web、date/page、byPage、final，每天分页，最多 50,000 行。默认起点为最终日期所在月份向前 12 月的月初，终点是 PT 今天减 3 天，因此包含 12 个完整月和当前可用月片段。显式窗口用 `--start-date` / `--end-date` 同时指定。
- 独立清单绑定窗口、每一天、行数、文件名、SHA-256。CSV 只读取一次，浏览器对同一 UTF-8 内容验证后分析。API 完成只证明请求完成，不证明所有页面数据齐全；达到上限的日期保持不完整。采集失败不会替换上一份最终 CSV/清单。
- 没有清单时，不推测缺日为 0。两个 28 天窗口每一天都有该页显式行，才比较；有有效清单时缺行仅按“已返回数据集中的零”处理。不能把这种零表述为 Google 保证的全量零。

## 计算与输出

- 最近 12 个完整月：以数据窗口终点为锚，未完整结束的月份不入热力图；部分月份用 `*` 标记已观测数，缺失显示 `—`，不做热力上色。
- 按行与该页面完整月份的月均值比较；颜色不跨页面比较。点击/展示可切换，保留实际数字。
- 最近 28 天与前 28 天：等长窗口，以清单终点或导入数据最后一天为锚。按减少点击绝对量排序，同时展示比例、前期规模。
- “优先排查”阈值是前期至少 30 点击且下降至少 20%；这是可解释的初筛规则，不是统计显著性结论。低基数单独标记。
- CTR = 总点击 / 总展示；平均排名按展示加权；没有排名的行不补 0。详情显示四条月度趋势与排查清单。不导入查询明细、不推断查询原因。
- 导出分析 CSV、包含原始导入数据的单文件 HTML。报告属于私有数据；对外分享前由用户确认。

## 免费公开版

同一 `decay/engine.js` 用于 Skill 与公开网页，避免两套算法漂移。运行以下命令生成没有任何私有数据的单文件站点：

```bash
python3 assets/project-template/scripts/content_decay_report.py --out docs/index.html
```

公开版只读本地 CSV/清单；不登录、不上传、不存 localStorage、无统计脚本和第三方 CDN。CSP 禁止网络连接；托管平台仍会正常收到用户访问网页的网络请求。20 MB / 20 万行是第一版上限。

演示全部为 `example.com` 合成数据，必须保留演示标识。禁止把用户原始数据或带数据报告放进 `docs/`。发布前运行 Python/Node 测试并验收导入、未知日期、详情、导出、移动端和无网络连接行为。

## 官方口径

- [Search Analytics query](https://developers.google.com/webmaster-tools/v1/searchanalytics/query)：PT 日期、final 数据、请求参数与非全量行限制。
- [Getting your performance data](https://developers.google.com/webmaster-tools/v1/how-tos/all-your-data)：按天分页、50K 行上限和页面维度可能丢失数据。
