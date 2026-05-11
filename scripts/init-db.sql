CREATE DATABASE IF NOT EXISTS ecommerce_user DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS ecommerce_product DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS ecommerce_order DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS ecommerce_payment DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS ecommerce_ai DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE ecommerce_ai;

CREATE TABLE IF NOT EXISTS products (
    product_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(64) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    description TEXT,
    brand VARCHAR(128) DEFAULT '',
    seller_id VARCHAR(64) DEFAULT '',
    tags_json JSON,
    rating DECIMAL(3,2) DEFAULT 0,
    review_count INT DEFAULT 0,
    sales_count_30d INT DEFAULT 0,
    cost_price DECIMAL(10,2) DEFAULT 0,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS inventory (
    product_id VARCHAR(64) PRIMARY KEY,
    available_stock INT NOT NULL DEFAULT 0,
    safety_stock INT NOT NULL DEFAULT 50,
    reserved_stock INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_inventory_product FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE IF NOT EXISTS user_behaviors (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    product_id VARCHAR(64) NOT NULL,
    behavior_type VARCHAR(32) NOT NULL,
    category VARCHAR(64) DEFAULT '',
    score DECIMAL(8,4) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_behaviors_user_created (user_id, created_at),
    INDEX idx_user_behaviors_product_created (product_id, created_at)
);

CREATE TABLE IF NOT EXISTS recommendation_feedback (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    request_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    product_id VARCHAR(64) NOT NULL,
    action_type VARCHAR(32) NOT NULL,
    action_value DECIMAL(10,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_feedback_request (request_id),
    INDEX idx_feedback_user_created (user_id, created_at)
);

CREATE TABLE IF NOT EXISTS experiment_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    experiment_name VARCHAR(128) NOT NULL,
    experiment_group VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    request_id VARCHAR(64) NOT NULL,
    metric_name VARCHAR(64) NOT NULL,
    metric_value DECIMAL(10,4) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_experiment_name_group (experiment_name, experiment_group),
    INDEX idx_experiment_user_created (user_id, created_at)
);

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
    popularity_level VARCHAR(32) DEFAULT '',
    tags TEXT,
    raw_json JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
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

INSERT INTO products (product_id, name, category, price, description, brand, seller_id, tags_json, rating, review_count, sales_count_30d, cost_price, is_active) VALUES
('P001', 'iPhone 16 Pro', '手机', 7999.00, 'A18 芯片，专业影像旗舰。', 'Apple', 'S01', JSON_ARRAY('旗舰','新品','5G'), 4.80, 3200, 15000, 5500.00, 1),
('P002', '华为 Mate 70', '手机', 5999.00, '国产旗舰，鸿蒙生态。', '华为', 'S02', JSON_ARRAY('旗舰','国产','鸿蒙'), 4.70, 2800, 12000, 4000.00, 1),
('P003', 'AirPods Pro 3', '耳机', 1899.00, '主动降噪，空间音频。', 'Apple', 'S01', JSON_ARRAY('降噪','无线','新品'), 4.90, 5600, 25000, 1100.00, 1),
('P004', 'Sony WH-1000XM6', '耳机', 2499.00, '头戴降噪旗舰。', 'Sony', 'S03', JSON_ARRAY('头戴','降噪','Hi-Res'), 4.80, 1800, 8000, 1600.00, 1),
('P005', 'iPad Air M3', '平板', 4799.00, '学习办公一体化平板。', 'Apple', 'S01', JSON_ARRAY('学习','办公','M3芯片'), 4.70, 2100, 9000, 3200.00, 1),
('P006', '小米平板7 Pro', '平板', 2499.00, '高性价比娱乐平板。', '小米', 'S04', JSON_ARRAY('性价比','娱乐','120Hz'), 4.50, 1200, 6000, 1700.00, 1),
('P007', 'Anker 140W充电器', '配件', 399.00, '多口快充 GaN。', 'Anker', 'S05', JSON_ARRAY('快充','便携','GaN'), 4.60, 4300, 30000, 200.00, 1),
('P008', '联想拯救者Y9000P', '笔记本', 8999.00, '高性能游戏本。', '联想', 'S06', JSON_ARRAY('游戏','RTX4060','高刷'), 4.70, 900, 3500, 6500.00, 1),
('P009', '戴尔U2724D显示器', '显示器', 3299.00, '高色准办公显示器。', 'Dell', 'S07', JSON_ARRAY('4K','IPS','Type-C'), 4.60, 600, 2000, 2200.00, 1),
('P010', '罗技MX Master 3S', '配件', 749.00, '高效办公鼠标。', '罗技', 'S08', JSON_ARRAY('无线','办公','人体工学'), 4.80, 3800, 18000, 450.00, 1),
('P011', '三星980 Pro 2TB', '存储', 1199.00, 'PCIe4.0 高速 SSD。', '三星', 'S09', JSON_ARRAY('SSD','高速','PCIe4.0'), 4.90, 2100, 10000, 800.00, 1),
('P012', 'Switch 2', '游戏机', 2499.00, '便携主机，新品首发。', 'Nintendo', 'S12', JSON_ARRAY('新品','游戏','多人'), 4.60, 400, 5000, 1800.00, 1)
ON DUPLICATE KEY UPDATE name = VALUES(name), price = VALUES(price), category = VALUES(category), tags_json = VALUES(tags_json), rating = VALUES(rating), review_count = VALUES(review_count), sales_count_30d = VALUES(sales_count_30d), cost_price = VALUES(cost_price), is_active = VALUES(is_active);

INSERT INTO inventory (product_id, available_stock, safety_stock, reserved_stock) VALUES
('P001', 500, 50, 20),
('P002', 300, 50, 10),
('P003', 1000, 100, 30),
('P004', 90, 50, 8),
('P005', 400, 50, 15),
('P006', 600, 50, 12),
('P007', 2000, 200, 40),
('P008', 130, 30, 12),
('P009', 60, 20, 6),
('P010', 500, 80, 20),
('P011', 260, 40, 10),
('P012', 0, 20, 5)
ON DUPLICATE KEY UPDATE available_stock = VALUES(available_stock), safety_stock = VALUES(safety_stock), reserved_stock = VALUES(reserved_stock);

INSERT INTO user_behaviors (user_id, product_id, behavior_type, category, score) VALUES
('U10001', 'P001', 'view', '手机', 1.0),
('U10001', 'P003', 'view', '耳机', 1.0),
('U10001', 'P003', 'purchase', '耳机', 5.0),
('U10001', 'P005', 'view', '平板', 1.0),
('U10001', 'P010', 'click', '配件', 2.0),
('U10002', 'P008', 'view', '笔记本', 1.0),
('U10002', 'P012', 'view', '游戏机', 1.0),
('U10003', 'P011', 'purchase', '存储', 4.0);
