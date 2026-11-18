# 审查文档归档管理

## 用户需求依据

- 本次聊天，用户要求悬停审查条目时在右侧覆盖显示归档图标，背景从透明过渡到白色，图标默认灰色、悬停为红色，归档后提示到个人中心恢复或彻底删除。
- 同一请求要求个人中心增加归档管理卡片，提供还原和彻底删除，图标样式与列表归档一致。附图标出目标条目。

## 当前任务理解

每个审查条目独立归档，可从个人中心还原。彻底删除需再次确认，仅对归档且已结束的任务生效。删除报告与风险记录，解绑关联问答并保留历史消息。共用原件保留，最后一份审查移除时清理无其他引用且由当前用户上传的原件与报告文件。归档期间任务可继续运行。

## 实施方案

1. 增加归档状态、筛选及归档与还原接口。数据库层校验所有权与状态。
2. 删除归档审查及其独占记录，标记可删除的存储对象并重试清理，保护仍被引用的文件。
3. 在审查和个人中心复用悬停图标样式，验证归档、还原、删除以及共享文件。

## 分工与施工清单

由主 agent 实施和验证。

| 路径 | 职责 | 变更 | 状态 |
| --- | --- | --- | --- |
| `backend-java/src/main/java/com/lawwiz/business/review/{ReviewController,ReviewMapper,ReviewService}.java` | 归档筛选、归档与还原、删除审查关联记录 | 修改 | 已完成 |
| `backend-java/src/main/java/com/lawwiz/business/qa/{QaMapper,QaReviewLinks}.java` | 解绑已删除报告的问答会话 | 修改及新增 | 已完成 |
| `backend-java/src/main/java/com/lawwiz/business/files/{BusinessFiles,FileMapper,ObjectStorage}.java` | 保护共享文件并清理已无引用的文件 | 修改 | 已完成 |
| `backend-java/src/main/java/com/lawwiz/business/BusinessApplication.java` | 启用持久清理失败后的定期重试 | 修改 | 已完成 |
| `backend-java/src/test/java/com/lawwiz/business/review/ReviewArchiveTest.java` | 归档与彻底删除的状态边界 | 新增 | 已完成 |
| `deploy/mysql-init/10-business-schema.sql`、`deploy/migrations/20261119-review-archive.sql`、`deploy/README.md` | 新库和已有库的归档及文件清理字段 | 修改及新增 | 已完成 |
| `frontend/src/{api/review.ts,api/types.ts,views/ReviewView.vue,views/MeView.vue,components/ReviewRowActions.vue}` | 归档入口、管理卡片及共用悬停样式 | 修改及新增 | 已完成 |
| `frontend/src/main.ts` | 为通知和确认弹窗加载组件样式 | 修改 | 已完成 |
| `docs/{04-数据库设计.md,05-接口设计.md,06-MVP演示指南.md,FILE_MAP.md,tasks/README.md}` | 契约、演示和任务记录 | 修改 | 已完成 |

## 验证结果与未解决事项

- Git 归档的前端锁定依赖、lint、改动文件格式检查、类型检查与生产构建通过，Java 21 构建和七个测试通过。已有本机 MySQL 卷已验证升级字段，业务前后端已更新。
- 用独立开发账号在浏览器验证了叠层的透明到白色渐变、图标灰到红的悬停状态、右上角通知、个人中心还原与删除确认。取消确认后保留了原条目。用另一个测试账号验证跨用户归档被拒绝，并核对未归档及进行中任务的删除边界。
- 两份真实生成的测试报告共用同一原件。删除第一份后，第二份报告与原件均可读取，关联问答保留且解除绑定。删除最后一份后，审查、风险、报告、合同版本和文件元数据均无残留，RustFS 对测试原件和报告均返回 404。
