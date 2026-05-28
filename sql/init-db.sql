CREATE DATABASE IF NOT EXISTS ecommerce_user DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS ecommerce_product DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS ecommerce_order DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS ecommerce_payment DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS ecommerce_ai DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE ecommerce_ai;



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
);

CREATE TABLE IF NOT EXISTS course_chunks (
    chunk_id VARCHAR(128) PRIMARY KEY,
    course_id VARCHAR(64) NOT NULL,
    chunk_index INT NOT NULL,
    chunk_type VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    metadata_json JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_course_chunks_course (course_id),
    INDEX idx_course_chunks_type (chunk_type),
    CONSTRAINT fk_course_chunks_course FOREIGN KEY (course_id) REFERENCES course_records(course_id)
);


