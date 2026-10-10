(function (root) {
  'use strict';
  const DAY = 86400000;
  const iso = d => new Date(d).toISOString().slice(0, 10);
  function day(s) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s) || !Number.isFinite(Date.parse(s)) || iso(s) !== s) throw Error('日期须为有效的 YYYY-MM-DD');
    return Date.parse(s);
  }
  function csvRows(text) {
    const rows = []; let row = [], cell = '', quoted = false, closed = false;
    text = text.replace(/^\uFEFF/, '');
    for (let i = 0; i <= text.length; i++) {
      const c = text[i];
      if (quoted) {
        if (c === undefined) throw Error('CSV 引号未闭合');
        if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
        else if (c === '"') { quoted = false; closed = true; }
        else cell += c;
      } else if (c === ',' || c === '\n' || c === '\r' || c === undefined) {
        row.push(cell); cell = ''; closed = false;
        if (c !== ',') {
          if (row.some(x => x !== '')) rows.push(row);
          row = [];
          if (c === '\r' && text[i + 1] === '\n') i++;
        }
      } else if (c === '"' && cell === '' && !closed) quoted = true;
      else { if (closed || c === '"') throw Error('CSV 引号格式错误'); cell += c; }
    }
    return rows;
  }
  function parse(text) {
    if (text.length > 20 * 1024 * 1024) throw Error('第一版支持 20 MB 内的 CSV，请先筛选页面范围');
    const raw = csvRows(text), headers = (raw.shift() || []).map(x => x.trim().toLowerCase());
    const allowed = ['date', 'page', 'clicks', 'impressions', 'ctr', 'position'];
    if (new Set(headers).size !== headers.length || headers.some(x => !allowed.includes(x))) throw Error('仅接受 date,page,clicks,impressions 及可选 ctr,position 列；请勿导入查询、国家或设备明细');
    for (const h of allowed.slice(0, 4)) if (!headers.includes(h)) throw Error('缺少 ' + h + ' 列。GSC 普通页面汇总不能还原按月趋势，请使用“日期 × 页面”导出');
    if (raw.length > 200000) throw Error('第一版支持 20 万行内的 CSV');
    const keys = new Set();
    const rows = raw.map((cells, i) => {
      if (cells.length !== headers.length) throw Error('第 ' + (i + 2) + ' 行列数不匹配');
      const r = Object.fromEntries(headers.map((h, j) => [h, cells[j].trim()]));
      day(r.date);
      if (!r.page || !(r.page.startsWith('/') || /^https?:\/\//i.test(r.page))) throw Error('页面须为 HTTP(S) URL 或 / 开头的路径');
      const key = JSON.stringify([r.date, r.page]);
      if (keys.has(key)) throw Error('存在重复的日期 × 页面；请先去重，不能叠加不同导出');
      keys.add(key);
      for (const k of ['clicks', 'impressions']) {
        if (!/^\d+(\.0+)?$/.test(r[k]) || !Number.isSafeInteger(Number(r[k]))) throw Error(k + ' 须为非负整数');
        r[k] = Number(r[k]);
      }
      if (r.clicks > r.impressions) throw Error('点击不能大于展示');
      r.position = r.position === undefined || r.position === '' ? null : Number(r.position);
      if (r.position !== null && (!Number.isFinite(r.position) || r.position < 0 || (r.impressions > 0 && r.position < 1))) throw Error('平均排名无效');
      r.ctr = r.impressions ? r.clicks / r.impressions : null;
      return r;
    });
    return rows.sort((a, b) => a.date.localeCompare(b.date));
  }
  async function verify(text, manifest, filename) {
    const rows = parse(text);
    if (!manifest) return { rows, coverage: null };
    if (manifest.version !== 1 || manifest.kind !== 'gsc-content-decay' || manifest.status !== 'complete') throw Error('需要本工具生成的完整采集清单；旧 GSC 三表仍可只导入页面 CSV');
    const w = manifest.window || {}, start = day(w.start), end = day(w.end);
    if (start > end || end - start > 500 * DAY) throw Error('清单时间窗口无效');
    if (manifest.request?.type !== 'web' || manifest.request?.aggregationType !== 'byPage' || manifest.request?.dataState !== 'final' || JSON.stringify(manifest.request?.dimensions) !== '["date","page"]') throw Error('清单请求口径不匹配');
    const hash = [...new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)))].map(x => x.toString(16).padStart(2, '0')).join('');
    if (manifest.sha256 !== hash || manifest.row_count !== rows.length || manifest.file !== filename) throw Error('CSV 与清单的文件名、哈希或行数不一致');
    const counts = new Map();
    for (const r of rows) { if (day(r.date) < start || day(r.date) > end) throw Error('CSV 日期超出清单'); counts.set(r.date, (counts.get(r.date) || 0) + 1); }
    if (!Array.isArray(manifest.days) || manifest.days.length !== (end - start) / DAY + 1) throw Error('采集清单缺少日期');
    const capped = [];
    for (let i = 0; i < manifest.days.length; i++) {
      const d = manifest.days[i];
      if (d.date !== iso(start + i * DAY) || d.status !== 'complete' || d.rows !== (counts.get(d.date) || 0) || typeof d.capped !== 'boolean' || (d.rows >= 50000 && !d.capped)) throw Error('逐日采集记录不匹配');
      if (d.capped) capped.push(d.date);
    }
    return { rows, coverage: { start: w.start, end: w.end, capped } };
  }
  function total(rows) {
    const clicks = rows.reduce((s, r) => s + r.clicks, 0), impressions = rows.reduce((s, r) => s + r.impressions, 0);
    const positions = rows.filter(r => r.impressions > 0);
    return { clicks, impressions, ctr: impressions ? clicks / impressions : null,
      position: impressions && positions.every(r => r.position !== null) ? positions.reduce((s, r) => s + r.position * r.impressions, 0) / impressions : null };
  }
  function period(rows, start, end, coverage) {
    const selected = rows.filter(r => r.date >= start && r.date <= end), days = (day(end) - day(start)) / DAY + 1;
    const covered = coverage && coverage.start <= start && coverage.end >= end && !coverage.capped.some(d => d >= start && d <= end);
    const complete = !!covered || (!coverage && selected.length === days);
    return { ...total(selected), complete, observedDays: selected.length, days };
  }
  function analyze(rows, coverage, now = iso(Date.now())) {
    if (!rows.length && !coverage) throw Error('CSV 没有数据，也没有可验证的时间窗口');
    const end = coverage?.end || rows.at(-1).date, endTime = day(end);
    if (end >= now) throw Error('包含今天或未来日期，请使用已完成的历史数据');
    const endDate = new Date(endTime), nextDay = new Date(endTime + DAY);
    const monthEnd = nextDay.getUTCDate() === 1 ? new Date(Date.UTC(endDate.getUTCFullYear(), endDate.getUTCMonth() + 1, 1)) : new Date(Date.UTC(endDate.getUTCFullYear(), endDate.getUTCMonth(), 1));
    const months = Array.from({ length: 12 }, (_, i) => {
      const y = monthEnd.getUTCFullYear(), m = monthEnd.getUTCMonth() - 12 + i;
      const start = iso(Date.UTC(y, m, 1)), end = iso(Date.UTC(y, m + 1, 1) - DAY);
      return { start, end, label: start.slice(0, 7) };
    });
    const currentStart = iso(endTime - 27 * DAY), previousEnd = iso(endTime - 28 * DAY), previousStart = iso(endTime - 55 * DAY);
    const groups = new Map();
    for (const r of rows) { if (!groups.has(r.page)) groups.set(r.page, []); groups.get(r.page).push(r); }
    const pages = [...groups].map(([page, data]) => {
      const current = period(data, currentStart, end, coverage), previous = period(data, previousStart, previousEnd, coverage);
      const comparable = current.complete && previous.complete;
      const loss = comparable ? previous.clicks - current.clicks : null;
      const change = comparable && previous.clicks > 0 ? (current.clicks - previous.clicks) / previous.clicks : null;
      const monthly = months.map(m => period(data, m.start, m.end, coverage));
      const annual = total(data.filter(r => r.date >= months[0].start && r.date <= months[11].end));
      let status = '待补数据';
      if (comparable) status = previous.clicks < 30 ? '低基数 / 新增信号' : loss > 0 && change <= -0.2 ? '优先排查' : loss > 0 ? '小幅下降' : '稳定 / 增长';
      return { page, data, monthly, annual, current, previous, comparable, loss, change, status };
    });
    pages.sort((a, b) => (b.loss ?? -Infinity) - (a.loss ?? -Infinity) || b.annual.clicks - a.annual.clicks || a.page.localeCompare(b.page));
    return { months, pages, end, currentStart, previousEnd, previousStart, coverage };
  }
  function guidance(p) {
    if (!p.comparable) return ['先补齐两个 28 天窗口的数据，再判断是否下滑。'];
    const advice = [];
    if (p.previous.clicks < 30) advice.push('前期点击不足 30，先观察实际点击规模，不按降幅百分比直接排高优先级。');
    if (p.loss <= 0) advice.push('当前未观察到点击净下降，继续监测，不必为了更新而重写。');
    else {
      advice.push('先排查季节性、页面迁移和改版；这里是下滑信号，不是原因判定。');
      if (p.current.impressions < p.previous.impressions) advice.push('展示减少：核对查询需求、收录状态、页面覆盖与关键词排名。');
      if (p.current.ctr !== null && p.previous.ctr !== null && p.current.ctr < p.previous.ctr) advice.push('CTR 下降：核对相同查询与设备下的标题、摘要和搜索结果变化。');
      if (p.current.position !== null && p.previous.position !== null && p.current.position > p.previous.position) advice.push('平均排名变差：进一步按查询拆分，检查竞争页面、内容时效和内链。');
      advice.push('记录修改日期与假设，修改后用同口径窗口复查；可补充去年同期，但本工具不自动认定季节性。');
    }
    return advice;
  }
  function csvCell(value) {
    let s = value === null || value === undefined ? '' : String(value);
    if (/^[\s]*[=+@-]/.test(s) && typeof value !== 'number') s = "'" + s;
    return '"' + s.replace(/"/g, '""') + '"';
  }
  function exportCSV(model) {
    const rows = [['page', 'previous_28d_clicks', 'current_28d_clicks', 'lost_clicks', 'change_ratio', 'status', 'comparison_end', ...model.months.flatMap(m => [m.label + '_clicks_observed', m.label + '_complete'])]];
    for (const p of model.pages) rows.push([p.page, p.comparable ? p.previous.clicks : null, p.comparable ? p.current.clicks : null, p.loss, p.change, p.status, model.end, ...p.monthly.flatMap(m => [m.complete || m.observedDays ? m.clicks : null, m.complete])]);
    return '\uFEFF' + rows.map(r => r.map(csvCell).join(',')).join('\r\n');
  }
  const api = { DAY, iso, day, csvRows, parse, verify, total, period, analyze, guidance, exportCSV };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Decay = api;
})(globalThis);
