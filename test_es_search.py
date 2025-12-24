"""测试新的ES搜索功能"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.es_client import ESClient


def test_search():
    """测试搜索功能"""
    print("=" * 60)
    print("测试 Elasticsearch 搜索功能")
    print("=" * 60)
    
    es_client = ESClient()
    
    # 测试查询
    test_queries = [
        "机器人",
        "比赛规则",
        "通信协议",
        "装甲板",
        "伤害机制"
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"查询: '{query}'")
        print("="*60)
        
        # 搜索 chunks
        print("\n【Chunks 搜索结果】")
        try:
            chunks_results = es_client.search_chunks(query, size=5)
            print(f"找到 {len(chunks_results)} 个结果")
            
            for i, result in enumerate(chunks_results, 1):
                print(f"\n{i}. 文档: {result.get('doc_name', 'N/A')}")
                
                # 页码信息
                pages = result.get('source_pages', [])
                if pages:
                    page_range = result.get('page_range', {})
                    if page_range:
                        print(f"   页码: {page_range.get('first', '?')} - {page_range.get('last', '?')}")
                    else:
                        print(f"   页码: {pages}")
                
                # 内容
                content = result.get('content', '')
                content_preview = content[:100].replace('\n', ' ')
                print(f"   内容: {content_preview}...")
                
                # 评分
                score = result.get('score', 0)
                print(f"   评分: {score:.4f}")
                
                # 高亮
                if 'highlight' in result:
                    highlights = result['highlight'].get('content', [])
                    if highlights:
                        print(f"   高亮: {highlights[0][:80]}...")
                
                # 元数据
                chunk_type = result.get('type', 'N/A')
                confidence = result.get('confidence_avg', 0)
                print(f"   类型: {chunk_type}, 置信度: {confidence:.3f}")
        
        except Exception as e:
            print(f"Chunks 搜索失败: {e}")
        
        # 搜索 sections
        print("\n【Sections 搜索结果】")
        try:
            sections_results = es_client.search_sections(query, size=3)
            print(f"找到 {len(sections_results)} 个结果")
            
            for i, result in enumerate(sections_results, 1):
                print(f"\n{i}. 文档: {result.get('doc_name', 'N/A')}")
                
                # 页码范围
                page_range = result.get('page_range', {})
                if page_range:
                    print(f"   页码范围: {page_range.get('first', '?')} - {page_range.get('last', '?')}")
                
                # 标题
                heading = result.get('heading', '无标题')
                print(f"   标题: {heading[:80]}")
                
                # 内容预览
                content = result.get('content', '')
                content_preview = content[:150].replace('\n', ' ')
                print(f"   内容: {content_preview}...")
                
                # 评分
                score = result.get('score', 0)
                print(f"   评分: {score:.4f}")
                
                # 高亮
                if 'highlight' in result:
                    heading_highlights = result['highlight'].get('heading', [])
                    content_highlights = result['highlight'].get('content', [])
                    
                    if heading_highlights:
                        print(f"   标题高亮: {heading_highlights[0][:80]}")
                    if content_highlights:
                        print(f"   内容高亮: {content_highlights[0][:80]}...")
                
                # 统计
                chunk_count = result.get('chunk_count', 0)
                chunk_types = result.get('chunk_types', {})
                print(f"   包含 {chunk_count} 个chunks: {chunk_types}")
        
        except Exception as e:
            print(f"Sections 搜索失败: {e}")


def test_get_by_id():
    """测试按ID获取文档"""
    print("\n" + "="*60)
    print("测试按ID获取文档")
    print("="*60)
    
    es_client = ESClient()
    
    # 测试获取chunk
    test_chunk_id = "RoboMaster_2026_机甲大师超级对抗赛比赛规则手册V1.0.0（20251021）#chunk#1"
    print(f"\n获取 Chunk ID: {test_chunk_id}")
    chunk = es_client.get_chunk_by_id(test_chunk_id)
    if chunk:
        print(f"✓ 找到 chunk:")
        print(f"  内容: {chunk.get('content', '')[:100]}...")
        print(f"  页码: {chunk.get('source_pages', [])}")
    else:
        print("✗ 未找到该 chunk")
    
    # 测试获取section
    test_section_id = "RoboMaster_2026_机甲大师超级对抗赛比赛规则手册V1.0.0（20251021）#section#0"
    print(f"\n获取 Section ID: {test_section_id}")
    section = es_client.get_section_by_id(test_section_id)
    if section:
        print(f"✓ 找到 section:")
        print(f"  标题: {section.get('heading', '')[:100]}")
        print(f"  页码范围: {section.get('page_range', {})}")
        print(f"  包含chunks: {section.get('chunk_count', 0)}")
    else:
        print("✗ 未找到该 section")


if __name__ == "__main__":
    test_search()
    test_get_by_id()
    
    print("\n" + "="*60)
    print("测试完成!")
    print("="*60)
