# 高性价比人生指南 · 在线阅读页

一个单文件 HTML 阅读页，把开源书《高性价比人生指南》的全部 34 节、654 条建议
渲染成可搜索的页面。手机上打开就能看，不用装任何东西。

**在线阅读：** https://donnoe.github.io/how-to-live-better/

## 这是什么

原书由 [eternity4719/HowToLiveBetter](https://github.com/eternity4719/HowToLiveBetter)
维护（Unlicense，公有领域），按「性价比」排序，每条写清花掉什么、换回什么、证据多硬，
只引期刊论文和官方文件。

本仓库不是原书的 fork，也不改动原书内容。它只做一件事：把原书正文渲染成一个
**自包含的单文件网页**，方便在手机和别人的电脑上直接打开。

## 页面特性

**每天十条**：打开首页先看到十条建议——不花钱或少花钱、收益标「大」的那些。
同一天里刷新多少次都是这十条，第二天自动换一批（种子由本地日期生成，不联网）。
想看更多点「换一批」。十条按八个生活领域轮转抽取，不会十条全挤在安全类。

**八个生活领域**：34 节归入 意外防护 / 钱与保障 / 关系与家庭 / 法律与安全 /
健康身体 / 情绪与精力 / 工作与技能 / 育儿与养老。每个领域一个颜色，
建议卡片和目录都带领域标——扫一眼就知道这条管的是命、钱还是关系。

**零外部资源**：没有 CDN、没有字体外链、不 fetch 任何数据，断网也能读

- 逐条卡片：建议标题、证据等级（A/B/C）、性价比档、成本标签、所属领域
- **「说人话」高亮块**——原书里这一栏专门把统计量翻成日常说法，页面上做得最显眼
- 全站关键词搜索（结果高亮）、只看 A 级、只看说人话
- 左侧目录带性价比色点，目录里每节还有一条粗横条表示这节的三档性价比构成
- 手机端：搜索框独占一行、顶栏向下滚动后自动收成一行、回到顶部按钮
- 明暗主题切换（纸感米白 / 夜墨两套配色）
- 正文一行锁在 36 个汉字以内，宽屏上不会拉成一行五十字
- 支持直接打印

## 本地使用

不用构建，双击 `index.html` 即可。

## 重新生成

```bash
# 需要先有一份上游仓库的本地克隆
git clone --depth 1 https://github.com/eternity4719/HowToLiveBetter.git /tmp/upstream

# 全部 34 节
python build.py all -o index.html --repo /tmp/upstream

# 只做某几节
python build.py 1 2 16 --repo /tmp/upstream
```

源目录也可以用环境变量 `HLTB_REPO` 指定。

改完 `build.py` 后跑一下自检，确认每日十条的抽取逻辑没坏：

```bash
python build.py all -o index.html --repo /tmp/upstream
node test-daily.js
```

统计口径（条目数、A/B/C 分级、性价比三档）与上游的 `tools/sync-stats.ps1`
和 `index.html` 保持一致，生成结果可与上游徽章逐项对照。

## 领域划分

`build.py` 顶部的 `DOMAINS` 决定每节属于哪个领域。区间按各节真实主题划，
不是按节号顺序猜——比如第 11 节「程序员红线」归「工作与技能」，
跟第 26 节「做一个网站」同类，尽管中间隔着十几节别的内容。
上游新增或调整章节时，记得同步这个表。

## 安全约定

页面把上游 markdown 渲染进单文件 HTML，所以把渲染边界收在下面几条。
改 build.py 时这几条要一起看，`node test-security.js` 会逐条复查：

- **URL 走白名单**：`inline()` 只放行 `http/https`，其余（含 `javascript:`、
  `data:`、带引号或空格的）一律降级为 `#`。URL 会被拼进 `href="..."`，
  而正文转义用的是 `html.escape(quote=False)`（不动引号），不做这层校验的话
  一个带引号的链接就能闭合 href、注入 `onmouseover=` 之类的属性。
- **所有外链带 `rel="noopener noreferrer"`**：前者在旧浏览器上防反向标签劫持，
  后者不把「读者从哪来」告诉对方站点。页面另有 `<meta name="referrer"
  content="no-referrer">` 兜底。
- **零外部资源**：没有 link/@import/远程 url()/外链 script，
  也没有 fetch/XHR/WebSocket 等出网调用。页面不主动联系任何服务器，
  唯一的出网是读者自己点击文献链接。
- **只往 localStorage 写主题和已读条目 id**：不存搜索词、不存阅读正文。
  已读记录只存在读者自己的浏览器里，不上传，也没有清缓存之外的清除入口
  （控制台执行 `localStorage.removeItem('hltb-read')` 即可）。

## 自动更新

`.github/workflows/rebuild.yml` 每天 06:00（北京时间）拉取上游重新生成，
内容有变化才提交。也可以去 Actions 页面手动触发。
它只执行本仓库的 build.py，不执行上游的任何代码，上游仅作为 markdown 数据源；
权限收敛到 `contents: write` 一项。

## 授权

原书内容为 Unlicense（公有领域）。本仓库的构建脚本同样不作任何权利保留。
