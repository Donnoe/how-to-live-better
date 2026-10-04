# 设计方向确认记录

## 用户选择原话

> 问：C 佐藤可士和版 + 吸收 A 的领域色 (推荐)
> 问：是 Donnoe，继续

（选项文字因编码丢失显示为 `��`，据上下文与后续回答判定为「是 Donnoe，继续」。）

## 三版初稿

| 版本 | 文件 | 桌面截图 | 手机截图 | 逻辑 |
|---|---|---|---|---|
| A 轮盘 · 彩虹分类 | `design-demos/roulette.html` | `shot-roulette.png` | `shot-roulette-mobile.png` | 🎲 秒数轮盘（掷到 6 号 Utility-First Colorful Docs），把彩虹色用在 34 节归纳出的 8 大生活领域上 |
| B 现实参照 | `design-demos/benchmark.html` | `shot-benchmark.png` | `shot-benchmark-mobile.png` | 🏆 微信读书/得到类每日推荐流的单栏卡片拆解 |
| C 顶级定制 | `design-demos/studio.html` | `shot-studio.png` | `shot-studio-mobile.png` | 🧠 佐藤可士和「胜任的可爱」：纸感米底 + 朱红点睛 + 衬线大标题 |

## 最终执行方向

**C 版为骨架，吸收 A 版的生活领域色。**

采纳自 C（佐藤可士和定制版）：
- 纸感米白底 `#FBF6EE` 系，朱红 `#CC785C` 系作唯一强调色
- 衬线 display 大标题（「今天给你十张」级别的气口）
- 目录里「右边的粗条是这一节的性价比比例」的红色横条设计
- 松弛的留白与气口，不幼稚但有温度
- 「每天十条，够用了。」这个文案定位（源自 spec 第 7 节的视觉母题）

采纳自 A（彩虹分类版）：
- 34 节归纳成 8 个生活领域，每个领域一个颜色
- **关键修正**：颜色用在**建议标签**上（每条建议标出属于哪个领域），而不是用在 UI 按钮上。这样颜色承担信息、帮读者建立领域心智，而不是变成装饰。

## 账号

`github.com/Donnoe/how-to-live-better`（用户原话说的「Donne」在 gh 账号列表中不存在，活跃账号为 Donnoe，已确认）

## 执行前自检

- 三版均零 `<link>`、零外链脚本，纯系统字体栈 — 已 grep 验证
- 三版均为完整可交互 HTML，非静态图
- spec 见 `design-demos/spec.md`