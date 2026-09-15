# 文档插图

本目录存放各文档引用的插图。

## 图的两种形态

自 2026-09-13 起，插图有**源码形态**与**交付形态**两种，源码是唯一真源：

| 形态 | 文件 | 用途 |
| --- | --- | --- |
| **源码** | `*.mmd`（Mermaid） | **唯一真源**。改图改这里 |
| 交付位图 | `*.png` | 供 Word/PDF 交付件嵌入 |
| 矢量中间件 | `*.svg` | 渲染时自动产出，便于无损查看与进一步加工 |

> ⚠️ **历史遗留图只有位图、没有源码**（`fig-m2-*`、`fig-m4-*`、`fig-m6-*`、`fig-m7-*`），因为它们是 2026-09-09 从 `2023442256黎建斌.docx` 里导出时**从截图重新截的**（实为 JPEG，3136×2436），原始绘图文件已不存在。**这些图要改只能重画**，建议后续统一改为 Mermaid 源码。

## 渲染方法

`tools/render-mmd.mjs` 把 `.mmd` 渲染为 `.png` 与 `.svg`。它**不依赖 `@mermaid-js/mermaid-cli`**（后者会额外下载自己的 Chromium），而是复用本机已安装的浏览器。

### 一次性准备

```powershell
# 在任意临时目录安装 mermaid（仅取它的 dist，不需要装进本项目）
npm install mermaid
$env:MERMAID_DIR = "<该目录的绝对路径>"
```

### 渲染

```powershell
# 在仓库根目录（law-wiz/）执行
$env:MERMAID_DIR = "<含 node_modules/mermaid 的目录>"
node tools/render-mmd.mjs docs/assets/fig-architecture.mmd docs/assets/fig-architecture 2400
```

产出 `fig-architecture.png` 与 `fig-architecture.svg`。

### 环境变量

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `MERMAID_DIR` | 含 `node_modules/mermaid` 的目录 | 当前工作目录 |
| `CHROME_PATH` | 浏览器可执行文件 | 自动探测 Chrome / Edge |
| `MMD_NODE_SPACING` | 同层节点间距 | 45 |
| `MMD_RANK_SPACING` | 层间距 | 70 |

### 渲染器的三个设计决定（都是踩坑后的结论）

1. **必须用 UMD 构建 `dist/mermaid.min.js`，不能用 ESM 构建。**
   mermaid 12 的 ESM 构建（`mermaid.esm.min.mjs`）靠 `import ... from "./chunks/..."` 加载几十个分块文件。把它内联进 HTML 后，这些**相对路径在 `file://` 下解析不到**，模块静默不加载，页面只剩一段未执行的脚本文本 —— 而 DOM 里可能仍有 `RENDER_OK` 之类的字样，造成"渲染成功"的假象。UMD 构建是**单文件、零相对 import**，稳定可用。

2. **必须用 `--dump-dom` 取回 SVG，不能靠截图猜尺寸。**
   先渲染、再量尺寸、最后按尺寸截图，是唯一可靠的两步法。

3. **`--user-data-dir` 指向 `.chrome-profile`，渲染后删除。**
   否则 Chrome 复用旧 profile 会锁住目录；脚本在结束时自动清理该目录与临时 HTML。

## 关于 `fig-architecture` 的版式

该图的 `.mmd` 使用 `flowchart TB`（自上而下），渲染尺寸约 **2057×2760（宽高比 0.75）**，呈纵向长条。

- **这是自动布局的必然结果，不是参数问题**：图有 6 个层级，最宽的一层是 8 个节点，6 层必须垂直堆叠。实测把 `nodeSpacing` 从 25 调到 80、`rankSpacing` 从 35 调到 120，**尺寸逐像素不变** —— 宽度由最宽层决定，与层间距无关。
- **与 Word 交付件相容**：报告为 A4 纵向，该比例优于横版，缩放后仍可读。
- **曾试过 `flowchart LR`（横排）**：布局比例为 3005×1532（宽高比 1.96），但截图为空白 —— 横排与当前截图适配逻辑冲突，未继续深究。若将来需要横版，**需先修渲染器的尺寸适配**再改方向。

## 第 ⑤ 层：外部能力接入

这一层画出的是**外部能力本身** —— 大模型、OCR、向量存储、对象存储，以及 P2/P3 的签章、时间戳、区块链。

> **一期不建 Provider 接口体系**：外部能力由需要的切片**直接接入**，
> 但**同一个能力只在一处封装**。见 [ADR-0012](../adr/0012-defer-capability-abstraction.md)。

绿色方块表示这些能力由外部系统提供。当某个能力**真的出现第二种实现**时
（LLM 接 Ollama、向量库换 pgvector、本地 OCR 替代云端），在那一刻抽接口 ——
那时接口形状才是已知的。相关决策见 [ADR-0004](../adr/0004-vector-store-abstraction.md)、[ADR-0005](../adr/0005-signature-provider-abstraction.md)、[ADR-0006](../adr/0006-timestamp-source.md)。

图中还标出了**交付分期**：P1 的模块为蓝色实线框，P2 及以后为灰色虚线框 —— 使「设计完整、分期交付」在图上直接可见，避免评审误以为全部模块均已实现。
