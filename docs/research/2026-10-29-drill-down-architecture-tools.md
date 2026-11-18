# 可下钻架构图：Skill、应用与项目选型

核验日期：2026-10-29。目标交互是“点击架构节点，进入该节点内部的另一张图，并能返回”，不是单纯放大画布、展开属性或跳转源码。整理了 28 个候选；核心候选核对官方文档及相关源码，成熟度参考 GitHub API。未逐项安装运行，因此“支持”表示有文档或实现证据，不表示已在 law-wiz 验收。

## 结论

1. **law-wiz 长期维护首选 LikeC4 + 官方 `likec4-dsl` skill。** 它原生维护父子元素与子视图，抽象层数可自定，有 MCP，能生成单个自包含 HTML。AI 仍需依据代码建立模型；它不会因为启用子视图就自动理解整个仓库。[视图](https://likec4.dev/dsl/views/)、[配置](https://likec4.dev/dsl/config/)、[HTML 导出](https://likec4.dev/guides/static-website/)、[官方 AI 工具](https://likec4.dev/tooling/ai-tools/)
2. **交互形式最直接的是 DrillFlow + `drillflow-diagrams` skill/MCP。** 任意节点可以拥有任意深度子图，Mermaid subgraph 可以转成真正可进入的 subflow。应用本地优先，但不等于应用开源；当前单 HTML 导出仍在尚未上线的 Pro 规划中。[官网](https://drillflow.de)、[格式与 skill](https://github.com/capydev42/drillflow-skill)、[MCP](https://github.com/capydev42/drillflow-mcp)
3. **希望自动分析现有 Python/TypeScript 仓库，优先评估 CodeBoarding。** 它生成嵌套组件分析及可进入的组件子页面；默认 HTML 存在 CDN 依赖，完全离线需额外处理。[项目与说明](https://github.com/CodeBoarding/CodeBoarding)
4. **严格 C4 与成熟生态选 Structurizr；手工图形化协作选 IcePanel；中文 3D 子场景选 iCraft。** 三者的层级语义、交付方式和计费各不相同。[Structurizr](https://docs.structurizr.com/server/diagrams/viewer)、[IcePanel](https://docs.icepanel.io/core-features/diagramming.md)、[iCraft](https://icraft.gantcloud.com/blog/subscene)

上次产物用 Archify 子图加外层导航实现跨图下钻。若未来频繁调整模块和关系，原生管理父子视图的工具可以减少自行维护导航映射的工作。

## 检索渠道与判断方式

| 渠道 | 用途 |
| --- | --- |
| Skills.sh 网站及 `npx skills find` | 检索 LikeC4、Structurizr、interactive architecture、system atlas、DrillFlow、arch-lab、Archify 等关键词 |
| SkillsMP、skilld 等目录及普通搜索 | 扩展发现；不以目录描述直接证明功能 |
| GitHub README、源码、API | 验证实际跳转、许可证、归档状态、近期维护；识别 README 空项目 |
| 官方产品站与文档 | 验证层级限制、导出、本地部署、免费能力与商业边界 |
| MCP 目录和官方 MCP 仓库 | 区分“生成模型/验证格式”和“真的修改或发布图” |
| ChatGPT/Codex 插件目录 | 检索到 tldraw、Figma、MagicPath 等通用绘图能力；未据其目录描述认定原生下钻 |
| 中文产品与开发者文档 | 找到 iCraft 原生嵌套子场景及 Player SDK |

匹配分三类：**原生结构下钻**（进入独立子图）、**模型聚焦/折叠**（改变同图可见范围）、**作者维护的跨页链接**。三类都可能有用，但维护成本不同。技能安装量和 stars 只作辅助，不证明功能或安全性。

## 12 个重点应用与项目

| 候选 | 下钻方式 | 输入与自动化 | 交付与主要边界 |
| --- | --- | --- | --- |
| **LikeC4** | 元素进入 scoped view；抽象层级自定 | `.c4` / `.likec4` 模型；官方 skill、MCP、Model API | MIT；本地预览、静态站、单 HTML；需建立正确架构模型。[视图](https://likec4.dev/dsl/views/)、[导出](https://likec4.dev/guides/static-website/) |
| **DrillFlow** | 任意节点拥有 subflow；面包屑和树导航 | 手工、Mermaid、原生 JSON；官方 skill/MCP | 编辑器免费、本地浏览器存储、可离线；应用闭源；单 HTML 导出尚在规划。[官网](https://drillflow.de)、[公开组件](https://github.com/capydev42/drillflow-skill) |
| **Structurizr** | 双击系统→容器→组件；目标视图须存在 | Structurizr DSL / Java API；官方 MCP | `local` / `export` 免费；静态站保留双击下钻；预编译 `server` 要许可。[查看器](https://docs.structurizr.com/server/diagrams/viewer)、[静态站](https://docs.structurizr.com/export/static-site)、[分发说明](https://docs.structurizr.com/binaries) |
| **IcePanel** | 对象进入内部图；Belong To 导航 | 图形化 C4 共享模型；付费 MCP | 商业 SaaS，3 层架构图；模型第 4 层连接到代码。MCP 能写模型对象，不能创建 diagram。[图与层级](https://docs.icepanel.io/core-features/diagramming.md)、[MCP](https://docs.icepanel.io/integrations/mcp-server.md) |
| **CodeBoarding** | 嵌套组件图；HTML 节点打开组件子页面 | 静态分析 + LLM；支持 Python、TS/JS；CLI | MIT 分析引擎/CLI；默认 HTML 从 CDN 加载脚本；在线平台的开源范围不能由 CLI 许可推定。[项目](https://github.com/CodeBoarding/CodeBoarding) |
| **iCraft Editor / Player** | 元素子场景内继续绘图，再返回父场景 | 中文可视化编辑器；官方 JS/React Player | 3D/2D 展示与嵌入适用；商业专有许可；没有核实通用代码逆向能力。[子场景教程](https://icraft.gantcloud.com/blog/subscene) |
| **Archyl** | 双击进入下一层，面包屑返回 | C4 四级；Git 发现、YAML、MCP | 商业 SaaS，有免费对象额度；企业定制才提供 on-prem；AI 发现准确度未实测。[层级](https://www.archyl.com/docs/c4-model/overview)、[套餐](https://www.archyl.com/pricing) |
| **StructSmith** | 节点进入详情视图，非仅属性面板 | 可视化模型；REST + 原生 MCP | MIT；本地优先、单容器 + SQLite；未确认自包含交互 HTML 导出和通用源码逆向。[项目](https://github.com/dziksu/StructSmith) |
| **arch-lab** | 节点指向 childDiagramId；面包屑 | `.alab` 模型；`alab` skill；校验/转换 MCP | MIT；浏览器解析/布局，PNG/SVG/模型导出；分层 ZIP 不等于交互 HTML。生态很小。[FAQ](https://arch-lab.dev/faq)、[skill](https://arch-lab.dev/skill) |
| **Ilograph** | 嵌套资源内部聚焦、细节层级、perspective 切换 | YAML 模型，自动布局 | Desktop 可离线；付费能力含自包含交互 HTML。默认单击首先是选择，不是换一张独立子图。[浏览操作](https://www.ilograph.com/docs/getting-started/browsing-diagrams/)、[桌面版](https://www.ilograph.com/desktop/) |
| **Renderizr** | 基于 Structurizr 工作区视图及元素激活目标导航 | 已有 workspace JSON；有配套 skill | MIT；静态 SPA 或内联全部资源的单 HTML，还包含 workspace 文档与 ADR。小型社区项目，非源码分析器。[项目](https://github.com/FormulaMonks/renderizr) |
| **Enterprise Architect** | Composite Element 双击进入 child diagram | 手工 UML/SysML 等模型 | 商业桌面建模工具；启用 concise navigation 后同位切换并有返回箭头。仅为可点击图引入时较重。[官方说明](https://sparxsystems.com/enterprise_architect_user_guide/17.2/modeling_fundamentals/compositeelements.html) |

### LikeC4 的关键设置

`implicitViews` 默认关闭。开启后，已有模型中未显式定义 scoped view 的元素也会自动得到子视图，点击即可进入；自动产生的是模型的视图，不是对任意业务源码的逆向分析。[配置文档](https://likec4.dev/dsl/config/)

静态构建的 `--output-single-file` 明确输出单个自包含 HTML；也支持 hash history，便于静态托管。对于“生成后直接发给别人打开”的目标，这比自行拼接许多页面更接近现成方案。[导出文档](https://likec4.dev/guides/static-website/)

### Structurizr 的产品代际变化

当前应看统一仓库 `structurizr/structurizr` 及 `local / server / export` 工作流。旧 Lite、CLI、UI 仓库已归档；源码 Apache-2.0 不代表所有官方预编译模式都免费。`server` 分发授权、`local` 和静态导出需要分开判断。[当前仓库](https://github.com/structurizr/structurizr)、[二进制许可](https://docs.structurizr.com/binaries)

### DrillFlow 的发布边界与文档差异

本地编辑和导入可以不发布。使用 MCP 的 publish 工具则会上传为持链接可访问的只读图；匿名链接有时效及管理限制。这与本地 HTML 附件不同。其公开 MCP/skill 为 MIT，应用本身闭源。[MCP 仓库](https://github.com/capydev42/drillflow-mcp)

核验时 skill 仍称 Mermaid 只在浏览器导入、要链接必须 JSON，而较新的 MCP README 已提供 `publish_mermaid`；token 条件描述也有差异。因此可以确认 skill/MCP 都存在，但不能把两份文档的每句话拼成一致保证。[skill](https://github.com/capydev42/drillflow-skill)、[MCP](https://github.com/capydev42/drillflow-mcp)

## 找到的 9 个相关 Skill

安装量取本次 Skills CLI 查询的近似展示值，不与 GitHub stars 混用。

| Skill | 安装量快照 | 能做什么 | 判断与来源 |
| --- | --- | --- | --- |
| **官方 `likec4-dsl`** | 约 2.4K | 教 AI 准确写 DSL、模型、视图和验证流程 | 最适合本需求的长期建模入口；官方仓库约 5,983 stars、MIT。[官方入口](https://likec4.dev/tooling/ai-tools/) |
| **`drillflow-diagrams`** | 1 | 生成嵌套 Mermaid / DrillFlow JSON，说明层级引用和导入发布 | 需求匹配很高，但 skill/MCP 仓库仅 1/0 stars，很新；建议先做小样验证。[skill 源码](https://github.com/capydev42/drillflow-skill)、[目录](https://skills.sh/capydev42/drillflow-skill/drillflow-diagrams) |
| **`alab`** | 2 | 教 AI 写 arch-lab 多种图语法，另有 MCP 校验 | 有原生子图，但生态小，仓库 3 stars。[官方 skill 页](https://arch-lab.dev/skill) |
| **`system-atlas`** | 508 | 等距交互地图、章节、Go inside 步骤、生成 SYSTEM.md | MIT、约 459 stars。内部步骤视图贴近讲解，但不是已证明的任意层 C4 子图树；字体样式表可能联网。[仓库](https://github.com/inkboard/system-atlas)、[目录](https://skills.sh/inkboard/system-atlas/system-atlas) |
| **`understand` / Understand Anything** | 约 5.4K | 分析代码，生成文件/函数/类知识图、领域视图、问答 | MIT、约 88,731 stars。源码理解很相关，但不能把“可点击知识图”直接等同每节点进入内部架构子图。[仓库](https://github.com/Egonex-AI/Understand-Anything)、[目录](https://skills.sh/egonex-ai/understand-anything/understand) |
| **`structurizr-c4`** | 12 | 生成、验证、本地查看 Structurizr DSL | 社区封装，Java 21+、脚本式工具链；仓库 0 stars，应列实验备选。[仓库](https://github.com/Tacuchi/structurizr-c4-skill) |
| **`scaffoldizr`** | 230 | 搭建 Structurizr 模型与文档目录，提供 AI 非交互命令 | 建模脚手架，需要配合查看器；MIT、约 5 stars。[仓库](https://github.com/FormulaMonks/scaffoldizr) |
| **`renderizr`** | 194 | 把 Structurizr workspace 渲染为可分享 SPA / 单 HTML | 对离线交付很相关；MIT、约 5 stars，宜先试样。[仓库](https://github.com/FormulaMonks/renderizr) |
| **`archify`** | 约 180.8K | 多类型图、代码证据、验证、交互 HTML 与导出 | 已有工具；本次产物的跨图层级由额外导航实现，普及度不代表原生维护层级图模型。[仓库](https://github.com/tt-a1i/archify) |

LikeC4 官方站点型 skill 的目录详情路由本次出现失效，安装应以官方 AI Tools 文档的入口为准，而非依赖该目录卡片。

经官方来源核对的安装入口，供后续选用：

```bash
npx skills add https://likec4.dev/
npx skills add capydev42/drillflow-skill --skill drillflow-diagrams
npx skills add inkboard/system-atlas --skill system-atlas
npx skills add raksitnongbua/arch-lab --skill alab
```

分别见 [LikeC4](https://likec4.dev/tooling/ai-tools/)、[DrillFlow 目录与源码](https://skills.sh/capydev42/drillflow-skill/drillflow-diagrams)、[System Atlas](https://github.com/inkboard/system-atlas)、[arch-lab](https://arch-lab.dev/skill)。本次没有执行这些安装。

## 另外 12 个候选与容易误判的结果

| 候选 | 实际能力与限制 | 来源 |
| --- | --- | --- |
| **ArchFlow** | C4 L1→L2→L3、自托管团队平台、研究代理；AGPL-3.0。比静态文档重，未核实单 HTML 交互导出 | [仓库](https://github.com/TheAlexPG/ArchFlow) |
| **arch-diagram** | Claude Code 插件；目录→文件→函数、面包屑、单 HTML。MIT，新项目；工作流约定主要识别 JS/TS，FastAPI 装饰器路由未识别 | [仓库](https://github.com/noam812/arch-diagram) |
| **Ropeman** | 双击区域递归请求 AI 分析子域；返回层级和缓存真实存在。许可 TBD；Bridge 仍可能调用云模型，WebGPU 才是实验性离线推理 | [仓库](https://github.com/yoonsooc/ropeman) |
| **GemDraw** | 描述系统→HLD→双击组件生成 UML 子图；不是从真实源码还原。Apache-2.0；UML 类节点不能继续无限下钻，本地模型部署较重 | [仓库](https://github.com/akulkarni9/GemDraw) |
| **ArchiLens** | 当前已实现模块点击进入 L2；应认定有限层级正例。Apache-2.0，2 stars；HTML 脚本有 CDN 依赖 | [仓库](https://github.com/saurabh-oss/archilens) |
| **Understand Anything** | 代码/领域交互知识图、搜索、源码与解释，适合辅助逆向理解；不作为严格子图导航的已验证替代 | [仓库](https://github.com/Egonex-AI/Understand-Anything) |
| **System Atlas** | Go inside 看步骤、章节化讲解；适合教学与方案讨论，嵌套架构深度需另外确认 | [仓库](https://github.com/inkboard/system-atlas) |
| **Archify** | 单图表达、验证与交付强；本次采用外层导航组织 20 张图 | [仓库](https://github.com/tt-a1i/archify) |
| **Scaffoldizr** | 架构模型脚手架；本身不是子图查看器 | [仓库](https://github.com/FormulaMonks/scaffoldizr) |
| **draw.io / diagrams.net** | 多页及形状页链接可组织层级体验；父子关系与跨页一致性由作者维护。已有官方 MCP/skills，不应写成无 AI 接入 | [多页](https://www.drawio.com/docs/manual/pages/)、[官方 MCP](https://www.drawio.com/mcp/) |
| **GitDiagram** | 点击打开 GitHub 文件/目录；不进入节点内部的新架构图 | [官方使用说明](https://gitdiagram.com/visualize-codebase) |
| **Deep Dive Diagrams** | 核验时只有 README 与 2 次提交，没有可用应用实现；不进入推荐 | [仓库](https://github.com/Unskilledcrab/deep-dive-diagrams) |

Ropeman、GemDraw、ArchiLens、arch-diagram 分别只有约 1、2、2、1 stars。这不否定其功能，但意味着要把“交互源码存在”与“已成熟可依赖”分开。对于 law-wiz，尤其应核对 Python 装饰器路由、异步后台任务、跨服务 HTTP 和动态分派能否被正确识别。

## 自己构建时可用的 4 个基础库

| 基础库 | 官方已有能力 | 仍需自己做 |
| --- | --- | --- |
| [React Flow](https://reactflow.dev/learn/layouting/sub-flows) | 子流程、分组与父子节点 | 架构模型、独立子图路由、面包屑、源码关联 |
| [Vue Flow](https://vueflow.dev/) | Vue 嵌套节点与图；可贴合本仓库 Vue 技术栈 | 同上，不能仅因支持 nested graph 就认定已有完整下钻应用 |
| [Cytoscape.js](https://js.cytoscape.org/) | Compound nodes、父子图关系和图算法 | 在聚焦、折叠与切换子图之间选择交互，再实现导航 |
| [AntV G6](https://g6.antv.antgroup.com/en/manual/element/combo/overview/) | Combo 与展开/折叠，折叠时汇总外部连接 | 独立子图切换及架构领域语义；默认双击折叠不是新图导航 |

这些适合开发自己的产品。若目标只是持续产出 law-wiz 的可分享架构文档，先用成品建模工具的成本通常更低；这是本次选型判断，非性能测试结论。

## 对 law-wiz 的建议

| 目标 | 优先候选 | 原因 |
| --- | --- | --- |
| 稳定维护“系统→服务→切片→内部职责”，继续发单 HTML | **LikeC4 + 官方 skill** | 模型真源、层级自由、原生导航、可静态交付；不依赖所有语言都可被自动逆向 |
| 直接把嵌套 Mermaid 变成能进入的子图 | **DrillFlow** | 交互与格式最直接；先接受当前交付、闭源应用及新生态边界 |
| 尽量从现有 Python/Vue 代码提取初稿 | **CodeBoarding** | 嵌套组件分析已落地；仍需人工核对业务边界和补齐离线资源 |
| 更严格的 C4 标准与既有生态 | **Structurizr local + export** | 成熟模型、视图规则、官方 MCP；使用当前统一工具链 |
| 无代码绘图、多人维护 | **IcePanel** | 共享对象模型与原生层级；确认三层是否足够及 MCP/套餐限制 |
| 演示效果优先、中文 3D 展示 | **iCraft** | 独立子场景及嵌入组件已有明确操作与 API |

下一步比较样例应统一使用同一小片：`系统总览 → Backend → review 切片 → Agent 调用/报告`。分别核对返回、跨层连接、对象复用、中文、代码证据、导出后的交互与断网表现，再决定迁移；不应只比较截图美观度。

## 可复核材料

本次检索原始记录、源码摘录、GitHub 元数据、链接检查和分项笔记保存在仓库 `.research/2026-10-29-drilldown/`。本机部分 `curl` 遇到 Windows 证书吊销检查故障，已通过远端抓取再次验证相关官方页面的 HTTP 200；未将这些网络故障当作产品失效。官方 G6 旧中文路径失效，本文引用已验证的英文 Combo 文档。

未新增项目依赖或实现约定；已检查项目 AGENTS.md，无需更新。
