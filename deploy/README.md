# 部署说明

> ⚠️ **本文描述的是目标状态，编排文件尚未编写**：`docker-compose.dev.yml`、
> `docker-compose.prod.yml` 与 `backend/Dockerfile` 都还不存在。下面命令里出现的文件名，
> 就是落地时要建的文件 —— 本文是**它们必须满足的约束**（尤其是 §3.4 的内存上限）。

本项目部署在**一台 1Panel 主机**上（主机地址与凭据不入库，由团队内部维护）。
**部署前必须先读容量约束**（见下方 §3.4），否则会踩内存不足的坑。

## 一、两种用法，别搞混

| 文件 | 用途 | 起什么 |
| --- | --- | --- |
| `docker-compose.dev.yml` | **本地开发** | 只起 MySQL + Redis 两个依赖，后端与前端在宿主机跑（保留热更新） |
| `docker-compose.prod.yml` | **服务器部署** | 完整栈：MySQL + Redis + 后端 |

后端与前端在本地用 `uv` / `pnpm` 直接跑，**不要用 compose 起应用** —— 容器里的热更新体验远不如宿主机。

## 二、本地开发

```powershell
# 1) 起依赖
docker compose -f deploy/docker-compose.dev.yml up -d

# 2) 后端
cd backend
uv venv --python "C:\Users\<你>\AppData\Local\Python\pythoncore-3.14-64\python.exe"
uv sync --extra dev
Copy-Item .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# 3) 前端（另开一个终端）
cd frontend
pnpm install
pnpm dev        # http://localhost:5173
```

前端 dev server 把 `/api` 代理到 `127.0.0.1:8000`，因此**本地没有跨域问题**。

## 三、服务器部署

### 3.1 关键：不要起独立 Nginx

服务器 **80/443 已被 1Panel 自带的 OpenResty 占用**（它同时服务着禅道）。
因此：

- `docker-compose.prod.yml` **不包含任何 Web 服务器容器**；
- 后端只绑 `127.0.0.1:8000`，由 **1Panel 面板配置站点 + 反向代理**指过来；
- 前端构建产物（`frontend/dist`）上传到该站点的静态目录。

在 1Panel 面板里：**网站 → 创建网站 → 反向代理**，把 `/api` 指向 `http://127.0.0.1:8000`，
其余路径指向静态目录。

### 3.2 步骤

```bash
# 在服务器上
mkdir -p /opt/law-wiz && cd /opt/law-wiz
# 上传 docker-compose.prod.yml 与 .env（.env 由 .env.prod.example 复制并填好凭据）
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f backend

# 首次部署要建表（在 backend 容器内执行）
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

### 3.3 上线前必须确认的三件事

| 项 | 为什么 |
| --- | --- |
| **`LAWWIZ_JWT_SECRET` 是独立生成的长随机串** | 留空 compose 会拒绝启动；用开发默认值等于没有鉴权 |
| **`LAWWIZ_ALLOW_FIXED_VERIFY_CODE=false`** | 固定验证码 `000000` 上线等于任何人可注册任意账号。后端启动校验会拒绝在 production 下启用它，但**别依赖这道防线，配置里就写对** |
| **`sql_mode` 含 `STRICT_TRANS_TABLES`** | 非严格模式下超长值会被**静默截断**而非拒绝（实测见 `docs/04-数据库设计.md` §2.2）。compose 已显式指定，改配置时别删 |

### 3.4 内存上限不是可选项

目标服务器只有 **1.7 GiB 内存、可用约 950 MiB**，且上面已跑着禅道（含 MariaDB，常驻 434 MiB）。
Compose 里每个服务的 `mem_limit` 都是按实测值定的：

| 服务 | 上限 | 依据 |
| --- | --- | --- |
| MySQL | 384 MB | `innodb_buffer_pool_size=128M` + 连接开销 |
| Redis | 96 MB | `maxmemory 64mb` + 进程基座 |
| 后端 | 384 MB | 单 worker、不装 torch/paddle |

**改大之前先看容量文档**。不设上限的容器会把禅道一起拖垮，而禅道是你们项目管理要用的。

## 四、两个反复踩到的坑（已写进配置，别改回去）

### 4.1 `mysqladmin ping` 不能用来判就绪

它在**认证失败时也返回成功**，会导致容器"看起来就绪但连不上"。
compose 的 healthcheck 用的是真实查询 `SELECT 1`。

更隐蔽的是：MySQL 容器**初始化期间会短暂接受连接**，此时 `SELECT 1` 也可能通过。
若写脚本等待就绪，需要**连续多次探测通过**才算数（我们的验证脚本就是这么做的）。

### 4.2 不要用 `latest` 标签

MySQL 必须是 `mysql:9.7`：**8.0 已于 2026-04-30 EOL**，而 **9.0–9.6 是创新版、
只支持到下一个季度版发布为止、已全部作废**（见 ADR-0008）。
`latest` 会让你在某次例行更新后被动换到另一个大版本。

同理，Python 基座镜像用 `python:3.14-slim`，且 Dockerfile 里有构建期断言
校验它不是 free-threaded 变体（见 ADR-0009）。

## 五、日志与排查

```bash
docker compose -f docker-compose.prod.yml logs -f backend     # 后端日志
docker compose -f docker-compose.prod.yml ps                   # 各服务状态
docker stats --no-stream                                       # 实时内存占用

# 健康检查（含运行环境自查：python 版本与是否 free-threaded）
curl -s http://127.0.0.1:8000/api/v1/health | python -m json.tool
```

后端日志每行都带 `request_id`，与响应体里的 `request_id` 一致 ——
用户报障时让他提供这个号，可直接定位到具体请求。
