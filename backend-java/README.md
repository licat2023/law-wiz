# 智法宝 Java 业务后端

Java 21、Spring Boot MVC、MyBatis 和 Spring Data Redis。当前迁移切片包括用户注册、登录、令牌轮换与注销、资料、限流和健康检查。

从本目录运行 `mvn test`。本地联调可指定已有的 MySQL 业务库和 Redis。使用 `LAWWIZ_JDBC_URL`、`LAWWIZ_DB_USER`、`LAWWIZ_DB_PASSWORD`、`LAWWIZ_REDIS_URL`、`LAWWIZ_JWT_SECRET` 和 `LAWWIZ_SERVER_PORT` 配置连接后，运行 `mvn spring-boot:run`。开发验证码仅用于隔离环境。

迁移期间的数据库初始化沿用[现有部署说明](../deploy/README.md)，当前启用的业务后端和验收范围见[迁移记录](../docs/tasks/T20261118-01-spring-backend-migration.md)。
