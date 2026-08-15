---
name: document-ingestion
description: 上传文档到知识库（CSV/PDF/doc），自动完成解析→分块→向量化→元数据入库。当用户需要上传文档、导入数据、构建知识库时使用。
allowed_tools: [parse_document, chunk_document]
---

## Description
文档摄入：上传 → 解析（pypdf/pymupdf）→ 分块（recursive）→ 向量化（Milvus）→ 元数据（MySQL），个人文档自动脱敏。

## Trigger
用户上传文档/导入数据/构建知识库时激活。触发关键词：上传/导入/解析/入库。

## Architecture（按序加载）
1. Rules（先读边界，再行动）：
   - [Load Shared Rules: identity](../_shared/rules/identity.md)
   - [Load Shared Rules: fallback](../_shared/rules/fallback.md)
   - [Load Rules: privacy](./rules/privacy.md)
2. Commands（执行流程）：
   - [Load Command: ingest-doc](./commands/ingest-doc.md)
3. Scripts（调用示例，按需引用）：
   - [Load Script: upload-example](./scripts/upload-example.md)
