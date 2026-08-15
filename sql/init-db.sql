-- ============================================================
-- init-db.sql — 公选课系统 MySQL 初始化
-- 库名: course_system (密码: 123456,见 docker-compose.yml)
-- 表清单:
--   course_records   — v1 课程结构化数据(500 门公选课)
--   course_chunks    — v1 课程文本块(每课 4 块:basic/schedule_capacity/learning_profile/audience_tags)
--   document_records — v2 文档摄入 dataset 级元数据(源文档)
--   document_chunks  — v2 文档摄入 chunk 级元数据(分块)
--   report_artifacts — v2 Phase2 report(教师端成绩单)产物元数据
--   evaluation_records — v2 Phase2 evaluation(教师端生成→学生端同步)评价档案
--   chat_sessions/chat_messages/chat_memory_entries — v2 Phase2 chat 长期记忆
-- source of truth: 本文件是建表唯一来源,代码层不建表只 CRUD
-- 重建方式: docker compose down -v && docker compose up -d --build
-- 字符集: utf8mb4 / utf8mb4_unicode_ci
-- ============================================================

CREATE DATABASE IF NOT EXISTS course_system DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE course_system;

-- ------------------------------------------------------------ course_records
CREATE TABLE IF NOT EXISTS course_records (
    course_id VARCHAR(64) PRIMARY KEY,
    course_name VARCHAR(255) NOT NULL,
    teacher VARCHAR(128) DEFAULT '',
    credits DECIMAL(4,2) DEFAULT 0,
    course_type VARCHAR(64) DEFAULT '',
    course_category VARCHAR(128) DEFAULT '',
    domain VARCHAR(128) DEFAULT '',
    campus VARCHAR(64) DEFAULT '',
    time_slot VARCHAR(128) DEFAULT '',
    capacity INT DEFAULT 0,
    current_enrolled INT DEFAULT 0,
    popularity_level TINYINT DEFAULT 0,
    has_exam TINYINT DEFAULT 0,
    group_work_required TINYINT DEFAULT 0,
    tags TEXT,
    raw_json JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    search_text TEXT GENERATED ALWAYS AS (CONCAT_WS(' ', course_name, teacher, course_category, domain, campus, time_slot, tags)) STORED,
    FULLTEXT INDEX ft_search_text (search_text) WITH PARSER ngram,
    INDEX idx_domain (domain),
    INDEX idx_course_category (course_category),
    INDEX idx_campus (campus),
    INDEX idx_popularity_enrolled (popularity_level DESC, current_enrolled DESC, course_id ASC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ course_chunks
CREATE TABLE IF NOT EXISTS course_chunks (
    chunk_id VARCHAR(128) PRIMARY KEY,
    course_id VARCHAR(64) NOT NULL,
    chunk_index INT NOT NULL,
    chunk_type VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    metadata_json JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_course_chunks_course (course_id),
    INDEX idx_course_chunks_type (chunk_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ document_records
CREATE TABLE IF NOT EXISTS document_records (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    dataset_id VARCHAR(64) NOT NULL UNIQUE,
    dataset_name VARCHAR(255) NOT NULL,
    source_doc_name VARCHAR(512) NOT NULL,
    storage_path VARCHAR(1024) NOT NULL,
    file_type VARCHAR(16) NOT NULL,
    file_size BIGINT DEFAULT 0,
    chunk_strategy VARCHAR(32) DEFAULT 'auto',
    chunks_count INT DEFAULT 0,
    status VARCHAR(16) DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_doc_records_dataset_name (dataset_name),
    INDEX idx_doc_records_status (status),
    INDEX idx_doc_records_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ document_chunks
CREATE TABLE IF NOT EXISTS document_chunks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    chunk_id VARCHAR(64) NOT NULL UNIQUE,
    dataset_id VARCHAR(64) NOT NULL,
    chunk_index INT NOT NULL,
    chunk_type VARCHAR(32) DEFAULT 'generic_fixed',
    content_preview VARCHAR(512) DEFAULT '',
    page_number INT DEFAULT 0,
    milvus_vector_id VARCHAR(128) DEFAULT '',
    content TEXT NOT NULL,
    metadata_json JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_doc_chunks_dataset (dataset_id),
    INDEX idx_doc_chunks_type (chunk_type),
    INDEX idx_doc_chunks_page (dataset_id, page_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ report_artifacts
-- report(教师端批量成绩单)产物元数据：一学生一行，支持失败重试/下载寻址/审计
CREATE TABLE IF NOT EXISTS report_artifacts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id VARCHAR(32) NOT NULL,
    student_id VARCHAR(64) NOT NULL,
    student_name VARCHAR(128) NOT NULL DEFAULT '',
    format VARCHAR(8) NOT NULL DEFAULT 'pdf',          -- pdf | html
    status VARCHAR(16) NOT NULL DEFAULT 'ok',           -- ok | failed
    file_key VARCHAR(512) NOT NULL DEFAULT '',          -- MinIO 对象键或本地相对路径
    token_expires_at DATETIME DEFAULT NULL,             -- 下载 token 过期时间（TTL 校验落点）
    error_code VARCHAR(64) DEFAULT '',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_report_artifacts_batch (batch_id),
    INDEX idx_report_artifacts_student (student_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ evaluation_records
-- evaluation(教师端生成→学生端同步)评价档案：append 保留历史，学生端只读本人
CREATE TABLE IF NOT EXISTS evaluation_records (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    target_user_id VARCHAR(64) NOT NULL,
    comment_type VARCHAR(32) NOT NULL,                 -- semester_summary|encouragement|improvement_advice|recommendation
    radar_json JSON,                                   -- 维度提案 + 确定性雷达值
    comment TEXT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'generated',   -- generated | fallback
    generated_by VARCHAR(64) DEFAULT '',               -- 教师 user_id（临时口径，不校验）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_evaluation_user_time (target_user_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ chat_sessions
-- chat 会话元数据：会话归属/统计/记忆提取水位（last_extracted_seq 幂等标记）
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL DEFAULT '',
    message_count INT NOT NULL DEFAULT 0,
    last_extracted_seq INT NOT NULL DEFAULT 0,          -- 记忆提取水位（增量幂等）
    last_failure_at BIGINT NOT NULL DEFAULT 0,          -- 提取失败时间戳（epoch 秒，退避用）
    status VARCHAR(16) NOT NULL DEFAULT 'active',        -- active | closed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_chat_sessions_user (user_id, updated_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ chat_messages
-- chat 会话记录（append-only）：用户当前通话的消息历史，可查询/可审计/是记忆提取源
CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    seq INT NOT NULL,
    role VARCHAR(16) NOT NULL,                           -- user | assistant | tool
    content MEDIUMTEXT,
    tool_calls_json JSON,                                -- assistant 工具调用（审计）
    usage_json JSON,                                     -- token 统计（Phase 4 指标源）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_chat_messages_session_seq (session_id, seq),
    INDEX idx_chat_messages_user (user_id, seq),
    INDEX idx_chat_messages_session (session_id, seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ chat_memory_entries
-- 跨会话长期记忆：按 user_id 隔离，新会话首轮注入；AGENTS.md 不再承载用户级内容
CREATE TABLE IF NOT EXISTS chat_memory_entries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    kind VARCHAR(16) NOT NULL DEFAULT 'fact',            -- preference | fact | decision
    content TEXT NOT NULL,
    content_hash CHAR(32) NOT NULL,                      -- NFKC 归一后 md5（精确去重键）
    source_session_id VARCHAR(64) NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_memory_dedup (user_id, kind, content_hash),
    INDEX idx_memory_entries_user (user_id, updated_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
