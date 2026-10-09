# -*- coding: utf-8 -*-
"""把《高性价比人生指南》指定的节，渲染成一个自包含的单文件 HTML 阅读页。

用法：
    python build.py                      # 默认第 1、2、16 节
    python build.py 1 2 16 3             # 指定任意节号（按给定顺序渲染）
    python build.py all                  # 全部节（用于线上站点）
    python build.py all -o index.html    # 指定输出文件名
    python build.py all --repo /path/to/HowToLiveBetter

源目录也可用环境变量 HLTB_REPO 覆盖（供 GitHub Actions 使用，优先级低于 --repo）。
产物默认与脚本同目录，单个 .html，无任何外部依赖，双击即可打开、可离线读。

数字与标签的口径完全照抄仓库 tools/sync-stats.ps1 与 index.html 的 COST_W / e.ratio：
仓库改了那两行，这里也要同步改，否则性价比档会和官方检索页对不上。
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def parse_args():
    ap = argparse.ArgumentParser(description="生成《高性价比人生指南》单文件阅读页")
    ap.add_argument("sections", nargs="*", help="节号；或 all 表示全部节")
    ap.add_argument("-o", "--out", default=None, help="输出文件名（默认按节号自动命名）")
    ap.add_argument("--repo", default=None, help="上游仓库目录（默认 D:\\Agent\\HowToLiveBetter）")
    return ap.parse_args()


ARGS = parse_args()
REPO = Path(ARGS.repo or os.environ.get("HLTB_REPO") or r"D:\Agent\HowToLiveBetter")

UPSTREAM = "https://github.com/eternity4719/HowToLiveBetter"


def avail_sections():
    """扫描 book/ 目录，得到实际存在的节号。"""
    return sorted(int(p.name[:2]) for p in REPO.glob("book/[0-9][0-9]-*.md"))


ALL = avail_sections()
if not ALL:
    raise SystemExit("在 %s 下找不到 book/NN-*.md，请用 --repo 指定正确的仓库目录" % REPO)

if ARGS.sections:
    if any(a.lower() == "all" for a in ARGS.sections):
        SECTIONS = ALL
    else:
        SECTIONS = [int(a) for a in ARGS.sections]
else:
    SECTIONS = [n for n in (1, 2, 16) if n in ALL]

SCOPE = ("全书 %d 节" % len(ALL)) if SECTIONS == ALL else ("第 %s 节" % "、".join(str(n) for n in SECTIONS))

# 成本权重与档位规则，抄自 index.html 的 COST_W 与 e.ratio 两行
COST_W = {
    "钱": {"0": 0, "少": 1, "多": 2},
    "时间": {"少": 0, "中": 1, "多": 2},
    "毅力": {"否": 0, "些": 1, "是": 2},
}
RATIO_ORDER = {"极高": 0, "高": 1, "一般": 2}

# 34 节 → 8 大生活领域。颜色在建议标签上承担信息：
# 读者看颜色就知道这条讲的是钱、关系还是法律，而不是给 UI 按钮上色。
# 区间按各节真实主题划，不按节号顺序猜——比如第 11 节「程序员红线」是技术人的事，
# 该跟第 26 节「做网站」归一类，尽管中间隔着十几节别的内容。
DOMAINS = [
    (1, 2, "健康身体", "d5"),      # 不要早死 / 不要慢慢死
    (3, 4, "情绪与精力", "d6"),    # 不要浪费精力 / 时间
    (5, 7, "钱与保障", "d2"),       # 不要浪费钱 / 反面清单 / 没钱怎么活
    (8, 9, "法律与安全", "d4"),     # 法律与财产安全 / 法律红线
    (10, 10, "关系与家庭", "d3"),   # 恋爱和结婚
    (11, 11, "工作与技能", "d7"),   # 程序员和技术人
    (12, 12, "钱与保障", "d2"),     # 创业与做生意
    (13, 13, "意外防护", "d1"),     # 紧急情况
    (14, 15, "法律与安全", "d4"),   # 账号信息安全 / 租房买房
    (16, 17, "健康身体", "d5"),     # 慢性病 / 家里有老人
    (18, 18, "育儿与养老", "d8"),   # 养孩子划不划算
    (19, 19, "钱与保障", "d2"),     # 在职离职和工伤
    (20, 20, "育儿与养老", "d8"),   # 刚出生的孩子
    (21, 21, "意外防护", "d1"),     # 出国旅行与境外安全
    (22, 22, "情绪与精力", "d6"),   # 怎么放松
    (23, 23, "工作与技能", "d7"),   # 学什么技能
    (24, 24, "健康身体", "d5"),     # 看病
    (25, 25, "关系与家庭", "d3"),   # 人走了以后办什么
    (26, 26, "工作与技能", "d7"),   # 做一个网站或平台
    (27, 28, "健康身体", "d5"),     # 怀孕生产 / 别为外形搞坏身体
    (29, 29, "情绪与精力", "d6"),   # 遭遇重大打击之后
    (30, 32, "育儿与养老", "d8"),   # 上学的孩子 / 十八岁之后 / 出国留学
    (33, 34, "健康身体", "d5"),     # 残疾之后 / 常备药
]


def domain_of(n):
    """节号 → (领域名, 色 class)。落在末尾区间的一律归最后一档。"""
    for lo, hi, name, cls in DOMAINS:
        if lo <= n <= hi:
            return name, cls
    raise SystemExit("第 %d 节没有归入任何领域，请检查 DOMAINS 区间" % n)


def find_file(n):
    hits = sorted(REPO.glob("book/%02d-*.md" % n))
    if not hits:
        raise SystemExit("找不到第 %d 节" % n)
    return hits[0]


def parse(path):
    lines = path.read_text(encoding="utf-8").split("\n")
    title, intro, entries, cur = "", [], [], None
    for ln in lines:
        m = re.match(r"^#\s+(.*)$", ln)
        if m and not title:
            title = m.group(1).strip()
            continue
        m = re.match(r"^###\s+(\d+)\.\s*(.*)$", ln)
        if m:
            cur = {"no": int(m.group(1)), "title": m.group(2).strip(),
                   "tags_raw": None, "fields": {}, "last": None}
            entries.append(cur)
            continue
        if cur is None:
            if ln.strip() and not ln.startswith("["):
                intro.append(ln.strip())
            continue
        mt = re.match(r"^<!--\s*成本标签:\s*(.*?)\s*-->", ln)
        if mt:
            cur["tags_raw"] = mt.group(1)
            continue
        mf = re.match(r"^-\s*(成本|说人话|收益|证据等级|来源|备注)：(.*)$", ln)
        if mf:
            cur["last"] = mf.group(1)
            cur["fields"][mf.group(1)] = mf.group(2).strip()
            continue
        if not ln.strip():
            cur["last"] = None
            continue
        if cur["last"]:
            cur["fields"][cur["last"]] += ln.strip()
    return title, intro, entries


def parse_tags(raw):
    if not raw:
        return {}
    return dict(re.findall(r"(钱|时间|毅力|收益|口径)=(\S+)", raw))


def ratio_of(t):
    try:
        cs = sum(COST_W[k][t[k]] for k in ("钱", "时间", "毅力"))
    except KeyError:
        return None
    lv = t.get("收益")
    if lv == "大":
        return "极高" if cs == 0 else ("高" if cs <= 2 else "一般")
    if lv == "中" and cs == 0:
        return "高"
    return "一般"


def safe_url(u):
    """只放行 http/https，其余一律降级为 '#'。

    这不是洁癖：URL 要拼进 href="..."，而下面 inline() 里的 html.escape 用的是
    quote=False（不转义引号），所以一个带引号的 URL 能提前闭合 href、注入
    onmouseover= 之类的属性。上游 markdown 是外部输入，构造这种载荷不需要
    什么技术门槛，所以边界上只认协议、不认引号。

    顺带挡掉 javascript: 和 data:——两者都能在点击时执行任意脚本。
    """
    u = u.strip()
    if re.match(r"(?i)^https?://", u) and not re.search(r"[\s\"'<>`]", u):
        return u
    return "#"


def inline(s):
    """把一小段 markdown 行内语法转成 HTML。先整体转义，再用占位符放链接。"""
    stash = []

    def mk(url, text=None):
        shown = text or url
        if len(shown) > 62:
            shown = shown[:59] + "…"
        # url 必须再转义一次：stash 出来的 HTML 是拼进属性里的，
        # 不转义的话引号会闭合 href，把它变成新的属性。
        # noreferrer 一并加上，避免点击外链时把 referrer 带给对方站点。
        stash.append('<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>'
                     % (html.escape(safe_url(url), quote=True),
                        html.escape(shown, quote=False)))
        return "\u0001%d\u0001" % (len(stash) - 1)

    s = html.escape(s, quote=False)
    s = re.sub(r"&lt;(https?://[^\s]+?)&gt;", lambda m: mk(m.group(1)), s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", lambda m: mk(m.group(2), m.group(1)), s)
    s = re.sub(r"(?<![\w\"=])(https?://[^\s，。；）)]+)", lambda m: mk(m.group(1)), s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = s.replace("\\*", "*").replace("\\_", "_")
    s = re.sub("\u0001(\\d+)\u0001", lambda m: stash[int(m.group(1))], s)
    return s


def link_count(s):
    return len(re.findall(r"https?://", s or ""))


def source_rev():
    """取上游当前提交的短 hash 与日期。

    故意用上游 git 状态而不是构建时间：同样的源状态下重跑结果完全一致，
    产物可做字节级比对，方便确认「没改坏东西」。
    """
    try:
        p = subprocess.run(["git", "-C", str(REPO), "log", "-1", "--date=short",
                            "--format=%h|%cd"],
                           capture_output=True, text=True, encoding="utf-8", timeout=15)
        if p.returncode == 0 and "|" in (p.stdout or ""):
            h, d = p.stdout.strip().split("|", 1)
            return h.strip(), d.strip()
    except Exception:
        pass
    return "", ""

CSS = r"""
*,*::before,*::after{box-sizing:border-box}
:root{
  /* 纸感底色：不是纯白，是有一点黄的米白，像摊开的书页 */
  --paper:#F7F3EC;--card:#FFFCF7;--card2:#FBF6EE;--sink:#F1EBE0;
  --rule:#E6DDCE;--rule2:#D5C9B4;
  --ink:#2A2521;--ink2:#5F564C;--ink3:#8A8072;
  /* 唯一强调色：朱红。用在小面积，底色始终是纸 */
  --a:#B03A24;--a-soft:#F6E4DC;--a-line:#E3C3B6;
  --b:#2C5B79;--b-soft:#E3EBF1;
  --c:#6E655A;--c-soft:#EBE5DA;
  /* 八个生活领域。颜色承担信息：看色就知道这条管的是命、钱还是关系 */
  --d1:#B23A1E;--d1-bg:#FBE9E2;   /* 意外防护 */
  --d2:#0E7C6E;--d2-bg:#E1F1EE;   /* 钱与保障 */
  --d3:#C0456E;--d3-bg:#FBE7EE;   /* 关系与家庭 */
  --d4:#2F6BB5;--d4-bg:#E5EDF8;   /* 法律与安全 */
  --d5:#A6701A;--d5-bg:#F8EEDD;   /* 健康身体 */
  --d6:#4A7A2E;--d6-bg:#EAF2E3;   /* 情绪与精力 */
  --d7:#6A52B5;--d7-bg:#EDE9F9;   /* 工作与技能 */
  --d8:#8A5A2B;--d8-bg:#F5EBE1;   /* 育儿与养老 */
  --mark:#F5D98A;
  /* 中文系统字体栈：西文在前（接住数字与拉丁字母），中文在后 */
  --font:ui-sans-serif,system-ui,-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",sans-serif;
  --serif:"Songti SC","STSong","Noto Serif SC","Source Han Serif SC","SimSun",ui-serif,serif;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --bar:56px;--side:296px;
}
[data-theme=dark]{
  --paper:#1A1817;--card:#232120;--card2:#1E1C1B;--sink:#2A2725;
  --rule:#363230;--rule2:#474240;
  --ink:#EFE9E0;--ink2:#B4AA9E;--ink3:#8B8278;
  --a:#F09A80;--a-soft:#3A2620;--a-line:#573328;
  --b:#8FC0DC;--b-soft:#1E2E38;
  --c:#B0A69A;--c-soft:#2C2A28;
  --d1:#E8836A;--d1-bg:#3A2420;
  --d2:#3FBFA9;--d2-bg:#1B3630;
  --d3:#EE8CAC;--d3-bg:#3A2430;
  --d4:#79ADEA;--d4-bg:#1D2C3E;
  --d5:#DBA85A;--d5-bg:#372C18;
  --d6:#8FBC6E;--d6-bg:#27331E;
  --d7:#A692E8;--d7-bg:#2A2540;
  --d8:#C99A62;--d8-bg:#352818;
  --mark:#6B5A22;
}
html{scroll-behavior:smooth;scroll-padding-top:calc(var(--bar) + 14px)}
body{margin:0;background:var(--paper);color:var(--ink);
  font:16px/1.85 var(--font);
  -webkit-font-smoothing:antialiased;-webkit-text-size-adjust:100%;
  line-break:strict;overflow-wrap:break-word;font-synthesis:none}
h1,h2,h3{text-wrap:balance}
p{text-wrap:pretty}
a{color:var(--a);text-decoration:none}
a:hover{text-decoration:underline;text-underline-offset:2px}
mark{background:var(--mark);color:inherit;border-radius:2px;padding:0 1px}
strong{font-weight:600;color:var(--ink)}

/* min-height 用常量、不用 --bar：--bar 是 JS 实测回写的值，
   若拿它当 min-height，顶栏收起后会因为 min-height 还停在旧高度而缩不下去。 */
.bar{position:sticky;top:0;z-index:30;display:flex;flex-wrap:wrap;align-items:center;gap:10px;
  padding:0 18px;min-height:56px;background:var(--paper);border-bottom:1px solid var(--rule)}
.bar h1{font-family:var(--serif);font-size:16px;font-weight:600;margin:0;white-space:nowrap;min-width:0;letter-spacing:.01em}
.bar h1 small{font-weight:400;font-size:12px;color:var(--ink3);margin-left:8px;font-family:var(--font)}
.spacer{flex:1}
.search{position:relative;width:300px;max-width:42vw}
.search input{width:100%;height:34px;padding:0 30px 0 32px;border-radius:999px;border:1px solid var(--rule);
  background:var(--card);color:var(--ink);font:inherit;font-size:13px}
.search input:focus{outline:0;border-color:var(--a);background:var(--card)}
.search svg{position:absolute;left:10px;top:50%;transform:translateY(-50%);width:15px;height:15px;
  fill:none;stroke:var(--ink3);stroke-width:2;pointer-events:none}
.search kbd{position:absolute;right:10px;top:50%;transform:translateY(-50%);font:500 10px/1 var(--font);
  color:var(--ink3);border:1px solid var(--rule);border-radius:4px;padding:2px 4px;background:var(--card2)}
.btn{height:30px;padding:0 12px;border-radius:999px;border:1px solid var(--rule);background:var(--card);
  color:var(--ink2);font:500 12px/1 var(--font);cursor:pointer;transition:all .18s;white-space:nowrap}
.btn:hover{border-color:var(--a);color:var(--a)}
.btn[aria-pressed=true]{background:var(--a-soft);border-color:var(--a-line);color:var(--a)}
.btn.ghost{background:transparent}
.jump{display:none;height:30px;max-width:38vw;padding:0 6px;border-radius:8px;border:1px solid var(--rule);
  background:var(--card);color:var(--ink2);font:500 12px/1 var(--font)}
.count{font-size:12px;color:var(--ink3);white-space:nowrap;font-variant-numeric:tabular-nums}

.shell{display:flex;align-items:flex-start}
.toc{position:sticky;top:var(--bar);flex:none;width:var(--side);height:calc(100vh - var(--bar));
  overflow-y:auto;padding:18px 14px 80px 18px;background:var(--card2);border-right:1px solid var(--rule)}
.toc .gt{font-size:13px;font-weight:600;margin:0 0 5px;color:var(--ink);display:flex;
  justify-content:space-between;align-items:baseline;gap:6px}
.toc .gt small{font-weight:400;font-size:11px;color:var(--ink3);flex:none;font-variant-numeric:tabular-nums}
.toc .grp{padding-bottom:13px;margin-bottom:13px;border-bottom:1px solid var(--rule)}
.toc .grp:last-child{border-bottom:0;margin-bottom:0}
.toc .domdot{width:7px;height:7px;border-radius:50%;flex:none;display:inline-block;margin-right:5px;
  vertical-align:middle}
.toc a{display:flex;gap:6px;align-items:baseline;padding:3px 6px;border-radius:6px;font-size:12.5px;
  line-height:1.6;color:var(--ink2)}
.toc a:hover{background:var(--card);color:var(--ink);text-decoration:none}
.toc a.active{background:var(--a-soft);color:var(--a)}
.toc a i{font-style:normal;color:var(--ink3);font-variant-numeric:tabular-nums;flex:none;min-width:16px;text-align:right}
.toc a span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dot{width:6px;height:6px;border-radius:50%;flex:none;margin-top:7px}
.d0{background:var(--a)}.d1{background:var(--d2)}.d2{background:var(--ink3)}
/* 目录里那一节的三档性价比构成：粗条越长说明这节越值得先看 */
.rbar{display:flex;height:3px;border-radius:2px;overflow:hidden;margin:0 0 6px;gap:1px}
.rbar i{display:block}
.rb0{background:var(--a)}.rb1{background:var(--d2)}.rb2{background:var(--rule2)}

main{flex:1;min-width:0;padding:30px 40px 140px;max-width:960px}
section{margin-bottom:44px}
.sec-h{display:flex;align-items:baseline;gap:12px;padding-bottom:10px;border-bottom:1px solid var(--rule2);margin-bottom:6px}
.sec-h h2{font-family:var(--serif);font-size:23px;font-weight:600;margin:0;letter-spacing:.01em}
.sec-h .meta{font-size:12px;color:var(--ink3);font-variant-numeric:tabular-nums}
.intro{color:var(--ink2);font-size:15px;margin:12px 0 22px;padding-left:14px;border-left:2px solid var(--rule2)}

/* ── 每日十条 ───────────────────────────────────────────
   母题：这本书一次只给你十条，不要你一夜之间改变人生。
   所以它不是网格列表，是一沓纸里抽出来的十张——有纸叠、撕口、手写序号。 */
.daily{margin-bottom:52px;padding-bottom:30px;border-bottom:2px solid var(--rule2)}
.daily-h{margin-bottom:20px}
.daily-eyebrow{font-size:12.5px;color:var(--a);letter-spacing:.06em;margin-bottom:8px;
  font-variant-numeric:tabular-nums}
.daily-eyebrow .daily-sep{margin:0 7px;color:var(--ink3)}
.daily h2{font-family:var(--serif);font-size:clamp(28px,4.6vw,40px);font-weight:600;margin:0 0 10px;
  letter-spacing:.02em;line-height:1.25}
.daily-lead{font-size:15px;color:var(--ink2);margin:0 0 14px;max-width:34em;line-height:1.85}
.daily-act{display:flex;gap:8px;flex-wrap:wrap}
.daily-list{background:var(--card2);border:1px solid var(--rule);border-radius:14px;padding:6px 20px 6px}
.dnote{color:var(--ink3);font-size:12.5px}

/* 十张：两条之间是虚线撕口 */
.dcard{padding:18px 2px;border-bottom:1px dashed var(--rule2);position:relative}
.dcard:last-child{border-bottom:0}
.dcard-head{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:7px}
.dno{font-family:var(--serif);font-size:13px;font-weight:600;color:var(--a);
  background:var(--a-soft);border-radius:5px;padding:2px 7px;flex:none;
  font-variant-numeric:tabular-nums}
.dcard.read .dno{background:var(--sink);color:var(--ink3)}
.dhead{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;padding:3px 9px;
  border-radius:999px;border:1px solid transparent;flex:none}
.dhead .dt{display:inline-block;width:6px;height:6px;border-radius:50%;flex:none}
.dgrade{font:500 11px/1 var(--font);padding:3px 8px;border-radius:999px;flex:none}
.gA{background:var(--d2-bg);color:var(--d2)}
.gB{background:var(--d5-bg);color:var(--d5)}
.gC{background:var(--c-soft);color:var(--c)}
.dwhere{font-size:12px;color:var(--ink3);font-variant-numeric:tabular-nums}
.dtitle{font-family:var(--serif);font-size:18.5px;font-weight:600;margin:0 0 8px;line-height:1.5;letter-spacing:.01em}
.dplain{font-size:16.5px;line-height:1.9;color:var(--ink);margin:0 0 12px;max-width:36em}
.dmeta{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12.5px;color:var(--ink3)}
.dgo{color:var(--a);font-size:13px;font-weight:500;white-space:nowrap}
.dread{color:var(--ink3);font-size:12px;margin-left:auto}
.dcard.read .dplain{color:var(--ink2)}
.daily-note{margin:12px 2px 0}

/* 正文卡片 */
.card{background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:16px 18px 14px;margin-bottom:12px;transition:border-color .18s}
.card.read{border-color:var(--rule2)}
.card.read .chead h3{color:var(--ink2)}
.chead{display:flex;gap:10px;align-items:flex-start}
.num{flex:none;min-width:24px;height:24px;padding:0 6px;border-radius:7px;background:var(--sink);color:var(--ink3);
  font:600 12px/24px var(--font);text-align:center;font-variant-numeric:tabular-nums}
.chead h3{margin:0;font-size:17px;font-weight:600;line-height:1.55;letter-spacing:.01em;flex:1;min-width:0}
.read-badge{display:none;font:500 11px/1 var(--font);padding:2px 7px;border-radius:999px;
  background:var(--d6-bg);color:var(--d6);border:1px solid currentColor;flex:none;margin-top:3px}
.card.read .read-badge{display:inline-block}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 12px 34px;align-items:center}
.badge{font:500 11px/1 var(--font);padding:4px 9px;border-radius:999px;border:1px solid transparent}
.r0{background:var(--a-soft);color:var(--a);border-color:var(--a-line)}
.r1{background:var(--d2-bg);color:var(--d2)}
.r2{background:var(--c-soft);color:var(--c)}
.tag{font:400 11px/1 var(--font);padding:4px 9px;border-radius:999px;background:var(--sink);color:var(--ink3)}
/* 领域标签：这一条属于哪个生活领域 */
.dom{font:500 11px/1 var(--font);padding:4px 9px;border-radius:999px;display:inline-flex;align-items:center;gap:5px}
.dom::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;flex:none}

/* 正文列宽锁在 36em —— 中文一行 36 个汉字是回行不迷路的硬上限。
   不锁的话，main 在宽屏上会被拉到 900px+，一行 50 多个字，
   眼睛回行时找不到下一行开头，读起来格外累。 */
.plain{margin:0 0 12px 34px;padding:12px 16px;background:var(--a-soft);
  border-radius:0 10px 10px 0;font-size:17px;line-height:1.9;color:var(--ink);max-width:36em}
.fields{margin-left:34px;max-width:38em}
.f{display:grid;grid-template-columns:52px 1fr;gap:10px;padding:7px 0;border-top:1px solid var(--rule);
  font-size:14px;line-height:1.8;color:var(--ink2)}
.f b{font-weight:500;color:var(--ink3);font-size:12.5px;padding-top:3px}
.f.note b{color:var(--a)}
.f>div{min-width:0;overflow-wrap:anywhere}
.src{margin:10px 0 0 34px;border-top:1px solid var(--rule);padding-top:8px}
.src summary{cursor:pointer;font-size:13px;color:var(--ink3);list-style:none;user-select:none}
.src summary::-webkit-details-marker{display:none}
.src summary::before{content:"▸ ";color:var(--ink3)}
.src[open] summary::before{content:"▾ "}
.src summary:hover{color:var(--a)}
.src .sbody{font-size:13px;line-height:1.8;color:var(--ink2);padding:8px 0 2px;overflow-wrap:anywhere}
.cfoot{display:flex;justify-content:flex-end;align-items:center;margin:12px 0 0 34px;padding-top:8px}
.btn-read{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:999px;
  border:1px solid var(--rule);background:var(--card);color:var(--ink3);
  font:500 12px/1.3 var(--font);cursor:pointer;transition:all .18s;user-select:none}
.btn-read:hover{border-color:var(--a);color:var(--a)}
.btn-read .check-icon{flex:none}
.btn-read[aria-pressed=true],.card.read .btn-read{
  background:var(--d6-bg);border-color:var(--d6);color:var(--d6);
}
.btn-read[aria-pressed=true]:hover,.card.read .btn-read:hover{
  background:var(--a-soft);border-color:var(--a-line);color:var(--a);
}
.btn-read.sm{padding:2px 9px;font-size:11.5px}
.dmeta-act{display:inline-flex;align-items:center;gap:8px;margin-left:auto}

body.plain-only .fields,body.plain-only .src{display:none}
.hidden{display:none!important}
/* 搜索/筛选命中时，目标条目短暂高亮，帮眼睛从十条里找回位置 */
@keyframes hit{0%{background:var(--a-soft)}100%{background:transparent}}
.flash{animation:hit 1.6s ease-out}

.empty{color:var(--ink3);font-size:15px;padding:40px 0;text-align:center}
footer{color:var(--ink3);font-size:12.5px;border-top:1px solid var(--rule);padding-top:14px;line-height:2}
footer a{color:var(--ink2)}

#top{position:fixed;right:16px;bottom:16px;z-index:40;width:42px;height:42px;border-radius:50%;
  border:1px solid var(--rule);background:var(--card);color:var(--ink2);cursor:pointer;
  font:400 17px/1 var(--font);box-shadow:0 2px 12px rgba(0,0,0,.14);
  opacity:0;pointer-events:none;transition:opacity .2s,color .18s}
#top.show{opacity:1;pointer-events:auto}
#top:hover{color:var(--a);border-color:var(--a)}

/* 八个领域的配色，一处定义，标签/目录点/色带共用 */
.d1{color:var(--d1);background:var(--d1-bg)}
.d2{color:var(--d2);background:var(--d2-bg)}
.d3{color:var(--d3);background:var(--d3-bg)}
.d4{color:var(--d4);background:var(--d4-bg)}
.d5{color:var(--d5);background:var(--d5-bg)}
.d6{color:var(--d6);background:var(--d6-bg)}
.d7{color:var(--d7);background:var(--d7-bg)}
.d8{color:var(--d8);background:var(--d8-bg)}
.dhead.d1,.dom.d1{background:var(--d1-bg);color:var(--d1)}
.dhead.d2,.dom.d2{background:var(--d2-bg);color:var(--d2)}
.dhead.d3,.dom.d3{background:var(--d3-bg);color:var(--d3)}
.dhead.d4,.dom.d4{background:var(--d4-bg);color:var(--d4)}
.dhead.d5,.dom.d5{background:var(--d5-bg);color:var(--d5)}
.dhead.d6,.dom.d6{background:var(--d6-bg);color:var(--d6)}
.dhead.d7,.dom.d7{background:var(--d7-bg);color:var(--d7)}
.dhead.d8,.dom.d8{background:var(--d8-bg);color:var(--d8)}
.toc .domdot.d1,.toc .domdot.d2,.toc .domdot.d3,.toc .domdot.d4,
.toc .domdot.d5,.toc .domdot.d6,.toc .domdot.d7,.toc .domdot.d8{background:currentColor}

@media (max-width:1080px){
  .toc{display:none}
  .jump{display:block}
  main{padding:24px 22px 130px;max-width:none}
}
@media (max-width:820px){
  .bar{padding:8px 12px;gap:8px;min-height:0}
  /* 顶栏三行：① 标题+节号+明暗 ② 筛选按钮+计数 ③ 搜索（独占整行，手机上才好打字） */
  .bar h1{order:1;flex:1 1 120px;font-size:15px;overflow:hidden;text-overflow:ellipsis}
  .spacer{display:none}
  .jump{order:2}
  #theme{order:3}
  #f-all{order:4}#f-a{order:5}#f-plain{order:6}
  .count{order:7;margin-left:auto}
  .search{order:8;width:auto;max-width:none;flex:1 1 100%;margin-top:2px}
  .search input{height:34px}
  .search kbd{display:none}
  /* 向下滚动后收成一行（标题+搜索+明暗），把竖向空间还给正文；滚回顶部再展开 */
  body.compact .jump,body.compact #f-all,body.compact #f-a,
  body.compact #f-plain,body.compact .count{display:none}
  body.compact .search{order:2;flex:1 1 120px;margin-top:0}
  body.compact #theme{order:3}
  main{padding:18px 13px 110px}
  .daily{margin-bottom:38px;padding-bottom:22px}
  .daily h2{font-size:27px}
  .daily-lead{font-size:14.5px}
  .daily-list{padding:2px 15px;border-radius:12px}
  .dcard{padding:15px 2px}
  .dtitle{font-size:17px}
  .dplain{font-size:16px;line-height:1.85}
  .sec-h h2{font-size:20px}
  .card{padding:14px 14px 12px;border-radius:10px;margin-bottom:10px}
  .chead h3{font-size:16px}
  .plain{font-size:16px;padding:10px 13px}
  .f{font-size:13.5px;grid-template-columns:44px 1fr;gap:8px}
  .intro{font-size:14px;margin:10px 0 18px}
}
@media (max-width:520px){
  .bar h1 small{display:none}
  .chips,.plain,.fields,.src,.cfoot{margin-left:0}
  .num{min-width:22px;height:22px;font-size:11px;line-height:22px}
  .daily-lead{font-size:14px}
  .dwhere{font-size:11.5px}
}
@media (max-width:380px){
  .btn{padding:0 9px;font-size:11px}
  .bar h1{flex:1 1 90px;font-size:14px}
  .jump{max-width:32vw}
  .dtitle{font-size:16px}
}
@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  .flash{animation:none}
}
@media print{
  .bar,.toc,#top,.daily-act,.cfoot{display:none}
  main{max-width:none;padding:0}
  .daily{border-bottom:1px solid #ccc;break-after:page;margin-bottom:0}
  .card{break-inside:avoid;border-color:#ccc}
  .src .sbody{display:block}
  .dcard{break-inside:avoid}
  body{font-size:11pt;background:#fff;color:#000}
}
"""

def render_entry(e, sec_no):
    t = parse_tags(e["tags_raw"])
    f = e["fields"]
    grade = (f.get("证据等级") or "?").strip()[:1]
    ratio = ratio_of(t)
    dom_name, dom_cls = domain_of(sec_no)
    chips = []
    gcls = {"A": "gA", "B": "gB", "C": "gC"}.get(grade, "gC")
    chips.append('<span class="badge %s">%s 级</span>' % (gcls, grade))
    if ratio:
        chips.append('<span class="badge r%d">性价比 %s</span>' % (RATIO_ORDER[ratio], ratio))
    for k in ("口径",):
        if t.get(k):
            chips.append('<span class="tag">%s %s</span>' % (k, t[k]))
    for k in ("钱", "时间", "毅力"):
        if t.get(k):
            chips.append('<span class="tag">%s %s</span>' % (k, t[k]))
    if t.get("收益"):
        chips.append('<span class="tag">收益 %s</span>' % t["收益"])

    rows = []
    for k in ("成本", "收益"):
        if f.get(k):
            rows.append('<div class="f"><b>%s</b><div>%s</div></div>' % (k, inline(f[k])))
    if f.get("备注"):
        rows.append('<div class="f note"><b>备注</b><div>%s</div></div>' % inline(f["备注"]))

    src = f.get("来源", "")
    n = link_count(src)
    src_html = ""
    if src:
        src_html = ('<details class="src"><summary>来源%s</summary>'
                    '<div class="sbody">%s</div></details>'
                    % ("（%d 条文献）" % n if n else "", inline(src)))

    card_id = "s%d-%d" % (sec_no, e["no"])
    return ('<article class="card" id="%s" data-grade="%s" data-ratio="%s" data-domain="%s">'
            '<div class="chead"><span class="num">%d</span><h3>%s</h3><span class="read-badge">已读</span></div>'
            '<div class="chips"><span class="dom %s">%s</span>%s</div>'
            '<p class="plain">%s</p>'
            '<div class="fields">%s</div>%s'
            '<div class="cfoot"><button class="btn-read" type="button" data-id="%s" aria-pressed="false">'
            '<svg class="check-icon" viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">'
            '<path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M3 8.5l3.5 3.5 6.5-7"/>'
            '</svg><span class="read-label">标记读过</span>'
            '</button></div></article>') % (
        card_id, grade, ratio or "-", dom_cls, e["no"], inline(e["title"]),
        dom_cls, dom_name, "".join(chips), inline(f.get("说人话", "")), "".join(rows), src_html,
        card_id)


JS = r"""
const cards=[...document.querySelectorAll('.card')];
const secs=[...document.querySelectorAll('section:not(.daily)')];
const bar=document.querySelector('.bar');
const q=document.getElementById('q');
const cnt=document.getElementById('cnt');
const jump=document.getElementById('jump');
const fAll=document.getElementById('f-all');
const fA=document.getElementById('f-a');
const fP=document.getElementById('f-plain');
const themeBtn=document.getElementById('theme');
const topBtn=document.getElementById('top');
let grade=null, plainOnly=false;

/* ── 每日十条 ────────────────────────────────────────────
   同一天内刷新多少次都是这十条，第二天自动换一批。
   做法：把本地日期编成种子，喂给一个确定性 PRNG，同种子必得同序列。
   不存服务器、不看时间戳，纯靠日期——所以跨零点打开就是新的一批，
   同一天反复刷新、关掉再打开，又还是同一批。
   mulberry32：32 位状态、周期足够长、几行就能写对。 */
const POOL=JSON.parse(document.getElementById('daily-pool').textContent);
const READ_KEY='hltb-read';
let readSet;
try{
  const stored=JSON.parse(localStorage.getItem('hltb-read')||'[]');
  readSet=new Set(Array.isArray(stored)?stored:[]);
}catch(e){
  readSet=new Set();
}

function saveRead(){
  try{ localStorage.setItem('hltb-read',JSON.stringify([...readSet].slice(-5000))); }catch(e){}
}

function updateCard(id){
  const c=document.getElementById(id);
  if(!c) return;
  const isRead=readSet.has(id);
  c.classList.toggle('read',isRead);
  const btn=c.querySelector('.btn-read');
  if(btn){
    btn.setAttribute('aria-pressed',String(isRead));
    const txt=btn.querySelector('.read-label');
    if(txt) txt.textContent=isRead?'已读':'标记读过';
  }
}

function initAllReadCards(){
  cards.forEach(c=>{
    if(readSet.has(c.id)){
      c.classList.add('read');
      const btn=c.querySelector('.btn-read');
      if(btn){
        btn.setAttribute('aria-pressed','true');
        const txt=btn.querySelector('.read-label');
        if(txt) txt.textContent='已读';
      }
    }
  });
}

function toggleRead(id){
  if(!id) return;
  if(readSet.has(id)){
    readSet.delete(id);
  }else{
    readSet.add(id);
  }
  saveRead();
  updateCard(id);
  renderDaily();
}

function xmur3(str){
  let h=1779033703^str.length;
  for(let i=0;i<str.length;i++){
    h=Math.imul(h^str.charCodeAt(i),3432918353);
    h=h<<13|h>>>19;
  }
  return function(){
    h=Math.imul(h^h>>>16,2246822507);
    h=Math.imul(h^h>>>13,3266489909);
    return (h^=h>>>16)>>>0;
  };
}
function mulberry32(a){
  return function(){
    a|=0;a=a+0x6D2B79F5|0;
    let t=Math.imul(a^a>>>15,1|a);
    t=t+Math.imul(t^t>>>7,61|t)^t;
    return ((t^t>>>14)>>>0)/4294967296;
  };
}
function today(){
  const d=new Date();
  return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
}
/* 按领域分组再洗牌、最后轮转取——这样十条不会挤在同一个领域里，
   而是横跨八个生活领域，读完十条等于把生活各转了一圈。 */
function pickDaily(seed){
  const rnd=mulberry32(xmur3(seed)());
  const byDom={};
  POOL.forEach(it=>{ (byDom[it.cls]=byDom[it.cls]||[]).push(it); });
  const keys=Object.keys(byDom);
  keys.forEach(k=>{
    const arr=byDom[k];
    for(let i=arr.length-1;i>0;i--){
      const j=Math.floor(rnd()*(i+1));
      const t=arr[i];arr[i]=arr[j];arr[j]=t;
    }
  });
  /* 轮转取：每轮从下一个领域拿一条，八个领域转一圈再转第二圈。
     循环上界给足但有限——万一某个领域被抽空也不会转不出来。 */
  const out=[];let i=0;
  while(out.length<10&&i<1000){
    const k=keys[i%keys.length];
    if(byDom[k].length) out.push(byDom[k].shift());
    i++;
  }
  return out;
}

const dailyList=document.getElementById('daily-list');
const dailyDate=document.getElementById('daily-date');
const dailyCnt=document.getElementById('daily-cnt');
const dailyNote=document.getElementById('daily-note');
const btnShuffle=document.getElementById('f-shuffle');
const btnRead=document.getElementById('f-read');
let curSeed=today();
let readOnly=false;

function esc(s){ return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

function renderDaily(){
  let list=pickDaily(curSeed);
  const totalInBatch=list.length;
  let unseen=0;
  list.forEach(it=>{ if(!readSet.has(it.id)) unseen++; });

  if(readOnly){
    list=list.filter(it=>!readSet.has(it.id));
  }

  const html=list.map((it,i)=>{
    const isRead=readSet.has(it.id);
    const cost=it.money==='0'?'不花钱':(it.money==='少'?'少花钱':(it.money?'花点钱':''));
    return '<article class="dcard'+(isRead?' read':'')+'" data-id="'+it.id+'">'
      +'<div class="dcard-head">'
      +'<span class="dno">'+String(i+1).padStart(2,'0')+'</span>'
      +'<span class="dhead '+it.cls+'">'+esc(it.dom)+'</span>'
      +'<span class="dgrade g'+it.grade+'">证据 '+it.grade+'</span>'
      +'<span class="dwhere">'+it.sec+'. '+esc(it.secTitle)+'</span>'
      +(isRead?'<span class="dread">已读</span>':'')
      +'</div>'
      +'<h3 class="dtitle">'+esc(it.title)+'</h3>'
      +'<p class="dplain">'+esc(it.plain)+'</p>'
      +'<div class="dmeta"><span>'+(cost?esc(cost):'')+(it.time?' · 时间 '+esc(it.time):'')+'</span>'
      +'<div class="dmeta-act">'
      +'<button class="btn-read sm" type="button" data-id="'+it.id+'" aria-pressed="'+String(isRead)+'">'
      +'<svg class="check-icon" viewBox="0 0 16 16" width="12" height="12"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M3 8.5l3.5 3.5 6.5-7"/></svg>'
      +'<span class="read-label">'+(isRead?'已读':'标记读过')+'</span>'
      +'</button>'
      +'<a class="dgo" href="#'+it.id+'">看依据 ›</a>'
      +'</div></div>'
      +'</article>';
  }).join('');
  dailyList.innerHTML=html||(readOnly?'<p class="dnote">这批里的 10 条你都已经读过了！可以点「换一批」看看更多建议，或再次点击上方按钮取消只看未读。</p>':'<p class="dnote">候选池是空的。</p>');
  const d=new Date();
  dailyDate.textContent=(d.getMonth()+1)+' 月 '+d.getDate()+' 日';
  const label=(curSeed===today())?'今天十条':'换的一批';
  dailyCnt.textContent=label+' · '+(readOnly?list.length+' / '+totalInBatch:list.length)+' 条';
  dailyNote.textContent='十条里还有 '+unseen+' 条你没读过。读完的会记下来，下次开页面标灰；'
    +'（只是记一笔，没有打卡和连续天数）';
  btnRead.setAttribute('aria-pressed',String(readOnly));
}

btnShuffle.onclick=()=>{ curSeed='sh'+Date.now(); renderDaily(); };
btnRead.onclick=()=>{ readOnly=!readOnly; renderDaily(); };

/* 事件委托：点击正文或每日十条里的 .btn-read */
document.addEventListener('click',e=>{
  const btn=e.target.closest('.btn-read');
  if(!btn) return;
  const id=btn.dataset.id;
  if(id) toggleRead(id);
});

/* 点每日条目跳到正文里的那一条。顺带把那一条的来源展开并标记已读 */
dailyList.addEventListener('click',e=>{
  const a=e.target.closest('.dgo');
  if(!a) return;
  const card=e.target.closest('.dcard');
  const id=card.dataset.id;
  if(!readSet.has(id)){
    readSet.add(id); saveRead();
    updateCard(id);
    renderDaily();
  }
  const t=document.getElementById(id);
  if(t){
    const src=t.querySelector('details');
    if(src) src.open=true;
    t.classList.remove('flash');void t.offsetWidth;t.classList.add('flash');
    t.scrollIntoView({block:'start'});
  }
});

/* 顶栏高度会随换行变化，交给 JS 实测，锚点跳转才不会被顶栏盖住 */
function syncBar(){
  const h=Math.round(bar.getBoundingClientRect().height);
  document.documentElement.style.setProperty('--bar', h+'px');
}

function clearMarks(root){
  const ms=[...root.querySelectorAll('mark')];
  ms.forEach(m=>m.replaceWith(document.createTextNode(m.textContent)));
  if(ms.length) root.normalize();
}
function markAll(root,term){
  if(!term) return;
  const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode(n){
    if(!n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
    const p=n.parentElement;
    if(!p) return NodeFilter.FILTER_REJECT;
    if(p.closest('script,style,mark,a')) return NodeFilter.FILTER_REJECT;
    return NodeFilter.FILTER_ACCEPT;
  }});
  const nodes=[]; while(w.nextNode()) nodes.push(w.currentNode);
  const t=term.toLowerCase();
  nodes.forEach(n=>{
    const raw=n.nodeValue.toLowerCase();
    if(raw.indexOf(t)<0) return;
    const frag=document.createDocumentFragment();
    let i=raw.indexOf(t), last=0;
    while(i>=0){
      frag.appendChild(document.createTextNode(n.nodeValue.slice(last,i)));
      const m=document.createElement('mark');
      m.textContent=n.nodeValue.slice(i,i+t.length);
      frag.appendChild(m);
      last=i+t.length; i=raw.indexOf(t,last);
    }
    frag.appendChild(document.createTextNode(n.nodeValue.slice(last)));
    n.replaceWith(frag);
  });
}
function apply(){
  const term=q.value.trim().toLowerCase();
  clearMarks(document.querySelector('main'));
  let shown=0;
  cards.forEach(c=>{
    let ok=true;
    if(grade && c.dataset.grade!==grade) ok=false;
    if(ok && term && !c.textContent.toLowerCase().includes(term)) ok=false;
    c.classList.toggle('hidden',!ok);
    if(ok) shown++;
  });
  secs.forEach(s=>{
    const n=s.querySelectorAll('.card:not(.hidden)').length;
    s.classList.toggle('hidden',n===0);
    if(jump){
      const o=jump.querySelector('option[value="'+s.id+'"]');
      if(o) o.disabled=(n===0);
    }
  });
  document.getElementById('empty').classList.toggle('hidden',shown>0);
  cnt.textContent=shown+' / '+cards.length+' 条';
  if(term) markAll(document.querySelector('main'),term);
  document.querySelectorAll('.toc a').forEach(a=>{
    const el=document.getElementById(a.getAttribute('href').slice(1));
    a.classList.toggle('hidden',!el||el.classList.contains('hidden'));
  });
}
let timer=null;
q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(apply,90);});
function setMode(mode){
  grade=(mode==='A')?'A':null;
  plainOnly=(mode==='plain');
  document.body.classList.toggle('plain-only',plainOnly);
  const map={'all':fAll,'A':fA,'plain':fP};
  Object.keys(map).forEach(k=>map[k].setAttribute('aria-pressed',String(k===mode)));
  apply();
}
fAll.onclick=()=>setMode('all');
fA.onclick=()=>setMode('A');
fP.onclick=()=>setMode('plain');
fAll.setAttribute('aria-pressed','true');

if(jump){
  jump.addEventListener('change',()=>{
    const el=document.getElementById(jump.value);
    if(el) el.scrollIntoView({block:'start'});
  });
}
themeBtn.onclick=()=>{
  const cur=document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark';
  document.documentElement.setAttribute('data-theme',cur);
  try{localStorage.setItem('hltb-theme',cur);}catch(e){}
};
try{
  const t=localStorage.getItem('hltb-theme');
  if(t) document.documentElement.setAttribute('data-theme',t);
  else if(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches)
    document.documentElement.setAttribute('data-theme','dark');
}catch(e){}
document.addEventListener('keydown',e=>{
  if(e.key==='/'&&document.activeElement!==q&&!/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)){
    e.preventDefault();q.focus();
  }
  if(e.key==='Escape'&&document.activeElement===q){q.value='';apply();q.blur();}
});
topBtn.onclick=()=>window.scrollTo({top:0,behavior:'smooth'});
/* 滚动状态：① 顶栏收起（手机）② 回到顶部按钮出现。
   用 rAF 节流，避免滚动时每帧都跑；阈值留迟滞区间，防止在临界点来回抖动。 */
let compact=false, ticking=false;
function onScroll(){
  const y=window.scrollY;
  const want = compact ? (y>200) : (y>420);
  if(want!==compact){compact=want;document.body.classList.toggle('compact',compact);syncBar();}
  topBtn.classList.toggle('show',y>900);
}
addEventListener('scroll',()=>{
  if(ticking) return;
  ticking=true;
  requestAnimationFrame(()=>{ticking=false;onScroll();});
},{passive:true});
addEventListener('resize',syncBar);
if(document.fonts&&document.fonts.ready) document.fonts.ready.then(syncBar);
syncBar();

const links=[...document.querySelectorAll('.toc a')];
const io=new IntersectionObserver(es=>{
  es.forEach(e=>{ if(e.isIntersecting){
    if(e.target.classList.contains('card'))
      links.forEach(a=>a.classList.toggle('active',a.getAttribute('href')==='#'+e.target.id));
    else if(jump && e.target.tagName==='SECTION')
      jump.value=e.target.id;
  }});
},{rootMargin:'-70px 0px -75% 0px'});
cards.forEach(c=>io.observe(c));
if(jump) secs.forEach(s=>io.observe(s));

initAllReadCards();
renderDaily();
"""


def main():
    sec_toc = []
    sec_html = []
    jump_opts = []
    total = 0
    grade_cnt = {"A": 0, "B": 0, "C": 0}
    link_total = 0
    # 每日十条的候选池：优先「不花钱 / 少花钱 + 收益大」的条目，
    # 这类建议读者当天就能用上，抽出来才有「今天就能做」的价值。
    # 只收有「说人话」的——卡片正文就靠它，没有内容的条目抽出来是空壳。
    daily_pool = []
    dom_stat = {}

    for n in SECTIONS:
        p = find_file(n)
        title, intro, entries = parse(p)
        dom_name, dom_cls = domain_of(n)
        dom_stat[dom_name] = dom_stat.get(dom_name, 0) + len(entries)
        cards = []
        links = []
        # 这一节的性价比构成，目录里画成一条横条
        rr = [RATIO_ORDER.get(ratio_of(parse_tags(e["tags_raw"])), 2) for e in entries]
        bar_r0 = rr.count(0)
        bar_r1 = rr.count(1)
        bar_r2 = rr.count(2)
        for e in entries:
            g = (e["fields"].get("证据等级") or "?").strip()[:1]
            if g in grade_cnt:
                grade_cnt[g] += 1
            total += 1
            tags = parse_tags(e["tags_raw"])
            link_total += link_count(e["fields"].get("来源", "")) + link_count(e["fields"].get("备注", ""))
            cards.append(render_entry(e, n))
            r = ratio_of(tags)
            short = e["title"] if len(e["title"]) <= 34 else e["title"][:33] + "…"
            links.append('<a href="#s%d-%d" title="%s"><span class="dot d%d"></span>'
                         '<i>%d</i><span>%s</span></a>'
                         % (n, e["no"], html.escape(e["title"], quote=True),
                            RATIO_ORDER.get(r, 2), e["no"], html.escape(short)))
            plain = e["fields"].get("说人话", "").strip()
            if plain and tags.get("收益") == "大" and tags.get("钱") in ("0", "少"):
                daily_pool.append({
                    "id": "s%d-%d" % (n, e["no"]),
                    "sec": n,
                    "secTitle": title,
                    "no": e["no"],
                    "dom": dom_name,
                    "cls": dom_cls,
                    "grade": g if g in ("A", "B", "C") else "C",
                    "title": e["title"],
                    "plain": plain,
                    "money": tags.get("钱", ""),
                    "time": tags.get("时间", ""),
                })
        ratio_bar = ""
        if entries:
            tot = len(entries)
            ratio_bar = ('<span class="rbar" aria-hidden="true">'
                         '<i class="rb0" style="flex:%d"></i><i class="rb1" style="flex:%d"></i>'
                         '<i class="rb2" style="flex:%d"></i></span>'
                         % (bar_r0, bar_r1, bar_r2))
        sec_toc.append('<div class="grp"><div class="gt"><span class="domdot %s"></span>%s'
                       '<small>%d 条</small></div>%s%s</div>'
                       % (dom_cls, inline(title), len(entries), ratio_bar, "".join(links)))
        sec_html.append(
            '<section id="sec%d"><div class="sec-h"><h2>%s</h2>'
            '<span class="meta">%d 条</span></div>%s%s</section>'
            % (n, inline(title), len(entries),
               ('<p class="intro">%s</p>' % inline(" ".join(intro))) if intro else "",
               "".join(cards)))
        jump_opts.append('<option value="sec%d">%s</option>' % (n, html.escape(title)))

    rev, rev_date = source_rev()

    head = ('<!DOCTYPE html><html lang="zh-CN" data-theme="light"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<meta name="color-scheme" content="light dark">'
            '<meta name="theme-color" media="(prefers-color-scheme: light)" content="#ffffff">'
            '<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#1b1b1f">'
            # 读者点外链去看文献时，不把「从哪来」告诉对方站点。
            # 外链已带 noreferrer，这条是双保险，也覆盖非 a 标签的跳转。
            '<meta name="referrer" content="no-referrer">'
            '<meta name="description" content="《高性价比人生指南》%s，共 %d 条建议，'
            '每条标注成本、收益、证据等级（A/B/C）与原始文献链接。单文件、零依赖、可离线阅读。">'
            '<title>高性价比人生指南 · %s</title><style>%s</style></head><body>'
            % (SCOPE, total, SCOPE, CSS))

    bar = ('<header class="bar"><h1>高性价比人生指南<small>%s</small></h1>'
           '<select class="jump" id="jump" aria-label="跳转到某一节">%s</select>'
           '<div class="spacer"></div>'
           '<button class="btn" id="f-all">全部</button>'
           '<button class="btn" id="f-a">只看 A 级</button>'
           '<button class="btn" id="f-plain">只看说人话</button>'
           '<div class="search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/>'
           '<path d="M20 20l-3.5-3.5"/></svg>'
           '<input id="q" type="search" placeholder="搜索标题、说人话、收益…" autocomplete="off">'
           '<kbd>/</kbd></div>'
           '<span class="count" id="cnt">%d / %d 条</span>'
           '<button class="btn" id="theme">明/暗</button></header>' % (
               SCOPE, "".join(jump_opts), total, total))

    # 每日十条：把候选池以 JSON 数据岛注入，交给前端按日期种子抽取。
    # 放 data island 而不是写死十条，是为了让「第二天自动换一批」不依赖重新构建——
    # 换批逻辑全在前端，站点每天 06:00 的例行构建只负责内容更新。
    pool_json = json.dumps(daily_pool, ensure_ascii=False, separators=(",", ":"))
    # </script> 出现在数据里会提前闭合脚本标签，这里转义掉
    pool_json = pool_json.replace("</", "<\\/")

    daily = ('<section class="daily" id="daily">'
             '<div class="daily-h"><div class="daily-eyebrow">'
             '<span class="daily-date" id="daily-date"></span>'
             '<span class="daily-sep">·</span><span id="daily-cnt">10 / 10</span></div>'
             '<h2>今天给你十张</h2>'
             '<p class="daily-lead">从 %d 条建议里挑出 10 条不花钱、收益大的。'
             '同一天里刷新多少次都是这十条，第二天自动换新的；想看更多，点「换一批」。</p>'
             '<div class="daily-act">'
             '<button class="btn" id="f-shuffle">换一批</button>'
             '<button class="btn ghost" id="f-read">只看没读过的</button>'
             '</div></div>'
             '<div class="daily-list" id="daily-list"></div>'
             '<p class="daily-note" id="daily-note"></p></section>'
             % len(daily_pool))

    src_line = ('数据来源：<a href="%s" target="_blank" rel="noopener noreferrer">'
                'eternity4719/HowToLiveBetter</a>' % UPSTREAM)
    src_line += '（Unlicense，公有领域）'
    if rev:
        src_line += '，数据截至 <span style="font-family:var(--mono)">%s</span>%s' % (
            rev, '（%s）' % rev_date if rev_date else '')

    dom_line = '、'.join('%s %d 条' % (k, v) for k, v in
                         sorted(dom_stat.items(), key=lambda kv: -kv[1]))
    footer = ('<footer>%s。<br>'
              '「说人话」「收益」等栏目为原文摘录，未作改写；本页共 %d 条，'
              'A 级 %d 条、B 级 %d 条、C 级 %d 条，含 %d 条文献外链。<br>'
              '按生活领域划分：%s。<br>'
              '单文件自包含，不引用任何外部资源（正文中的文献链接除外），可离线阅读。'
              '由 build.py 生成。</footer>'
              % (src_line, total, grade_cnt["A"], grade_cnt["B"], grade_cnt["C"], link_total, dom_line))

    shell = ('<div class="shell"><aside class="toc">%s</aside><main>%s%s'
             '<div class="empty hidden" id="empty">没有匹配的条目</div>%s'
             '</main></div>'
             '<button id="top" title="回到顶部" aria-label="回到顶部">↑</button>'
             % ("".join(sec_toc), daily, "".join(sec_html), footer))

    # 注意：JS 字符串只含脚本体，<script> 开合标签在这里拼。
    # 之前漏了开标签，导致整段 JS 被当纯文本渲染在页面底部、脚本从未执行。
    out = (head + bar + shell + '<script id="daily-pool" type="application/json">'
           + pool_json + '</script><script>' + JS + '</script></body></html>')

    if ARGS.out:
        name = Path(ARGS.out)
        if not name.is_absolute():
            name = HERE / name
    else:
        name = HERE / ("高性价比人生指南_%s.html" % "_".join("第%d节" % n for n in SECTIONS))

    name.write_text(out, encoding="utf-8")
    print("范围 %s ｜ 节数 %d ｜ 条目 %d ｜ A %d B %d C %d ｜ 外链 %d"
          % (SCOPE, len(SECTIONS), total, grade_cnt["A"], grade_cnt["B"], grade_cnt["C"], link_total))
    print("输出：%s  (%d 字节)" % (name, len(out.encode("utf-8"))))


if __name__ == "__main__":
    main()
