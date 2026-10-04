#!/usr/bin/env node
/* index.html 的安全自检：确认渲染产物里没有可执行的注入面。
   跑法：node test-security.js  （需要先 python build.py all -o index.html）
   背景：上游 markdown 是外部输入，而 build.py 把它渲染进单文件 HTML，
   任何一个没转义干净的引号都会变成可执行属性。所以这些项必须每次构建后复查。 */
const fs = require('fs');
const path = require('path');

const idx = path.join(__dirname, 'index.html');
if (!fs.existsSync(idx)) { console.error('找不到 index.html'); process.exit(2); }
const html = fs.readFileSync(idx, 'utf-8');

let fail = 0;
function ok(cond, msg, detail) {
  console.log((cond ? '  ✓ ' : '  ✗ ') + msg + (detail ? ' — ' + detail : ''));
  if (!cond) fail++;
}

/* 取所有标签的裸文本（去掉 script/style），用于「能不能执行」的判定 */
const body = html.replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<style[\s\S]*?<\/style>/gi, '');

console.log('外链安全');
const blank = [...body.matchAll(/<a\b[^>]*>/g)].map(m => m[0]);
const targets = blank.filter(t => /target\s*=/.test(t));
const noNoopener = targets.filter(t => !/rel\s*=\s*["'][^"']*noopener/.test(t));
ok(noNoopener.length === 0, '所有 target=_blank 都带 noopener',
   noNoopener.length ? noNoopener.length + ' 个缺失：' + noNoopener[0] : targets.length + ' 个外链全部合规');
const noReferrer = targets.filter(t => !/rel\s*=\s*["'][^"']*noreferrer/.test(t));
ok(noReferrer.length === 0, '所有外链都带 noreferrer（不泄露 referrer）',
   noReferrer.length + ' 个缺失');

console.log('\n协议白名单');
const hrefs = [...body.matchAll(/href\s*=\s*"([^"]*)"/g)].map(m => m[1]);
const badProto = hrefs.filter(h => h && !/^(https?:\/\/|#)/.test(h));
ok(badProto.length === 0, 'href 只出现 https/http 和页内锚点',
   badProto.length ? '越界协议：' + [...new Set(badProto)].slice(0, 3).join(' ') : hrefs.length + ' 个 href 合规');
ok(!/href\s*=\s*["']\s*javascript:/i.test(body), '没有 javascript: 伪协议');
ok(!/href\s*=\s*["']\s*data:/i.test(body), '没有 data: 伪协议');

console.log('\n注入面');
/* 只在「标签的属性位置」上判定事件处理器。
   上游正文里出现过 "onmouseover=..." 这样的文字（举例说明攻击长什么样），
   那是被转义成纯文本的，不构成执行；判据若扫全文会一直误报，
   真正的风险只发生在 <tag ... on*= 这种位置上。 */
const attrPos = [...body.matchAll(/<[a-z][^>]*?\s(on[a-z]+)\s*=/gi)].map(m => m[1]);
ok(attrPos.length === 0, '标签属性位置上没有内联事件处理器', attrPos.join(',') || '无');
ok(!/<script\b/i.test(body.replace(/<script id="daily-pool"/i, '')), '正文里没有 script 标签（数据岛除外）');
ok(!/<iframe\b|<object\b|<embed\b/i.test(body), '没有 iframe/object/embed');
ok(!/<base\b/i.test(body), '没有 base 标签（防相对路径劫持）');
const forms = (body.match(/<form\b/gi) || []).length;
ok(forms === 0, '没有 form（防钓鱼提交）');

console.log('\n外部资源');
ok(!/<link\b/i.test(html), '没有 link 标签（不外链字体/样式）');
ok(!/@import/i.test(html), '没有 CSS @import');
ok(!/url\(\s*['"]?https?:/i.test(html), 'CSS 里没有远程 url()');
ok(!/<script[^>]+\bsrc\s*=/i.test(html), '没有外链 script src');
ok(!/fetch\s*\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|navigator\.send/i.test(html),
   '没有 fetch/XHR/WebSocket 等出网调用');

console.log('\n本地存储');
const lsKeys = [...html.matchAll(/localStorage\.(?:get|set)Item\(\s*['"]([^'"]+)/g)].map(m => m[1]);
console.log('  （用到：' + [...new Set(lsKeys)].join('、') + '）');
ok(!/localStorage\.setItem\([^,]*,\s*(q|search|keyword)/i.test(html), '不把搜索词写进本地存储');

console.log('\n凭据');
/* 只在「脚本与样式」之外的内容里找凭据样式，且要求形如赋值——
   文献标题里出现 Use Strong Passwords、passwd 之类的词是原文，不是泄露。 */
const creds = /(api[_-]?key\s*[:=]|secret\s*[:=]|passwo?rd\s*[:=]|bearer\s+[a-z0-9]{10,}|gho_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY)/i;
const hit = body.match(creds);
ok(!hit, '产物里没有凭据样式的内容', hit ? '命中：' + hit[0].slice(0, 40) : '');
ok(!/noreply\.github\.com|<meta name="author"[^>]*@/i.test(body), '正文里没有意外的邮箱/作者信息');

console.log(fail ? '\n✗ ' + fail + ' 项未通过' : '\n✓ 全部通过');
process.exit(fail ? 1 : 0);