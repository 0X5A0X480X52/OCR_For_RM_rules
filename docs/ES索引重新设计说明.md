# ES 索引重新设计说明

## 概述

基于清洗后的数据重新设计了 Elasticsearch 索引结构，现在支持两种索引类型：

- **chunks**: 细粒度的文本块索引（清洗后的chunk数据）
- **sections**: 粗粒度的章节索引（聚合后的section数据）

每条记录都保留完整的来源信息，包括文档名称、页码范围、位置等。

## 索引结构

### Chunks 索引 (robomaster_docs_chunks)

```json
{
  "chunk_id": "文档ID#chunk#序号",
  "doc_name": "原始文档名称",
  "doc_id": "标准化的文档ID",
  "content": "文本内容",
  "type": "chunk类型: heading/paragraph/list_item",
  "source_pages": [页码列表],
  "page_range": {
    "first": 起始页,
    "last": 结束页
  },
  "bbox_range": {
    "left": 左边界,
    "top": 上边界,
    "right": 右边界,
    "bottom": 下边界
  },
  "confidence_avg": OCR平均置信度,
  "node_count": 包含的原始节点数量,
  "meta": {
    "first_page": 首页,
    "last_page": 末页,
    "indent_x": 缩进位置,
    "height_avg": 平均高度
  }
}
```

### Sections 索引 (robomaster_docs_sections)

```json
{
  "section_id": "文档ID#section#序号",
  "doc_name": "原始文档名称",
  "doc_id": "标准化的文档ID",
  "heading": "章节标题",
  "content": "完整内容（标题+正文）",
  "source_pages": [页码列表],
  "page_range": {
    "first": 起始页,
    "last": 结束页
  },
  "chunk_count": 包含的chunk数量,
  "chunk_types": {
    "heading": 数量,
    "paragraph": 数量,
    "list_item": 数量
  },
  "heading_chunk_id": 标题chunk的ID,
  "content_chunk_ids": [内容chunk的ID列表]
}
```

## 使用流程

### 1. 完整流程（OCR + 清洗 + 索引）

```bash
# 执行OCR、清洗并索引到ES
python main.py --clean

# 仅OCR和清洗，不索引（离线处理）
python main.py --clean --no-es
```

### 2. 离线清洗模式

对已有的OCR输出进行清洗：

```bash
python main.py --clean-only output/quick_run_test
```

### 3. 离线索引模式

将已清洗的数据索引到ES：

```bash
python main.py --index-only output/quick_run_test
```

## 搜索示例

### Python API

```python
from src.es_client import ESClient

es_client = ESClient()

# 搜索 chunks（细粒度）
chunks_results = es_client.search_chunks("机器人", size=10)
for result in chunks_results:
    print(f"文档: {result['doc_name']}")
    print(f"页码: {result['source_pages']}")
    print(f"内容: {result['content'][:100]}...")
    print(f"评分: {result['score']}")
    if 'highlight' in result:
        print(f"高亮: {result['highlight']}")

# 搜索 sections（粗粒度，包含标题）
sections_results = es_client.search_sections("比赛规则", size=5)
for result in sections_results:
    print(f"文档: {result['doc_name']}")
    print(f"页码范围: {result['page_range']}")
    print(f"标题: {result['heading']}")
    print(f"评分: {result['score']}")

# 按特定文档搜索
doc_id = "RoboMaster_2026_机甲大师超级对抗赛比赛规则手册V1.0.0（20251021）"
chunks = es_client.search_chunks("装甲板", doc_id=doc_id)

# 按ID获取
chunk_id = f"{doc_id}#chunk#100"
chunk = es_client.get_chunk_by_id(chunk_id)

section_id = f"{doc_id}#section#10"
section = es_client.get_section_by_id(section_id)
```

### 测试脚本

```bash
# 测试ES搜索功能
python test_es_search.py
```

## 来源信息追溯

每条ES记录包含完整的来源信息：

1. **文档来源**:
   - `doc_name`: 原始文档名称
   - `doc_id`: 标准化ID

2. **页码信息**:
   - `source_pages`: 包含的所有页码
   - `page_range.first/last`: 起止页码

3. **位置信息**:
   - `bbox_range`: 在页面中的矩形位置
   - `meta.indent_x`: 缩进位置

4. **关联信息**:
   - Chunks: 通过 `id` 字段关联
   - Sections: 通过 `heading_chunk_id` 和 `content_chunk_ids` 关联到具体chunks

## 数据文件结构

```
output/
├── quick_run_test/  # 或 run_YYYYMMDD_HHMMSS/
    ├── 文档名1/
    │   ├── pages/  # 原始页面数据
    │   │   ├── page_001.json
    │   │   ├── page_001.txt
    │   │   └── ...
    │   ├── cleaned_chunks.json  # 清洗后的chunks（可索引到ES）
    │   ├── cleaned_basic_part.json  # 聚合后的sections（可索引到ES）
    │   └── cleaner.log
    ├── 文档名2/
    │   └── ...
    └── processing_report.json
```

## 优势

1. **双层索引**:
   - Chunks: 适合精确检索，返回具体段落
   - Sections: 适合章节检索，返回完整语境

2. **完整来源**:
   - 每条记录都有文档名、页码、位置信息
   - 可追溯到原始PDF页面

3. **高亮支持**:
   - 搜索结果自动高亮匹配内容
   - 便于快速定位

4. **灵活查询**:
   - 可按文档过滤
   - 支持全文搜索和字段搜索
   - IK分词器支持中文

5. **分离式流程**:
   - OCR、清洗、索引可独立执行
   - 便于离线处理和批量更新

## 注意事项

1. 原始OCR数据（旧的documents结构）不再索引到ES
2. 必须先执行 `--clean` 生成清洗数据才能索引
3. ES索引名称变更：
   - 旧: `robomaster_docs`
   - 新: `robomaster_docs_chunks`, `robomaster_docs_sections`
4. 首次使用会自动创建新索引（删除旧索引）
