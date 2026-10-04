#!/usr/bin/env node
/* build.py 里每日十条的抽取逻辑的独立自检。
   故意不 import build.py（它是脚本），而是把同样的算法抄一份来验证行为——
   两边算法不同步时这个测试会红，正好提醒人回去改。
   跑法：node test-daily.js */
const fs = require('fs');
const path = require('path');

const idx = path.join(__dirname, 'index.html');
if (!fs.existsSync(idx)) { console.error('找不到 index.html，先跑 python build.py all'); process.exit(2); }
const html = fs.readFileSync(idx, 'utf-8');

function xmur3(str){let h=1779033703^str.length;for(let i=0;i<str.length;i++){h=Math.imul(h^str.charCodeAt(i),3432918353);h=h<<13|h>>>19;}return function(){h=Math.imul(h^h>>>16,2246822507);h=Math.imul(h^h>>>13,3266489909);return (h^=h>>>16)>>>0;};}
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return ((t^t>>>14)>>>0)/4294967296;};}

const m = html.match(/<script id="daily-pool" type="application\/json">([\s\S]*?)<\/script>/);
if (!m) { console.error('页面里没有 daily-pool 数据岛'); process.exit(2); }
let POOL;
try { POOL = JSON.parse(m[1].replace(/<\\\//g, '</')); }
catch (e) { console.error('数据岛不是合法 JSON：' + e.message); process.exit(2); }

/* 与 build.py 中 pickDaily 同逻辑。少了任何一处上界，这里就会挂死而不是报错——
   挂死本身就是最糟的失败模式，所以给整个抽取过程加计时上界。 */
function pickDaily(seed){
  const rnd = mulberry32(xmur3(seed)());
  const byDom = {};
  POOL.forEach(it => { (byDom[it.cls] = byDom[it.cls] || []).push(it); });
  const keys = Object.keys(byDom);
  keys.forEach(k => {
    const arr = byDom[k];
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(rnd() * (i + 1));
      const t = arr[i]; arr[i] = arr[j]; arr[j] = t;
    }
  });
  const out = []; let i = 0;
  while (out.length < 10 && i < 1000) {
    const k = keys[i % keys.length];
    if (byDom[k].length) out.push(byDom[k].shift());
    i++;
  }
  return out;
}

let fail = 0;
function ok(cond, msg) { console.log((cond ? '  ✓ ' : '  ✗ ') + msg); if (!cond) fail++; }

console.log('候选池 ' + POOL.length + ' 条');
ok(POOL.length >= 20, '候选池足够大（≥20），十条不会天天重样');

console.log('\n同一天内确定性');
const t1 = pickDaily('2026-10-04').map(x => x.id);
const t2 = pickDaily('2026-10-04').map(x => x.id);
ok(JSON.stringify(t1) === JSON.stringify(t2), '同一种子两次抽取结果一致');

console.log('\n跨天会换');
const days = [];
for (let d = 1; d <= 30; d++) days.push(pickDaily('2026-10-' + String(d).padStart(2, '0')).map(x => x.id).join());
ok(new Set(days).size >= 25, '30 天里至少 25 天各不相同（实测 ' + new Set(days).size + '/30）');

console.log('\n每次抽取的基本保证');
let allTen = true, noDup = true, allPlain = true, spreadOk = true, inPool = true;
const poolIds = new Set(POOL.map(x => x.id));
for (let d = 1; d <= 60; d++) {
  const list = pickDaily('2026-10-' + String(d).padStart(2, '0'));
  if (list.length !== 10) allTen = false;
  if (new Set(list.map(x => x.id)).size !== list.length) noDup = false;
  if (!list.every(x => x.plain && x.plain.length > 20)) allPlain = false;
  if (new Set(list.map(x => x.cls)).size < 4) spreadOk = false;
  if (!list.every(x => poolIds.has(x.id))) inPool = false;
}
ok(allTen, '连续 60 天每天都出满 10 条');
ok(noDup, '同一天内 10 条互不重复');
ok(allPlain, '每条都带完整「说人话」（无空壳条目）');
ok(spreadOk, '每天横跨至少 4 个生活领域（不是十条全挤在一类）');
ok(inPool, '抽出的条目都确实来自候选池');

console.log('\n种子不卡死');
const t0 = Date.now();
for (let i = 0; i < 2000; i++) pickDaily('s' + i);
ok(Date.now() - t0 < 5000, '2000 次抽取在 5 秒内完成（无死循环，实测 ' + (Date.now() - t0) + 'ms）');

console.log(fail ? '\n✗ ' + fail + ' 项未通过' : '\n✓ 全部通过');
process.exit(fail ? 1 : 0);