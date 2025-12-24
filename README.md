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

### 2. 安装 Python 依赖（推荐使用虚拟环境）

项目包含自动引导脚本 `run.ps1`，会在运行前检查并创建 `.venv`，激活后安装依赖并运行完整流程（推荐）：

```powershell
# 推荐：一键引导（会创建/激活 .venv，安装依赖并运行）
.\run.ps1
```

如果希望手动控制虚拟环境和依赖安装，请按下面步骤操作：

```powershell
# 在 PowerShell 中创建并激活虚拟环境
python -m venv .venv
& .\.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

仓库中还提供 `setup_venv.ps1` 用于仅创建/激活虚拟环境：

```powershell
.\setup_venv.ps1
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

推荐使用 `.\run.ps1` 来执行完整流程（包含 ES 启动、虚拟环境的检查/创建、依赖安装和主程序运行）：

```powershell
# 推荐：一键运行（Windows PowerShell）
.\run.ps1
```

或者在已激活虚拟环境中单独执行：

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

## 索引与清洗（Chunks / Sections） 🔧

从清洗后的数据我们采用**双层索引**策略：

- **Chunks（细粒度）**: `robomaster_docs_chunks` - 每个 chunk 是语义连续、主题一致的文本块，适合精确定位具体段落。
- **Sections（粗粒度）**: `robomaster_docs_sections` - 按标题/章节聚合的内容，便于理解完整语境。

索引会保留完整的来源信息（`doc_name`/`doc_id`、`source_pages`、`page_range`、`bbox_range`、`confidence_avg` 等），并支持高亮检索。

### 常用命令（CLI）

```powershell
# 完整流程（默认启用清洗并索引）: OCR -> 清洗 -> 索引
python main.py

# 完整流程但不索引（仅本地输出清洗结果）
python main.py --no-es

# 若想禁用清洗（仅 OCR -> 保存原始 _processed.json），使用 --no-clean
python main.py --no-clean

# 仅对已有输出目录进行清洗
python main.py --clean-only output/run_YYYYMMDD_HHMMSS

# 仅对已有清洗结果进行索引（离线索引）
python main.py --index-only output/run_YYYYMMDD_HHMMSS
```

> 提示：`run.ps1` 提供一键引导（包含虚拟环境、依赖安装、ES 启动和完整流程），推荐在 Windows 上直接使用。

## 输出文件与目录结构 📁

运行后会在 `output/` 下生成按时间的 `run_YYYYMMDD_HHMMSS/` 任务目录，单个文档目录内典型文件：

- `pages/page_###.json`, `pages/page_###.txt`：每页的原始 PyMuPDF/OCR 审计文件
- `*_processed.json`：主流程生成的原始节点列表（已废弃为ES索引来源，保留审计）
- `cleaned_chunks.json`：一级清洗（chunk）输出，可直接索引到 chunks 索引
- `cleaned_basic_part.json`：二级聚合（section）输出，可直接索引到 sections 索引
- `cleaner.log`：清洗审计日志
- `processing_report.json`：任务统计报告

## 清洗模块（TextCleaner）参数（默认值）

清洗器核心参数可在 `src/text_cleaner.py` 或在 `main.py` 中调用时传入：

- `confidence_threshold=0.1`：OCR 置信度阈值，低于丢弃
- `short_line_threshold=20`：短行长度阈值（标题判定）
- `height_ratio_threshold=1.3`：字号/高度突变倍数用于标题判断
- `min_gap_threshold=15.0`：段间距阈值（像素），用于强断开

这些规则实现了“先贪婪合并、再用强信号切断”的策略，使得生成的 chunk 更加语义友好、检索友好。

## 配置（`config.py`）与常用环境变量 ⚙️

主要配置:

- `ES_HOST`（默认 `http://localhost:9200`）
- `ES_INDEX_NAME`（默认 `robomaster_docs`，最终索引为 `{ES_INDEX_NAME}_chunks` 和 `{ES_INDEX_NAME}_sections`）
- `ES_BULK_SIZE`（批量写入大小，默认 `1000`）
- `OCR_CONFIDENCE_THRESHOLD`（OCR 阈值，默认 `0.6`）
- `USE_GPU`（是否使用 GPU：`true/false`）
- `MIN_SEGMENT_LENGTH`, `MAX_SEGMENT_LENGTH`（分段长度上下限，默认 `15` / `500`）

可以通过 `.env` 或环境变量覆盖上述配置。

## ES 兼容性与测试 ✅

- 推荐 Elasticsearch 服务器版本：**8.10.2**（项目中使用并测试通过）
- 推荐 Python 客户端版本：**elasticsearch==8.10.0**（以匹配服务器）

常用测试脚本：

```powershell
# ES 连接与索引测试
python test_es_connection.py
python test_es_search.py
```

已知控制台输出中可能遇到 GBK 编码错误 (Windows 环境)，可以用：

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

## License

MIT
