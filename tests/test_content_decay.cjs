const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createHash, webcrypto } = require('node:crypto');
if (!globalThis.crypto) globalThis.crypto = webcrypto;
const D = require('../assets/project-template/decay/engine.js');
const header = 'date,page,clicks,impressions,position\n';
function daily(start, count, page = '/a', clicks = 10) {
  return Array.from({ length: count }, (_, i) => [D.iso(D.day(start) + i * D.DAY), page, typeof clicks === 'function' ? clicks(i) : clicks, 100, 5].join(',')).join('\n');
}
function manifest(text, start, end) {
  const rows = D.parse(text);
  return { version: 1, kind: 'gsc-content-decay', status: 'complete', file: 'data.csv',
    window: { start, end }, request: { type: 'web', aggregationType: 'byPage', dataState: 'final', dimensions: ['date', 'page'] },
    sha256: createHash('sha256').update(text).digest('hex'), row_count: rows.length,
    days: Array.from({ length: (D.day(end) - D.day(start)) / D.DAY + 1 }, (_, i) => {
      const date = D.iso(D.day(start) + i * D.DAY);
      return { date, status: 'complete', rows: rows.filter(r => r.date === date).length, capped: false };
    }) };
}
test('RFC CSV quotes, BOM, CRLF, newline and duplicate guards', () => {
  const rows = D.parse('\uFEFF' + header + '2026-01-01,"/path,a""b\nc",1,2,3\r\n');
  assert.equal(rows[0].page, '/path,a"b\nc');
  assert.throws(() => D.parse(header + daily('2026-01-01', 1) + '\n' + daily('2026-01-01', 1)), /重复/);
  assert.throws(() => D.parse(header + '2026-02-30,/a,1,2,3'), /日期/);
  assert.throws(() => D.parse(header + '2026-01-01,/a,1,,3'), /整数/);
  assert.throws(() => D.parse(header + '2026-01-01,/a,3,2,3'), /大于/);
  assert.throws(() => D.parse(header + '2026-01-01,javascript:alert(1),1,2,3'), /HTTP/);
  assert.throws(() => D.parse('page,clicks,impressions\n/a,1,2'), /date/);
  assert.throws(() => D.parse('date,page,query,clicks,impressions\n2026-01-01,/a,a,1,2'), /明细/);
});
test('56 explicit dates permit equal 28-day comparison, 55 do not', () => {
  const rows = D.parse(header + daily('2026-08-01', 56, '/a', i => i < 28 ? 20 : 10));
  let p = D.analyze(rows, null, '2026-10-10').pages[0];
  assert.equal(p.previous.clicks, 560); assert.equal(p.current.clicks, 280);
  assert.equal(p.loss, 280); assert.equal(p.change, -0.5); assert.equal(p.status, '优先排查');
  p = D.analyze(rows.slice(1), null, '2026-10-10').pages[0];
  assert.equal(p.loss, null); assert.equal(p.status, '待补数据');
});
test('window anchored to manifest even if last day has no rows, cap disables comparison', async () => {
  const text = header + daily('2026-08-01', 28), m = manifest(text, '2026-08-01', '2026-09-25');
  const verified = await D.verify(text, m, 'data.csv');
  let result = D.analyze(verified.rows, verified.coverage, '2026-10-10');
  assert.equal(result.end, '2026-09-25'); assert.equal(result.pages[0].current.clicks, 0); assert.equal(result.pages[0].loss, 280);
  m.days[30].capped = true;
  const capped = await D.verify(text, m, 'data.csv');
  result = D.analyze(capped.rows, capped.coverage, '2026-10-10'); assert.equal(result.pages[0].loss, null);
});
test('manifest rejects tampering, wrong file, incomplete days and wrong dimensions', async () => {
  const text = '\uFEFF' + header.replace(/\n/g, '\r\n') + daily('2026-08-01', 56), m = manifest(text, '2026-08-01', '2026-09-25');
  await D.verify(text, m, 'data.csv');
  await assert.rejects(D.verify(text + '\n', m, 'data.csv'), /哈希/);
  await assert.rejects(D.verify(text, m, 'wrong.csv'), /文件名/);
  await assert.rejects(D.verify(text, { ...m, days: m.days.slice(1) }, 'data.csv'), /缺少日期/);
  await assert.rejects(D.verify(text, { ...m, request: { ...m.request, dimensions: ['page', 'query'] } }, 'data.csv'), /口径/);
});
test('empty complete manifest has no fabricated pages; empty CSV alone is not evidence', async () => {
  const text = header, m = manifest(text, '2026-08-01', '2026-09-25');
  const v = await D.verify(text, m, 'data.csv');
  assert.equal(D.analyze(v.rows, v.coverage, '2026-10-10').pages.length, 0);
  assert.throws(() => D.analyze([], null), /没有数据/);
});
test('twelve full months exclude partial end month and respect leap February', () => {
  const rows = D.parse(header + daily('2024-03-01', 9));
  const result = D.analyze(rows, null, '2024-03-20');
  assert.equal(result.months.length, 12); assert.equal(result.months[11].end, '2024-02-29');
  assert.equal(result.pages[0].monthly[11].complete, false);
  const full = D.analyze(D.parse(header + '2024-03-31,/a,1,2,3'), null, '2024-04-04');
  assert.equal(full.months[11].end, '2024-03-31');
});
test('CTR recalculated, position impression-weighted; unknown position retained', () => {
  const total = D.total([{ clicks: 1, impressions: 10, position: 2 }, { clicks: 2, impressions: 90, position: 10 }]);
  assert.equal(total.ctr, 0.03); assert.equal(total.position, 9.2);
  assert.equal(D.total([{ clicks: 1, impressions: 10, position: null }]).position, null);
});
test('absolute loss ranks meaningful declines before tiny-base percentages', () => {
  const text = header + daily('2026-08-01', 56, '/big', i => i < 28 ? 20 : 10) + '\n' + daily('2026-08-01', 56, '/tiny', i => i === 0 ? 2 : i === 28 ? 1 : 0);
  const pages = D.analyze(D.parse(text), null, '2026-10-10').pages;
  assert.equal(pages[0].page, '/big'); assert.equal(pages[1].status, '低基数 / 新增信号');
});
test('exports preserve missing comparisons and future dates are rejected', () => {
  const model = D.analyze(D.parse(header + daily('2026-08-01', 1)), null, '2026-10-10');
  assert.match(D.exportCSV(model), /待补数据/); assert.match(D.exportCSV(model), /"\/a","","","",""/);
  assert.throws(() => D.analyze(D.parse(header + daily('2026-10-10', 1)), null, '2026-10-10'), /未来/);
});
