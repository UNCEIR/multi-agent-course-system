-- ============================================================
-- init-db.sql — 公选课系统 MySQL 初始化
-- 库名: course_system (密码: 123456,见 docker-compose.yml)
-- 表清单:
--   course_records   — v1 课程结构化数据(500 门公选课)
--   course_chunks    — v1 课程文本块(每课 4 块:basic/schedule_capacity/learning_profile/audience_tags)
--   document_records — v2 文档摄入 dataset 级元数据(源文档)
--   document_chunks  — v2 文档摄入 chunk 级元数据(分块)
-- source of truth: 本文件是建表唯一来源,代码层(course_repo/document_repo)不建表只 CRUD
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
