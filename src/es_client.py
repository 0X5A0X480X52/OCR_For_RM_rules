"""Elasticsearch 客户端模块"""
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from elasticsearch import Elasticsearch, helpers
from config import ES_HOST, ES_INDEX_NAME, ES_BULK_SIZE


class ESClient:
    """Elasticsearch 客户端，负责索引创建、文档批量写入和查询"""
    
    def __init__(self, host: str = ES_HOST):
        # Set a reasonable request timeout to avoid immediate connection timeouts
        self.client = Elasticsearch([host], request_timeout=30)
        self.index_name = ES_INDEX_NAME
        self.bulk_size = ES_BULK_SIZE
        
    def create_index(self):
        """创建带 IK 分词器的索引"""
        index_body = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "ik_max": {
                            "tokenizer": "ik_max_word"
                        },
                        "ik_smart": {
                            "tokenizer": "ik_smart"
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "global_id": {
                        "type": "keyword"
                    },
                    "doc_id": {
                        "type": "keyword"
                    },
                    "source": {
                        "type": "keyword"
                    },
                    "path": {
                        "type": "keyword"
                    },
                    "parent_path": {
                        "type": "keyword"
                    },
                    "source_page": {
                        "type": "integer"
                    },
                    "content_type": {
                        "type": "keyword"
                    },
                    "content": {
                        "type": "text",
                        "analyzer": "ik_max",
                        "fields": {
                            "keyword": {
                                "type": "keyword",
                                "ignore_above": 512
                            },
                            "smart": {
                                "type": "text",
                                "analyzer": "ik_smart"
                            }
                        }
                    },
                    "bbox": {
                        "type": "object",
                        "properties": {
                            "left": {"type": "float"},
                            "top": {"type": "float"},
                            "right": {"type": "float"},
                            "bottom": {"type": "float"}
                        }
                    },
                    "table_structure": {
                        "type": "object",
                        "enabled": False
                    },
                    "doc_node_count": {
                        "type": "integer"
                    },
                    "ocr_confidence": {
                        "type": "float"
                    },
                    "created_at": {
                        "type": "date"
                    }
                }
            }
        }
        
        if self.client.indices.exists(index=self.index_name):
            print(f"索引 {self.index_name} 已存在，删除并重建...")
            self.client.indices.delete(index=self.index_name)
        
        self.client.indices.create(index=self.index_name, body=index_body)
        print(f"索引 {self.index_name} 创建成功")
    
    def generate_global_id(self, doc_id: str, path: str) -> str:
        """生成全局唯一 ID"""
        return hashlib.sha1(f"{doc_id}#{path}".encode()).hexdigest()
    
    def bulk_index(self, documents: List[Dict[str, Any]]) -> Dict[str, int]:
        """批量索引文档"""
        success_count = 0
        error_count = 0
        
        actions = []
        for doc in documents:
            # 生成 global_id
            doc["global_id"] = self.generate_global_id(doc["doc_id"], doc["path"])
            doc["created_at"] = datetime.utcnow().isoformat()
            
            action = {
                "_index": self.index_name,
                "_id": doc["global_id"],
                "_source": doc
            }
            actions.append(action)
        
        # 批量写入
        for i in range(0, len(actions), self.bulk_size):
            batch = actions[i:i + self.bulk_size]
            try:
                success, errors = helpers.bulk(
                    self.client,
                    batch,
                    raise_on_error=False,
                    stats_only=False
                )
                success_count += len(batch) - len(errors)
                error_count += len(errors)
            except Exception as e:
                print(f"批量索引出错: {e}")
                error_count += len(batch)
        
        return {"success": success_count, "error": error_count}
    
    def update_doc_node_count(self, doc_id: str, node_count: int):
        """更新文档的节点总数"""
        query = {
            "script": {
                "source": "ctx._source.doc_node_count = params.count",
                "params": {
                    "count": node_count
                }
            },
            "query": {
                "term": {
                    "doc_id": doc_id
                }
            }
        }
        
        self.client.update_by_query(index=self.index_name, body=query)
    
    def get_by_global_id(self, global_id: str) -> Optional[Dict[str, Any]]:
        """根据 global_id 查询文档"""
        try:
            result = self.client.get(index=self.index_name, id=global_id)
            return result["_source"]
        except:
            return None
    
    def search_by_path(self, path: str) -> List[Dict[str, Any]]:
        """根据 path 查询文档"""
        query = {
            "query": {
                "term": {
                    "path": path
                }
            }
        }
        
        result = self.client.search(index=self.index_name, body=query)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    
    def search_content(self, text: str, size: int = 10) -> List[Dict[str, Any]]:
        """全文搜索"""
        query = {
            "query": {
                "match": {
                    "content": {
                        "query": text,
                        "analyzer": "ik_smart"
                    }
                }
            },
            "size": size
        }
        
        result = self.client.search(index=self.index_name, body=query)
        return [hit["_source"] for hit in result["hits"]["hits"]]
