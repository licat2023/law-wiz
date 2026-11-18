# 智法宝 Java 业务后端

Java 21、Spring Boot MVC、MyBatis 和 Spring Data Redis。当前迁移切片包括用户鉴权、健康检查、普通问答、报告追问及引用快照。问答通过 `LAWWIZ_AI_SERVICE_BASE_URL` 和 `LAWWIZ_AI_SERVICE_TOKEN` 访问独立推理服务。

合同上传以 `LAWWIZ_STORAGE_S3_ENDPOINT`、`LAWWIZ_STORAGE_S3_ACCESS_KEY`、`LAWWIZ_STORAGE_S3_SECRET_KEY` 和 `LAWWIZ_STORAGE_S3_BUCKET` 配置 RustFS。请预先创建业务桶。旧文件记录依照 `storage_bucket` 定位，迁移期间可用 `LAWWIZ_STORAGE_LOCAL_ROOT` 挂载旧文件卷。

从本目录运行 `mvn test`。本地联调可指定已有的 MySQL 业务库和 Redis。使用 `LAWWIZ_JDBC_URL`、`LAWWIZ_DB_USER`、`LAWWIZ_DB_PASSWORD`、`LAWWIZ_REDIS_URL`、`LAWWIZ_JWT_SECRET` 和 `LAWWIZ_SERVER_PORT` 配置连接后，运行 `mvn spring-boot:run`。开发验证码仅用于隔离环境。

迁移期间的数据库初始化沿用[现有部署说明](../deploy/README.md)，当前启用的业务后端和验收范围见[迁移记录](../docs/tasks/T20261118-01-spring-backend-migration.md)。
