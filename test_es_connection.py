"""测试ES连接和索引创建"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.es_client import ESClient

try:
    print("连接ES...")
    es_client = ESClient()
    print(f"ES客户端创建成功")
    
    print("\n创建索引...")
    es_client.create_index()
    print("索引创建成功!")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
