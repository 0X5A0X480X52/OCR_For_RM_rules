# PDF OCR 文本提取与 ES 检索系统

RoboMaster 比赛文档的 PDF 解析、OCR 文字提取、语义分段和 Elasticsearch 检索系统。

## 功能特性

- **PDF 解析**: 使用 PyMuPDF 和 pdfplumber 提取文本、表格和图片
- **双引擎 OCR**: RapidOCR（快速）+ PaddleOCR（高精度备用）
- **智能分段**: 基于句子边界的语义分段，支持标题识别
- **层级编码**: 文档结构树编码（`001.002.003` 或 `.blk.NNN`）
- **ES 检索**: 带 IK 分词器的全文检索，支持中文
- **溯源功能**: 每个节点保留原始 PDF 位置信息

## 安装依赖

### 1. 启动 Elasticsearch

```powershell
cd docker\elasticsearch-ik
.\build.ps1
docker run -d --name es-ik -p 9200:9200 -e "discovery.type=single-node" -e "xpack.security.enabled=false" -v "C:\esdata:/usr/share/elasticsearch/data" local/elasticsearch-ik:8.10.2
```

### 2. 安装 Python 依赖

```powershell
pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env` 并修改配置：

```bash
cp .env.example .env
```

主要配置项：
- `ES_HOST`: Elasticsearch 地址
- `OCR_CONFIDENCE_THRESHOLD`: OCR 置信度阈值（默认 0.6）
- `MIN_SEGMENT_LENGTH`: 最小分段长度（默认 15 字符）
- `MAX_SEGMENT_LENGTH`: 最大分段长度（默认 500 字符）

## 使用方法

### 运行完整流程

```powershell
python main.py
```

处理流程：
1. 初始化 ES 索引（带 IK 分词器）
2. 遍历 `docs_src/` 中的 PDF 文件
3. 逐页提取文本或 OCR 识别
4. 构建文档结构树并生成路径编码
5. 句子级分段处理
6. 批量索引到 Elasticsearch
7. 生成处理报告

### 查看结果

处理结果保存在 `output/` 目录：
- `*_processed.json`: 每个文档的结构化数据
- `processing_report.json`: 处理统计报告

## 项目结构

```
OCR/
├── docs_src/                 # 源 PDF 文档
├── docker/
│   └── elasticsearch-ik/     # ES Docker 配置
├── src/
│   ├── pdf_parser.py         # PDF 解析器
│   ├── ocr_engine.py         # OCR 引擎
│   ├── path_encoder.py       # 路径编码器
│   ├── segmenter.py          # 分段器
│   └── es_client.py          # ES 客户端
├── config.py                 # 配置管理
├── main.py                   # 主流程
└── requirements.txt          # 依赖列表
```

## 数据结构

### ES 索引字段

- `global_id`: 全局唯一 ID（SHA1）
- `doc_id`: 文档 ID（含版本号）
- `source`: 源文件路径
- `path`: 层级路径编码（如 `001.002.blk.003`）
- `parent_path`: 父节点路径
- `source_page`: 页码
- `content_type`: 内容类型（heading/paragraph/table）
- `content`: 文本内容（IK 分词）
- `bbox`: 边界框 `{left, top, right, bottom}`
- `table_structure`: 表格结构（JSON）
- `doc_node_count`: 文档总节点数
- `ocr_confidence`: OCR 置信度

### 路径编码规则

1. **结构化编号优先**: 识别文档中的 `1.2.3`、`第X章` 等编号
2. **自动块编号**: 无编号内容使用 `.blk.NNN` 后缀
3. **编号映射**: 附录→900+、表/图→特殊标记
4. **全局唯一**: `global_id = SHA1(doc_id + '#' + path)`

示例：
- `001` - 第1章
- `001.002` - 1.2节
- `001.002.003` - 1.2.3段落
- `001.002.blk.005` - 1.2节下的第5个自动块

## 查询示例

```python
from src.es_client import ESClient

client = ESClient()

# 全文搜索
results = client.search_content("机器人", size=10)

# 根据路径查询
results = client.search_by_path("001.002.003")

# 根据 global_id 查询
doc = client.get_by_global_id("<global_id>")
print(doc["source_page"])  # 获取页码
print(doc["bbox"])         # 获取位置
```

## 性能优化

- OCR 使用 ONNX Runtime 加速
- 批量索引（默认 1000 文档/批）
- 低置信度页面才使用 PaddleOCR
- 图片降采样到 300 DPI

## 故障排查

### ES 连接失败
```powershell
# 检查 ES 状态
docker ps | findstr es-ik
curl http://localhost:9200
```

### OCR 识别错误
- 检查依赖是否完整安装
- 调整 `OCR_CONFIDENCE_THRESHOLD`
- 查看 `processing_report.json` 中的错误信息

## License

MIT
