"""Elasticsearch 客户端模块"""
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from elasticsearch import Elasticsearch, helpers
from config import ES_HOST, ES_INDEX_NAME, ES_BULK_SIZE


class ESClient:
    """Elasticsearch 客户端，负责索引创建、文档批量写入和查询
    
    支持两种索引：
    - chunks: 清洗后的chunk级别数据
    - sections: 聚合后的section级别数据
    """
    
    def __init__(self, host: str = ES_HOST):
        # Set a reasonable request timeout to avoid immediate connection timeouts
        self.client = Elasticsearch([host], request_timeout=30)
        self.chunks_index = f"{ES_INDEX_NAME}_chunks"
        self.sections_index = f"{ES_INDEX_NAME}_sections"
        self.bulk_size = ES_BULK_SIZE
        
    def create_index(self):
        """创建带 IK 分词器的索引（chunks和sections）"""
        # 通用设置
        common_settings = {
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
        }
        
        # Chunks 索引映射（清洗后的chunk数据）
        chunks_mapping = {
            "settings": common_settings,
            "mappings": {
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "doc_name": {"type": "keyword"},
                    "doc_id": {"type": "keyword"},  # 从doc_name生成的标准化ID
                    "content": {
                        "type": "text",
                        "analyzer": "ik_max",
                        "fields": {
                            "keyword": {"type": "keyword", "ignore_above": 512},
                            "smart": {"type": "text", "analyzer": "ik_smart"}
                        }
                    },
                    "type": {"type": "keyword"},  # heading, paragraph, list_item
                    "source_pages": {"type": "integer"},
                    "page_range": {
                        "properties": {
                            "first": {"type": "integer"},
                            "last": {"type": "integer"}
                        }
                    },
                    "bbox_range": {
                        "properties": {
                            "left": {"type": "float"},
                            "top": {"type": "float"},
                            "right": {"type": "float"},
                            "bottom": {"type": "float"}
                        }
                    },
                    "confidence_avg": {"type": "float"},
                    "node_count": {"type": "integer"},
                    "meta": {
                        "properties": {
                            "first_page": {"type": "integer"},
                            "last_page": {"type": "integer"},
                            "indent_x": {"type": "float"},
                            "height_avg": {"type": "float"}
                        }
                    },
                    "created_at": {"type": "date"}
                }
            }
        }
        
        # Sections 索引映射（聚合后的section数据）
        sections_mapping = {
            "settings": common_settings,
            "mappings": {
                "properties": {
                    "section_id": {"type": "keyword"},
                    "doc_name": {"type": "keyword"},
                    "doc_id": {"type": "keyword"},
                    "heading": {
                        "type": "text",
                        "analyzer": "ik_max",
                        "fields": {
                            "keyword": {"type": "keyword", "ignore_above": 512},
                            "smart": {"type": "text", "analyzer": "ik_smart"}
                        }
                    },
                    "content": {
                        "type": "text",
                        "analyzer": "ik_max",
                        "fields": {
                            "keyword": {"type": "keyword", "ignore_above": 512},
                            "smart": {"type": "text", "analyzer": "ik_smart"}
                        }
                    },
                    "source_pages": {"type": "integer"},
                    "page_range": {
                        "properties": {
                            "first": {"type": "integer"},
                            "last": {"type": "integer"}
                        }
                    },
                    "chunk_count": {"type": "integer"},
                    "chunk_types": {"type": "object", "enabled": False},
                    "heading_chunk_id": {"type": "integer"},
                    "content_chunk_ids": {"type": "integer"},
                    "created_at": {"type": "date"}
                }
            }
        }
        
        # 创建 chunks 索引
        try:
            self.client.indices.delete(index=self.chunks_index, ignore=[404])
        except:
            pass
        
        self.client.indices.create(
            index=self.chunks_index,
            settings=chunks_mapping["settings"],
            mappings=chunks_mapping["mappings"]
        )
        print(f"索引 {self.chunks_index} 创建成功")
        
        # 创建 sections 索引
        try:
            self.client.indices.delete(index=self.sections_index, ignore=[404])
        except:
            pass
        
        self.client.indices.create(
            index=self.sections_index,
            settings=sections_mapping["settings"],
            mappings=sections_mapping["mappings"]
        )
        print(f"索引 {self.sections_index} 创建成功")
    
    def generate_chunk_id(self, doc_id: str, chunk_id: int) -> str:
        """生成chunk的全局唯一 ID"""
        return f"{doc_id}#chunk#{chunk_id}"
    
    def generate_section_id(self, doc_id: str, section_idx: int) -> str:
        """生成section的全局唯一 ID"""
        return f"{doc_id}#section#{section_idx}"
    
    def normalize_doc_name(self, doc_name: str) -> str:
        """标准化文档名为doc_id"""
        return doc_name.replace(' ', '_').replace('（', '(').replace('）', ')')
    
    def bulk_index_chunks(self, doc_name: str, chunks: List[Dict[str, Any]]) -> Dict[str, int]:
        """批量索引chunks数据"""
        success_count = 0
        error_count = 0
        
        doc_id = self.normalize_doc_name(doc_name)
        actions = []
        
        for chunk in chunks:
            chunk_data = chunk.copy()
            chunk_data["doc_name"] = doc_name
            chunk_data["doc_id"] = doc_id
            chunk_data["chunk_id"] = self.generate_chunk_id(doc_id, chunk["id"])
            
            # 提取页码范围（用于检索时的来源信息）
            if "source_pages" in chunk and chunk["source_pages"]:
                chunk_data["page_range"] = {
                    "first": min(chunk["source_pages"]),
                    "last": max(chunk["source_pages"])
                }
            
            chunk_data["created_at"] = datetime.utcnow().isoformat()
            
            action = {
                "_index": self.chunks_index,
                "_id": chunk_data["chunk_id"],
                "_source": chunk_data
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
                print(f"批量索引chunks出错: {e}")
                error_count += len(batch)
        
        return {"success": success_count, "error": error_count}
    
    def bulk_index_sections(self, doc_name: str, sections: List[Dict[str, Any]]) -> Dict[str, int]:
        """批量索引sections数据"""
        success_count = 0
        error_count = 0
        
        doc_id = self.normalize_doc_name(doc_name)
        actions = []
        
        for idx, section in enumerate(sections):
            section_data = section.copy()
            section_data["doc_name"] = doc_name
            section_data["doc_id"] = doc_id
            section_data["section_id"] = self.generate_section_id(doc_id, idx)
            section_data["created_at"] = datetime.utcnow().isoformat()
            
            action = {
                "_index": self.sections_index,
                "_id": section_data["section_id"],
                "_source": section_data
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
                print(f"批量索引sections出错: {e}")
                error_count += len(batch)
        
        return {"success": success_count, "error": error_count}
    
    def search_chunks(self, text: str, size: int = 10, doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """搜索chunks"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "match": {
                                "content": {
                                    "query": text,
                                    "analyzer": "ik_smart"
                                }
                            }
                        }
                    ]
                }
            },
            "size": size,
            "highlight": {
                "fields": {
                    "content": {}
                }
            }
        }
        
        if doc_id:
            query["query"]["bool"]["filter"] = [{"term": {"doc_id": doc_id}}]
        
        result = self.client.search(
            index=self.chunks_index,
            query=query["query"],
            size=query["size"],
            highlight=query["highlight"]
        )
        hits = []
        for hit in result["hits"]["hits"]:
            hit_data = hit["_source"]
            hit_data["score"] = hit["_score"]
            if "highlight" in hit:
                hit_data["highlight"] = hit["highlight"]
            hits.append(hit_data)
        return hits
    
    def search_sections(self, text: str, size: int = 10, doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """搜索sections（标题+内容）"""
        query = {
            "query": {
                "bool": {
                    "should": [
                        {
                            "match": {
                                "heading": {
                                    "query": text,
                                    "analyzer": "ik_smart",
                                    "boost": 2.0  # 标题权重更高
                                }
                            }
                        },
                        {
                            "match": {
                                "content": {
                                    "query": text,
                                    "analyzer": "ik_smart"
                                }
                            }
                        }
                    ],
                    "minimum_should_match": 1
                }
            },
            "size": size,
            "highlight": {
                "fields": {
                    "heading": {},
                    "content": {"fragment_size": 150, "number_of_fragments": 3}
                }
            }
        }
        
        if doc_id:
            query["query"]["bool"]["filter"] = [{"term": {"doc_id": doc_id}}]
        
        result = self.client.search(
            index=self.sections_index,
            query=query["query"],
            size=query["size"],
            highlight=query["highlight"]
        )
        hits = []
        for hit in result["hits"]["hits"]:
            hit_data = hit["_source"]
            hit_data["score"] = hit["_score"]
            if "highlight" in hit:
                hit_data["highlight"] = hit["highlight"]
            hits.append(hit_data)
        return hits
    
    def get_chunk_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """根据chunk_id获取chunk"""
        try:
            result = self.client.get(index=self.chunks_index, id=chunk_id)
            return result["_source"]
        except:
            return None
    
    def get_section_by_id(self, section_id: str) -> Optional[Dict[str, Any]]:
        """根据section_id获取section"""
        try:
            result = self.client.get(index=self.sections_index, id=section_id)
            return result["_source"]
        except:
            return None
