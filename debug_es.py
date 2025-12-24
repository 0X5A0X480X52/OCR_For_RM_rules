"""调试ES索引名称"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from config import ES_INDEX_NAME

print(f"ES_INDEX_NAME from config: {ES_INDEX_NAME}")

chunks_index = f"{ES_INDEX_NAME}_chunks"
sections_index = f"{ES_INDEX_NAME}_sections"

print(f"Chunks index: {chunks_index}")
print(f"Sections index: {sections_index}")

# 测试连接
from elasticsearch import Elasticsearch

client = Elasticsearch(["http://localhost:9200"], request_timeout=30)
print(f"\n连接成功")

# 测试exists方法
try:
    result = client.indices.exists(index="test_index")
    print(f"Exists test passed: {result}")
except Exception as e:
    print(f"Exists test failed: {e}")
    import traceback
    traceback.print_exc()

# 尝试列出所有索引
try:
    indices = client.cat.indices(format="json")
    print(f"\n现有索引:")
    for idx in indices:
        print(f"  - {idx['index']}")
except Exception as e:
    print(f"List indices failed: {e}")
