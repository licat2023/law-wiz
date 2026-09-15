# 智法宝前端（law-wiz frontend）

Vue 3 + Element Plus + Vite，一期承载 M2 合同智能审查与 M3 法律 AI 问答的 Web 界面。

## 快速开始

```powershell
pnpm install
pnpm dev        # http://localhost:5173
```

**开发环境不需要配置后端地址**：Vite 把 `/api` 代理到 `127.0.0.1:8000`，
因此前后端同源，没有跨域问题。生产由 OpenResty 同源代理，行为一致。

先起后端（见 [`../backend/README.md`](../backend/README.md)），否则登录会失败。

## 目录结构

```
src/
├── api/          接口封装
│   ├── client.ts   Axios 实例、拦截器、令牌存储、统一拆包
│   └── types.ts    **与后端 Pydantic 模型镜像的类型定义**
├── stores/       Pinia 状态
├── router/       路由与鉴权守卫
├── views/        页面
└── styles/       全局样式
```

> **当前 `src/` 下只有空目录**，上面是目标结构。页面清单由团队认领时决定。

## 四条硬性约定（做错会出问题，不是风格偏好）

### 1. ⛔ ID 一律当字符串，不做算术

后端主键是 `BIGINT UNSIGNED`，而 JS 的 `Number` 只能精确表示到 2^53−1。
`api/types.ts` 里所有 ID 都声明为 `string`，**前端只做传递与比较，不做运算**。
这是契约层规定（05-接口设计 §3.4），不是当前数据量小就可以忽略。

### 2. ⛔ 判成败看 `code`，不看 HTTP 状态码

统一响应体是 `{ code, message, data, request_id }`。后端两者都给，
但**业务结果以 `code` 为准**。`api/client.ts` 的 `request()` 已经做了这件事，
新接口请一律走它，不要直接用 `http.get`。

### 3. ⛔ 涉及 AI 的接口必须带 `Idempotency-Key`

发起审查（`createReview`）与发消息（`sendMessage`）都**要求**这个请求头：

- 审查会消耗 LLM 额度，重试不带键会**重复扣费并产生两个任务**；
- 提问重试不带键会产生**两条内容不同的回答**，用户无法判断哪条有效。

`crypto.randomUUID()` 生成；**同一次用户操作的重试必须复用同一个键** ——
每次重试都新生成一个键，等于没有幂等性。

### 4. ⛔ 风险报告必须按 `source_type` 区分三类依据

`RiskPoint.source_type` 有三个取值，界面上**必须呈现为不同的东西**：

| 取值            | 含义                         | 建议呈现                                   |
| --------------- | ---------------------------- | ------------------------------------------ |
| `retrieved_law` | 依据检索到的法条             | 展示法条引用，可点击查看原文               |
| `rule`          | 依据人工审查规则             | 标注"依据审查规则"，**不冒充法条**         |
| `llm_inference` | 模型推断，**无直接法律依据** | **必须标注**"未找到直接法律依据，仅供参考" |

三者混为一谈是本项目最容易被质疑的设计缺陷（见 03-概要设计 §5.3）。

同理，问答的 `QaMessage.has_citation === false` 时**必须提示"未找到直接法律依据"** ——
溯源不了的时候要说出来，而不是让用户以为所有回答都有依据。

## 三个实现要点（容易漏）

1. **列表与详情的 ID 字段是 `task_id` / `session_id` / `document_id` / `file_id`**，
   不是 `id`。后端用带资源前缀的字段名以避免响应里一堆无语义的 `id`（见 05-接口设计 §9.3）。
2. **选中的是"合同版本"而非合同**：`char_start` / `char_end` 的偏移基准是
   `contract_version.plain_text`（原文），**不是 OCR 结果、不是 PDF 页面坐标**。
   高亮必须基于后端返回的 `plain_text`，另找文本做高亮偏移一定对不上。
3. **上传前校验格式与大小，但后端会再校验一次**（依据文件头魔数，不信任扩展名）。
   前端校验只是少一次往返，**不是安全边界**。

## 构建

```powershell
pnpm typecheck     # vue-tsc 类型检查
pnpm build         # 类型检查 + 构建到 dist/
pnpm build:only    # 只构建，跳过类型检查（赶时间时用）
```

产物 `dist/` 上传到服务器站点静态目录，由 1Panel 的 OpenResty 托管
（见 [`../deploy/README.md`](../deploy/README.md)）。

## 多端说明

一期**只有 Web**。微信小程序（P5）与安卓 App（P6）为后续移植，
**各自独立开发、不共用代码库**，共用的是同一套 REST 接口。
因此本目录可以自由使用浏览器专属库（Element Plus、TinyMCE、Signature Pad），
**但不得把浏览器行为写进接口契约**（如依赖 Cookie 自动携带、依赖 `Referer` 判断来源）。
见 [ADR-0010](../docs/adr/0010-multi-client-strategy.md)。
