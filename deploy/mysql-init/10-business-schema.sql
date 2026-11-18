-- Creates the Java business schema on a new MySQL volume. Existing databases use explicit upgrades.
CREATE TABLE risk_rule (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    rule_code VARCHAR(32) NOT NULL,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(32),
    risk_level VARCHAR(8) NOT NULL,
    condition_expr TEXT NOT NULL,
    conclusion TEXT NOT NULL,
    suggestion TEXT,
    legal_basis TEXT,
    match_keywords VARCHAR(500),
    is_active BOOL NOT NULL DEFAULT '1',
    deleted_at DATETIME(3),
    created_at DATETIME(3) NOT NULL DEFAULT now(3),
    updated_at DATETIME(3) NOT NULL DEFAULT now(3),
    CONSTRAINT pk_risk_rule PRIMARY KEY (id),
    CONSTRAINT uk_risk_rule_code UNIQUE (rule_code)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX idx_risk_rule_active ON risk_rule (is_active, risk_level);

CREATE TABLE user (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    phone VARCHAR(20),
    email VARCHAR(120),
    password_hash VARCHAR(255) NOT NULL,
    account_type VARCHAR(16) NOT NULL DEFAULT 'personal',
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    last_login_at DATETIME(3),
    created_at DATETIME(3) NOT NULL DEFAULT now(3),
    updated_at DATETIME(3) NOT NULL DEFAULT now(3),
    CONSTRAINT pk_user PRIMARY KEY (id),
    CONSTRAINT uk_user_phone UNIQUE (phone),
    CONSTRAINT uk_user_email UNIQUE (email)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE contract (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    owner_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(200) NOT NULL,
    contract_type VARCHAR(32),
    status VARCHAR(16) NOT NULL DEFAULT 'draft',
    source VARCHAR(16) NOT NULL DEFAULT 'upload',
    current_version_id BIGINT UNSIGNED,
    deleted_at DATETIME(3),
    created_at DATETIME(3) NOT NULL DEFAULT now(3),
    updated_at DATETIME(3) NOT NULL DEFAULT now(3),
    CONSTRAINT pk_contract PRIMARY KEY (id),
    CONSTRAINT fk_contract_owner FOREIGN KEY(owner_id) REFERENCES user (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX idx_contract_owner_status ON contract (owner_id, status, created_at);

CREATE TABLE file_object (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sha256 VARCHAR(64) NOT NULL,
    storage_bucket VARCHAR(64) NOT NULL,
    object_key VARCHAR(512) NOT NULL,
    original_name VARCHAR(255),
    byte_size BIGINT NOT NULL,
    mime_type VARCHAR(128),
    uploader_id BIGINT UNSIGNED,
    deleted_at DATETIME(3),
    purge_requested_at DATETIME(3),
    created_at DATETIME(3) NOT NULL DEFAULT now(3),
    updated_at DATETIME(3) NOT NULL DEFAULT now(3),
    CONSTRAINT pk_file_object PRIMARY KEY (id),
    CONSTRAINT uk_file_object_sha256 UNIQUE (sha256),
    CONSTRAINT fk_file_object_uploader FOREIGN KEY(uploader_id) REFERENCES user (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX idx_file_pending_purge ON file_object (purge_requested_at, id);

CREATE TABLE risk_rule_source (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    risk_rule_id BIGINT UNSIGNED NOT NULL,
    knowledge_base_document_id BIGINT UNSIGNED,
    external_service VARCHAR(64),
    external_knowledge_base_id VARCHAR(128),
    external_document_id VARCHAR(128),
    external_revision_id VARCHAR(128),
    source_snapshot JSON,
    created_at DATETIME(3) NOT NULL DEFAULT now(3),
    CONSTRAINT pk_risk_rule_source PRIMARY KEY (id),
    CONSTRAINT uk_risk_rule_source UNIQUE (risk_rule_id, knowledge_base_document_id),
    CONSTRAINT uk_risk_rule_external_source UNIQUE (risk_rule_id, external_service, external_knowledge_base_id, external_document_id),
    CONSTRAINT fk_rule_source_rule FOREIGN KEY(risk_rule_id) REFERENCES risk_rule (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE user_profile (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    real_name VARCHAR(64),
    org_name VARCHAR(200),
    org_role VARCHAR(64),
    avatar_object_id BIGINT UNSIGNED,
    deleted_at DATETIME(3),
    created_at DATETIME(3) NOT NULL DEFAULT now(3),
    updated_at DATETIME(3) NOT NULL DEFAULT now(3),
    CONSTRAINT pk_user_profile PRIMARY KEY (id),
    CONSTRAINT uk_user_profile_user UNIQUE (user_id),
    CONSTRAINT fk_user_profile_user FOREIGN KEY(user_id) REFERENCES user (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE contract_version (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    contract_id BIGINT UNSIGNED NOT NULL,
    version_no INTEGER NOT NULL,
    file_object_id BIGINT UNSIGNED,
    plain_text LONGTEXT,
    text_source VARCHAR(16),
    page_count INTEGER,
    created_by BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT now(3),
    CONSTRAINT pk_contract_version PRIMARY KEY (id),
    CONSTRAINT uk_contract_version UNIQUE (contract_id, version_no),
    CONSTRAINT fk_contract_version_contract FOREIGN KEY(contract_id) REFERENCES contract (id),
    CONSTRAINT fk_contract_version_file FOREIGN KEY(file_object_id) REFERENCES file_object (id),
    CONSTRAINT fk_contract_version_creator FOREIGN KEY(created_by) REFERENCES user (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE review_task (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    contract_id BIGINT UNSIGNED,
    contract_version_id BIGINT UNSIGNED,
    user_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    stage VARCHAR(32),
    progress INTEGER NOT NULL DEFAULT '0',
    extracted_terms JSON,
    raw_llm_output JSON,
    error_code VARCHAR(64),
    error_message VARCHAR(500),
    started_at DATETIME(3),
    finished_at DATETIME(3),
    archived_at DATETIME(3),
    deleted_at DATETIME(3),
    created_at DATETIME(3) NOT NULL DEFAULT now(3),
    updated_at DATETIME(3) NOT NULL DEFAULT now(3),
    CONSTRAINT pk_review_task PRIMARY KEY (id),
    CONSTRAINT fk_review_task_contract FOREIGN KEY(contract_id) REFERENCES contract (id),
    CONSTRAINT fk_review_task_version FOREIGN KEY(contract_version_id) REFERENCES contract_version (id),
    CONSTRAINT fk_review_task_user FOREIGN KEY(user_id) REFERENCES user (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX idx_review_task_user_status ON review_task (user_id, status, created_at);
CREATE INDEX idx_review_task_user_archive ON review_task (user_id, archived_at, created_at);

CREATE TABLE qa_session (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    review_task_id BIGINT UNSIGNED,
    risk_point_id BIGINT UNSIGNED,
    title VARCHAR(200),
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    message_count INTEGER NOT NULL DEFAULT '0',
    last_message_at DATETIME(3),
    deleted_at DATETIME(3),
    created_at DATETIME(3) NOT NULL DEFAULT now(3),
    updated_at DATETIME(3) NOT NULL DEFAULT now(3),
    CONSTRAINT pk_qa_session PRIMARY KEY (id),
    CONSTRAINT fk_qa_session_user FOREIGN KEY(user_id) REFERENCES user (id),
    CONSTRAINT fk_qa_session_review FOREIGN KEY(review_task_id) REFERENCES review_task (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX idx_qa_session_user ON qa_session (user_id, last_message_at);

CREATE TABLE review_report (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    review_task_id BIGINT UNSIGNED NOT NULL,
    file_object_id BIGINT UNSIGNED,
    format VARCHAR(8) NOT NULL DEFAULT 'pdf',
    summary TEXT,
    high_count INTEGER NOT NULL DEFAULT '0',
    medium_count INTEGER NOT NULL DEFAULT '0',
    low_count INTEGER NOT NULL DEFAULT '0',
    generated_at DATETIME(3) NOT NULL DEFAULT now(3),
    deleted_at DATETIME(3),
    created_at DATETIME(3) NOT NULL DEFAULT now(3),
    updated_at DATETIME(3) NOT NULL DEFAULT now(3),
    CONSTRAINT pk_review_report PRIMARY KEY (id),
    CONSTRAINT uk_review_report_task UNIQUE (review_task_id),
    CONSTRAINT fk_review_report_task FOREIGN KEY(review_task_id) REFERENCES review_task (id),
    CONSTRAINT fk_review_report_file FOREIGN KEY(file_object_id) REFERENCES file_object (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE risk_point (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    review_task_id BIGINT UNSIGNED NOT NULL,
    risk_level VARCHAR(8) NOT NULL,
    risk_category VARCHAR(32),
    clause_title VARCHAR(200),
    clause_text TEXT,
    char_start INTEGER,
    char_end INTEGER,
    description TEXT NOT NULL,
    suggestion TEXT,
    legal_basis TEXT,
    source_type VARCHAR(32) NOT NULL,
    knowledge_base_document_id BIGINT UNSIGNED,
    source_snapshot JSON,
    external_service VARCHAR(64),
    external_document_id VARCHAR(128),
    external_chunk_id VARCHAR(128),
    external_revision_id VARCHAR(128),
    risk_rule_id BIGINT UNSIGNED,
    confidence NUMERIC(3, 2),
    is_dismissed BOOL NOT NULL DEFAULT '0',
    deleted_at DATETIME(3),
    created_at DATETIME(3) NOT NULL DEFAULT now(3),
    updated_at DATETIME(3) NOT NULL DEFAULT now(3),
    CONSTRAINT pk_risk_point PRIMARY KEY (id),
    CONSTRAINT fk_risk_point_task FOREIGN KEY(review_task_id) REFERENCES review_task (id),
    CONSTRAINT fk_risk_point_rule FOREIGN KEY(risk_rule_id) REFERENCES risk_rule (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX idx_risk_point_task_level ON risk_point (review_task_id, risk_level);

CREATE TABLE qa_message (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    qa_session_id BIGINT UNSIGNED NOT NULL,
    `role` VARCHAR(16) NOT NULL,
    content MEDIUMTEXT NOT NULL,
    has_citation BOOL NOT NULL DEFAULT '0',
    model_name VARCHAR(64),
    token_usage INTEGER,
    latency_ms INTEGER,
    created_at DATETIME(3) NOT NULL DEFAULT now(3),
    CONSTRAINT pk_qa_message PRIMARY KEY (id),
    CONSTRAINT fk_qa_message_session FOREIGN KEY(qa_session_id) REFERENCES qa_session (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX idx_qa_message_session ON qa_message (qa_session_id, id);

CREATE TABLE qa_citation (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    qa_message_id BIGINT UNSIGNED NOT NULL,
    knowledge_base_document_id BIGINT UNSIGNED,
    knowledge_base_chunk_id BIGINT UNSIGNED,
    quoted_text TEXT,
    source_snapshot JSON,
    external_service VARCHAR(64),
    external_knowledge_base_id VARCHAR(128),
    external_document_id VARCHAR(128),
    external_chunk_id VARCHAR(128),
    external_revision_id VARCHAR(128),
    external_index_id VARCHAR(128),
    relevance_score NUMERIC(5, 4),
    created_at DATETIME(3) NOT NULL DEFAULT now(3),
    CONSTRAINT pk_qa_citation PRIMARY KEY (id),
    CONSTRAINT fk_qa_citation_message FOREIGN KEY(qa_message_id) REFERENCES qa_message (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

ALTER TABLE contract ADD CONSTRAINT fk_contract_current_version FOREIGN KEY (current_version_id) REFERENCES contract_version (id);
