"""配置管理模块"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 项目根目录
PROJECT_ROOT = Path(__file__).parent
DOCS_SRC_DIR = PROJECT_ROOT / "docs_src"
OUTPUT_DIR = PROJECT_ROOT / "output"

# Elasticsearch 配置
ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
ES_INDEX_NAME = os.getenv("ES_INDEX_NAME", "robomaster_docs")
ES_BULK_SIZE = int(os.getenv("ES_BULK_SIZE", "1000"))

# OCR 配置
OCR_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.6"))
USE_GPU = os.getenv("USE_GPU", "false").lower() == "true"

# 分段配置
MIN_SEGMENT_LENGTH = int(os.getenv("MIN_SEGMENT_LENGTH", "15"))
MAX_SEGMENT_LENGTH = int(os.getenv("MAX_SEGMENT_LENGTH", "500"))

# 编号映射表（非标准编号到数字路径的映射规则）
NUMBERING_MAPPING = {
    "附录": 900,
    "annex": 900,
    "appendix": 900,
    "表": "table",
    "图": "figure",
    "Fig": "figure",
    "Table": "table",
}

# 确保输出目录存在
OUTPUT_DIR.mkdir(exist_ok=True)
