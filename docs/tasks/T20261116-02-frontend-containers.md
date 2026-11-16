# T20261116-02 前端镜像与全容器部署

## 用户需求依据

- R1，本次聊天，用户要求“为什么前端不放容器，前端也要有Dockerfile，并进容器编排”。
- R2，本次聊天，用户对本任务工作区安排选择“保留已有改动，直接在当前分支实施”。基线为 `30b4bd9`，已有未提交改动沿用原归属。
- R3，本次聊天，用户补充“那就更改现有的流程，全部用容器”。这取代了沿用宿主机开发启动方式的初步方案。
- R4，本次聊天，用户要求“继续完成上一轮因 usage limit 中断的任务。先检查当前工作区状态，避免重复执行已经完成的修改或命令，然后从未完成步骤继续。保留原有任务范围，不要停下来等人确认。”恢复时确认任务记录已建立，镜像和编排仍待实现。

## 当前任务理解

两个前端各有 Dockerfile，开发和生产 Compose 均启动两个前端、两个后端、MySQL 与 Redis。开发和演示只需要 Docker 环境即可启动应用并初始化空库。生产继续使用现有 1Panel OpenResty 作为 HTTPS 入口，每个站点独立代理到对应前端容器。前端保持同源 `/api`，业务页面支持直接访问和刷新，两个后端继续负责鉴权和上传校验。

实施选择为开发镜像运行 Vite，Compose Watch 同步页面源码，生产镜像使用 Nginx 交付静态资源和代理。后端镜像、空库初始化命令及数据库卷沿用现有设计。已有 1Panel 实例由部署环境维护。

## 实施方案

1. 用锁文件构建各站点，提供 Vite 开发阶段和 Nginx 生产阶段。代理按 Compose 服务名连接 API，保留请求路径、查询参数和转发头。
2. 接入两套编排，为全部服务设置内存预算。开发配置独立于生产，生产站点端口可通过环境变量设置。
3. 更新开发、演示和生产操作入口。在干净源码副本构建并启动两套编排，核对健康检查、站点、API、直接访问页面、上传和服务重建后的代理恢复。

## 分工与施工清单

由主 agent 实施和验收。

| 路径 | 职责 | 变更 | 状态 | 验证要求 |
| --- | --- | --- | --- | --- |
| `frontend/Dockerfile`、`knowledge_base/frontend/Dockerfile` | 各站点开发与生产镜像 | 新增 | 已完成 | 两个站点的容器构建和启动通过 |
| `frontend/.dockerignore`、`knowledge_base/frontend/.dockerignore` | 排除宿主依赖、构建产物及环境配置 | 新增 | 已完成 | 由干净源码构建 |
| `frontend/nginx.conf`、`knowledge_base/frontend/nginx.conf` | 静态内容、上传与同源 API | 新增 | 已完成 | 页面回退、静态资源、API 和上游重建验证通过 |
| `frontend/vite.config.ts`、`frontend/.env.example` | 开发代理指向 Compose 内的业务服务 | 修改 | 已完成 | 业务站点开发代理与源码同步验证通过 |
| `deploy/docker-compose.dev.yml`、`deploy/docker-compose.prod.yml` | 编排六个服务 | 修改 | 已完成 | 两套环境的服务均健康且有内存上限 |
| `deploy/.env.dev.example`、`deploy/.env.example` | 区分开发配置与生产站点入口 | 新增及修改 | 已完成 | 由各自模板准备隔离配置并启动 |
| `deploy/README.md`、`docs/06-MVP演示指南.md` | 容器启动、空库初始化、现有站点迁移和验证 | 修改 | 已完成 | 两套 Compose 空库启动流程通过 |
| `backend/README.md`、`knowledge_base/README.md`、`frontend/README.md`、`knowledge_base/frontend/README.md` | 各子项目的启动入口 | 修改 | 已完成 | 新增文档链接路径核对通过 |
| `README.md`、`AGENTS.md`、`docs/02-技术栈.md`、`docs/03-概要设计.md`、`docs/FILE_MAP.md` | 描述容器化拓扑、关键约定和文件职责 | 修改 | 已完成 | 与实际编排核对一致 |
| `docs/tasks/README.md`、本文 | 记录任务及验收结果 | 修改及新增 | 已完成 | 核对有效需求、入口和验收状态 |

## 验证结果与未解决事项

- 基线检查显示开发 Compose 只包含 MySQL 和 Redis。生产配置中的前端发布步骤要求人工上传 `dist/`。
- 使用 `git archive` 导出的基线和本次运行配置，在隔离的 Compose 项目中完成两套构建与空库启动。两套环境各六个容器均健康并设内存上限，两个前端在开发镜像中通过 lint，并在生产镜像构建中通过类型检查和 Vite 构建。
- 两套环境通过站点同源 API 验证业务及管理员登录、20 MiB 合同上传和 1,179,648 字节语料上传。业务页面直接访问和静态资源返回符合预期，非法 API 路径保留后端的 404。生产业务 API 保留入口转发的 HTTPS 协议和主机名。
- Compose Watch 实际同步两站点新增与编辑的源码。生产分别移除和以新容器 IP 重建两个后端，静态首页持续可访问，API 从 502 恢复正常，两个前端容器均无需重启。
- 生产编排在本机隔离验证。目标主机 OpenResty 站点切换由部署时执行，真实模型和嵌入调用未纳入本次容器验收。
