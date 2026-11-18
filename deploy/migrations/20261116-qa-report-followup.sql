-- 已有 MySQL 业务库启用报告追问的结构变更；空库由 MySQL 初始化镜像创建。
-- 只执行一次。普通会话及现有消息原样保留，旧会话的两列默认为 NULL。
ALTER TABLE qa_session
    ADD COLUMN review_task_id BIGINT UNSIGNED NULL,
    ADD COLUMN risk_point_id BIGINT UNSIGNED NULL,
    ADD CONSTRAINT fk_qa_session_review FOREIGN KEY (review_task_id) REFERENCES review_task (id);
