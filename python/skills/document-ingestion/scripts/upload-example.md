# Script: upload-example（上传调用示例）

> 编排契约示例；接口参数以 API 文档为准。

## HTTP 调用
```
POST /api/v1/documents/upload
multipart: file=<文档>  dataset_name=<数据集名>  chunk_strategy=auto
```

## 返回
`{dataset_id, chunks_count, status}`
