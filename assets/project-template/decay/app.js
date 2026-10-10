(() => {
  'use strict';
  const $ = id => document.getElementById(id), D = window.Decay;
  const fmt = v => v === null ? '—' : Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 1 });
  const pct = v => v === null ? '—' : (v * 100).toFixed(1) + '%';
  let model = null, payload = null, pageIndex = 0, generation = 0;
  function element(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
  function message(text, error = false) { $('message').textContent = text; $('message').className = error ? 'error' : ''; }
  function download(name, text, type) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = element('a'); a.href = url; a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function demoData() {
    const now = new Date(), end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) - 3 * D.DAY);
    const start = new Date(Date.UTC(end.getUTCFullYear() - 1, end.getUTCMonth(), 1));
    const names = ['guides/shower-door-size', 'collections/heated-towel-racks', 'blog/bathroom-layout', 'guides/glass-care', 'products/compact-rail', 'blog/new-materials'];
    const rows = ['date,page,clicks,impressions,position'];
    for (let t = +start; t <= +end; t += D.DAY) for (let i = 0; i < names.length; i++) {
      const age = Math.round((t - start) / D.DAY), recent = t > +end - 28 * D.DAY;
      const clicks = i === 0 ? Math.max(2, 35 - Math.floor(age / 12)) : i === 1 ? (recent ? 12 : 25) : i === 2 ? 5 + Math.floor(age / 25) : i === 3 ? 8 + Math.floor(4 * Math.sin(age / 23)) : i === 4 ? (age % 4 ? 0 : 1) : age < 260 ? 0 : 4 + Math.floor((age - 260) / 20);
      const impressions = clicks * (i === 1 && recent ? 22 : 16) + 20;
      rows.push([D.iso(t), 'https://example.com/' + names[i], clicks, impressions, i === 0 ? (3 + age / 35).toFixed(2) : i === 1 && recent ? 11 : 7].join(','));
    }
    return rows.join('\n');
  }
  async function load(input, token = ++generation) {
    model = null; payload = null;
    $('results').hidden = true; $('detail').hidden = true;
    message('正在本地校验与分析…');
    try {
      const { rows, coverage } = await D.verify(input.text, input.manifest, input.filename);
      const result = D.analyze(rows, coverage);
      if (token !== generation) return;
      model = result; payload = input; pageIndex = 0; $('seed').textContent = 'null';
      $('search').value = ''; $('min-clicks').value = '0';
      $('source-label').textContent = input.demo ? '合成演示数据 · 非真实站点' : '本地数据 / ' + input.filename;
      $('results').hidden = false;
      message(input.demo ? '演示已载入。上传你的 CSV 即可替换，不会与示例混用。' : '已在本机完成分析，没有上传数据。');
      $('coverage').textContent = `最近窗口 ${model.currentStart} 至 ${model.end}；前期 ${model.previousStart} 至 ${model.previousEnd}。` + (coverage ? `采集清单已验证。${coverage.capped.length ? coverage.capped.length + ' 天触及 API 行数上限，相关比较停用。' : ''}缺行按“已返回数据集中的 0”处理，不代表 Google 保证全量。` : '未提供采集清单：只有页面明确覆盖的日期参与完整比较，缺日不补 0。');
      $('stats').replaceChildren();
      const comparable = model.pages.filter(p => p.comparable), lost = comparable.filter(p => p.loss > 0).reduce((s, p) => s + p.loss, 0);
      const stats = [[model.pages.length, '已导入页面', '只包含 CSV 中出现的 URL'], [comparable.length, '可比较页面', '两个完整的 28 天窗口'], [model.pages.filter(p => p.status === '优先排查').length, '优先排查', '前期 ≥30 点击且下降 ≥20%'], [lost, '下降页面减少的点击', '不抵扣增长页，不是全站净损失']];
      for (const [value, title, note] of stats) { const card = element('div', undefined, 'stat'); card.append(element('span', title), element('strong', fmt(value)), element('small', note)); $('stats').append(card); }
      renderTable();
    } catch (error) { if (token === generation) message(error.message, true); }
  }
  async function importFiles() {
    const token = ++generation, file = $('csv-file').files[0], manifest = $('manifest-file').files[0];
    if (!file) { message('请先选择 CSV'); return; }
    $('results').hidden = true; model = null; payload = null;
    try {
      if (file.size > 20 * 1024 * 1024 || (manifest && manifest.size > 1024 * 1024)) throw Error('文件过大：CSV 上限 20 MB，清单上限 1 MB');
      const text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(await file.arrayBuffer());
      const input = { text, filename: file.name, manifest: manifest ? JSON.parse(await manifest.text()) : null };
      if (token === generation) await load(input, token);
    } catch (error) { if (token === generation) message('导入失败：' + error.message, true); }
  }
  function filtered() {
    const query = $('search').value.toLowerCase(), min = Math.max(0, Number($('min-clicks').value) || 0);
    const pages = model.pages.filter(p => p.page.toLowerCase().includes(query) && (min === 0 || (p.previous.complete && p.previous.clicks >= min)));
    if ($('sort').value === 'total') pages.sort((a, b) => b.annual.clicks - a.annual.clicks);
    return pages;
  }
  function renderTable() {
    if (!model) return;
    const metric = $('metric').value, pages = filtered(), maxPage = Math.max(0, Math.ceil(pages.length / 50) - 1);
    pageIndex = Math.min(pageIndex, maxPage);
    const head = element('tr');
    for (const text of ['页面 / 排查信号', ...model.months.map(m => m.label), '12 月已观测合计', '前 28 天点击', '近 28 天点击', '减少点击', '变化']) head.append(element('th', text));
    $('head').replaceChildren(head); $('body').replaceChildren();
    for (const p of pages.slice(pageIndex * 50, pageIndex * 50 + 50)) {
      const tr = element('tr'), cell = element('td'), button = element('button', p.page.replace(/^https?:\/\/[^/]+/, ''), 'page-button');
      button.title = p.page; button.addEventListener('click', () => showDetail(p));
      cell.append(button, element('span', p.status, 'signal')); tr.append(cell);
      const full = p.monthly.filter(m => m.complete), average = full.length ? full.reduce((s, m) => s + m[metric], 0) / full.length : 0;
      for (const m of p.monthly) {
        const td = element('td', m.complete ? fmt(m[metric]) : m.observedDays ? fmt(m[metric]) + '*' : '—');
        if (m.complete) { const ratio = average ? m[metric] / average : 0, light = 98 - Math.min(ratio, 2.5) * 21; td.style.backgroundColor = `hsl(151 28% ${light}%)`; td.style.color = light < 58 ? 'white' : '#254638'; td.title = `完整窗口；该页月均值 ${fmt(average)}，本月为 ${average ? ratio.toFixed(2) : '0'} 倍`; }
        else { td.className = 'partial'; td.title = `部分或未知：已观测 ${m.observedDays} / ${m.days} 天；不用于热力色比较`; }
        tr.append(td);
      }
      for (const v of [fmt(p.annual[metric]), p.comparable ? fmt(p.previous.clicks) : '—', p.comparable ? fmt(p.current.clicks) : '—', fmt(p.loss), pct(p.change)]) tr.append(element('td', v));
      tr.lastChild.className = p.change < 0 ? 'loss' : 'gain'; $('body').append(tr);
    }
    if (!pages.length) { const cell = element('td', '没有符合条件的页面'); cell.colSpan = 18; const row = element('tr'); row.append(cell); $('body').append(row); }
    $('count').textContent = `${pages.length} 个页面 · 第 ${pageIndex + 1} / ${maxPage + 1} 页 · 每页 50 条`;
    $('prev').disabled = pageIndex === 0; $('next').disabled = pageIndex >= maxPage;
  }
  function chart(p, key, label) {
    const card = element('div', undefined, 'chart'); card.append(element('h3', label));
    const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 460 150'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', label + '按月趋势');
    const values = p.monthly.map(m => m.complete ? m[key] : null), present = values.filter(v => v !== null), max = Math.max(...present, 1);
    function shape(tag, attrs, text) { const node = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v); if (text !== undefined) node.textContent = text; svg.append(node); return node; }
    shape('line', { x1: 35, x2: 448, y1: 118, y2: 118, stroke: '#dce5df' });
    shape('text', { x: 0, y: 20, fill: '#6a7a70', 'font-size': 10 }, key === 'ctr' ? pct(max) : fmt(max));
    let segment = [];
    function draw() { if (segment.length) shape('polyline', { points: segment.join(' '), fill: 'none', stroke: '#28735a', 'stroke-width': 2 }); segment = []; }
    values.forEach((v, i) => {
      const x = 40 + i * 36.5;
      if (v === null) { draw(); return; }
      const y = 118 - v / max * 98; segment.push(`${x},${y}`);
      const dot = shape('circle', { cx: x, cy: y, r: 3, fill: '#28735a' });
      const title = document.createElementNS(ns, 'title'); title.textContent = model.months[i].label + ': ' + (key === 'ctr' ? pct(v) : fmt(v)); dot.append(title);
    }); draw();
    shape('text', { x: 35, y: 143, fill: '#6a7a70', 'font-size': 10 }, model.months[0].label);
    shape('text', { x: 402, y: 143, fill: '#6a7a70', 'font-size': 10 }, model.months[11].label);
    card.append(svg, element('p', key === 'position' ? '排名数字越小越好；缺数据处断开。' : '只绘制完整月份；悬停圆点查看数值。'));
    return card;
  }
  function showDetail(p) {
    $('detail').hidden = false; $('detail-title').textContent = p.page;
    $('detail-compare').textContent = p.comparable ? `前 28 天 ${fmt(p.previous.clicks)} 点击 → 近 28 天 ${fmt(p.current.clicks)} 点击 · 变化 ${pct(p.change)} · ${p.status}` : '两个 28 天窗口尚未完整，不计算下滑幅度。';
    $('charts').replaceChildren(...[['clicks', '点击'], ['impressions', '展示'], ['ctr', 'CTR'], ['position', '平均排名']].map(([key, title]) => chart(p, key, title)));
    $('advice').replaceChildren(...D.guidance(p).map(text => element('li', text)));
    $('detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  $('csv-file').addEventListener('change', importFiles); $('manifest-file').addEventListener('change', importFiles);
  $('demo').addEventListener('click', () => { $('csv-file').value = ''; $('manifest-file').value = ''; load({ text: demoData(), filename: 'synthetic-demo.csv', manifest: null, demo: true }); });
  $('sample').addEventListener('click', () => download('synthetic-demo.csv', demoData(), 'text/csv;charset=utf-8'));
  for (const id of ['search', 'min-clicks', 'metric', 'sort']) $(id).addEventListener('input', () => { pageIndex = 0; renderTable(); });
  $('prev').addEventListener('click', () => { pageIndex--; renderTable(); }); $('next').addEventListener('click', () => { pageIndex++; renderTable(); });
  $('close-detail').addEventListener('click', () => { $('detail').hidden = true; });
  $('export-csv').addEventListener('click', () => { if (model) download('content-decay-analysis.csv', D.exportCSV(model), 'text/csv;charset=utf-8'); });
  $('export-html').addEventListener('click', () => {
    if (!payload) return;
    const clone = document.documentElement.cloneNode(true);
    clone.querySelector('#seed').textContent = JSON.stringify(payload).replace(/</g, '\\u003c');
    for (const id of ['body', 'head', 'stats', 'charts', 'advice']) clone.querySelector('#' + id).replaceChildren();
    clone.querySelector('#results').hidden = true; clone.querySelector('#detail').hidden = true;
    download('content-decay-private-report.html', '<!doctype html>\n' + clone.outerHTML, 'text/html;charset=utf-8');
    message('已保存含本次数据的离线报告。分享前请确认其中没有私有站点信息。');
  });
  $('clear').addEventListener('click', () => { generation++; model = null; payload = null; $('seed').textContent = 'null'; $('csv-file').value = ''; $('manifest-file').value = ''; $('results').hidden = true; for (const id of ['body', 'head', 'stats', 'charts', 'advice']) $(id).replaceChildren(); message('本次数据已清除。已下载到磁盘的报告不会被删除。'); });
  let seed = JSON.parse($('seed').textContent); if (seed) load(seed); seed = null;
})();
