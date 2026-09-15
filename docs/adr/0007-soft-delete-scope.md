# 软删除只用于需要保留历史的业务表；`user` 表硬删除

## 背景与决策

项目最初在所有业务表上统一使用 `deleted_at` 软删除，并试图用 `uk(phone, deleted_at)` 表达"未删除的行唯一、已删除的行可以并存"，以支持"注销后重新注册同一手机号"。

**在 MySQL 8.0.46 上实测后，该方案被证伪。**

**决策**：

1. **`user` 表采用硬删除**：`phone` / `email` 用普通唯一索引 `uk_user_phone(phone)`、`uk_user_email(email)` 保证唯一。
2. **仅需要保留历史的表使用 `deleted_at`**：`contract`、`contract_version`、`review_task`、`kb_document`、`qa_session`、`file_object`。
3. 所有表的唯一索引**一律建立在业务列上，不得包含 `deleted_at`**。

## 实测证据（2026-09-13，MySQL 8.0.46）

```sql
CREATE TABLE u (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  phone VARCHAR(20) NULL DEFAULT NULL,
  deleted_at DATETIME(3) NULL DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk (phone, deleted_at)
) ENGINE=InnoDB;

INSERT INTO u (phone) VALUES ('13800000000');   -- 成功
INSERT INTO u (phone) VALUES ('13800000000');   -- 成功  ← 期望失败
INSERT INTO u (phone) VALUES ('13800000000');   -- 成功  ← 期望失败
-- 结果：3 行 (13800000000, NULL) 并存

INSERT INTO u (phone, deleted_at) VALUES ('13800000000','2026-01-01 00:00:00.000');  -- 成功
INSERT INTO u (phone, deleted_at) VALUES ('13800000000','2026-01-01 00:00:00.000');  -- ERROR 1062 Duplicate entry
```

**结论**：MySQL 的唯一索引**不约束 `NULL`**。当 `deleted_at IS NULL` 时，整个索引元组含 `NULL` 而**完全不受唯一性检查**。也就是说，原设计里"未删除的那一行"恰恰是**唯一不受保护的那一行** —— 因果完全反了。唯一约束只在 `deleted_at` 取具体时间值时才生效。

## 被否决的替代方案

- **`uk(phone, deleted_at)`（原方案）**：唯一性对活跃行失效，同一手机号可重复注册，**该约束等于不存在**。
- **用哨兵值代替 `NULL`**（如未删除行写 `'1970-01-01'`）：技术上可行，但要求所有查询都把哨兵当"未删除"处理，一旦有人写了 `deleted_at IS NULL` 就会静默漏掉全部数据；这类陷阱的代价远高于收益。
- **额外增加一个"仅活跃行非空"的辅助列**（未删除时为常量、删除时为 `NULL`，再纳入唯一索引）：能正确表达意图，但为一张表引入一个纯粹服务于索引技巧的列，而本表**根本不需要软删除**，属于为不存在的问题增加复杂度。

## 后果

- `user` 表注销即物理删除行。**这同时满足《个人信息保护法》的要求** —— 用户要求删除账户时，继续保留其手机号与邮箱本身就是隐私风险。软删除在此不是"更安全"，而是"更危险"。
- `user` 若被硬删除，引用它的 `user_profile` 需级联删除或一并清理（`user_profile` 保留 `deleted_at` 但其唯一键 `uk_user_profile_user(user_id, deleted_at)` 仅在**软删除**路径下使用；实际注销走硬删除时该行一并删除）。
- **后续新增表必须遵守本条**：唯一索引不得包含 `deleted_at`。若某张表确实需要"活跃行唯一 + 已删除行并存"，必须新开一条 ADR 讨论方案，而不是默认沿用旧写法。
- 本决策的发现过程（把 DDL 在真实 MySQL 上执行一遍）已写入 [04-数据库设计](../04-数据库设计.md) §2.3 与 §5.1，作为"设计必须可执行验证"的例证。
