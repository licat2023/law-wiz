# 文档插图

本目录存放文档引用的架构图和业务流程图。

## 文件用途

| 文件 | 用途 |
| --- | --- |
| [`fig-demo-architecture.mmd`](fig-demo-architecture.mmd) | 当前 Demo 的架构图源码，修改后重新渲染 PNG 与 SVG |
| `fig-demo-architecture.png`、`fig-demo-architecture.svg` | 分别供需求说明书和概要设计引用 |
| `fig-m2-*`、`fig-m4-*`、`fig-m6-*`、`fig-m7-*` | 需求说明书引用的业务流程图，仅有位图 |

## 渲染方法

[`tools/render-mmd.mjs`](../../tools/render-mmd.mjs) 使用本机安装的 Chrome 或 Edge 将 `.mmd` 渲染为 `.png` 与 `.svg`，需要 Mermaid 的 `dist/mermaid.min.js` 构建。

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
node tools/render-mmd.mjs docs/assets/fig-demo-architecture.mmd docs/assets/fig-demo-architecture 2400
```

产出 `fig-demo-architecture.png` 与 `fig-demo-architecture.svg`。

### 环境变量

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `MERMAID_DIR` | 含 `node_modules/mermaid` 的目录 | 当前工作目录 |
| `CHROME_PATH` | 浏览器可执行文件 | 自动探测 Chrome / Edge |
| `MMD_NODE_SPACING` | 同层节点间距 | 45 |
| `MMD_RANK_SPACING` | 层间距 | 70 |

脚本通过 `--dump-dom` 读取 SVG，再按图的尺寸截图。Mermaid 的 UMD 构建可直接内联到本地 HTML。
