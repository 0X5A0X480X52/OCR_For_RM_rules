"""
文本清洗与聚合模块
基于原始 pages/*.json 输出，进行二次加工：
- 按页读取 nodes，按 bbox.top 排序构造阅读顺序
- 增量式合并：标题/列表/强标点等强信号切断
- 标题识别：关键词+短行+字号突变(bbox_height)+编号样式
- 列表聚合：前缀符号+缩进+行距
- 过滤低置信度 image_ocr (0.0)
- 输出 cleaned_chunks.json + cleaner.log
"""
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


class TextCleaner:
    """文本清洗与聚合器"""
    
    # 标题关键词模式
    HEADING_KEYWORDS = [
        '附录', '章', '节', '说明', '流程', '规则', '处罚', '定义',
        '简介', '概述', '总则', '细则', '要求', '标准', '检录',
        '赛前', '赛中', '赛后', '机器人', '场地', '裁判'
    ]
    
    # 编号样式正则
    NUMBERING_PATTERNS = [
        r'^第[一二三四五六七八九十\d]+章',  # 第X章
        r'^第[一二三四五六七八九十\d]+节',  # 第X节
        r'^\d+\.\d+',  # X.Y
        r'^\d+\.\d+\.\d+',  # X.Y.Z
        r'^[（\(][一二三四五六七八九十\d]+[）\)]',  # (一)
        r'^[①②③④⑤⑥⑦⑧⑨⑩]',  # 圆圈数字
    ]
    
    # 列表前缀模式
    LIST_PREFIXES = [
        r'^[•\-·]',  # 圆点、横线
        r'^\d+[.、)]',  # 1. 1、 1)
        r'^[a-zA-Z][.、)]',  # a. A、
        r'^[（\(][a-zA-Z\d]+[）\)]',  # (a) (1)
    ]
    
    # 强句末标点
    SENTENCE_END_MARKS = {'。', '!', '?', ':', ':', ';', ';'}
    
    # 页脚/页眉噪声模式 (版权信息、页码等)
    FOOTER_PATTERNS = [
        r'^\d+\s*©\s*\d{4}.*版权所有',  # "2 © 2025 大疆 版权所有"
        r'^©\s*\d{4}.*版权所有\s*\d+',  # "© 2025 大疆 版权所有 3"
        r'^\d+\s*①?\s*\d{4}.*版权所有',  # "46 2025大疆版权所有" 或 "56 ①2025大疆版权所有"
        r'^\d+\s*$',  # 纯数字页码
        r'^[-=_]{3,}$',  # 分隔线
    ]
    
    def __init__(
        self,
        confidence_threshold: float = 0.1,
        short_line_threshold: int = 20,
        height_ratio_threshold: float = 1.3,
        min_gap_threshold: float = 15.0,
        log_file: Optional[Path] = None
    ):
        """
        Args:
            confidence_threshold: OCR置信度阈值,低于此值的node直接丢弃
            short_line_threshold: 短行字符数阈值,用于标题判断
            height_ratio_threshold: 字号突变倍数阈值
            min_gap_threshold: 段间距阈值(像素),用于强断开
            log_file: 审计日志文件路径
        """
        self.confidence_threshold = confidence_threshold
        self.short_line_threshold = short_line_threshold
        self.height_ratio_threshold = height_ratio_threshold
        self.min_gap_threshold = min_gap_threshold
        self.log_file = log_file
        self.log_lines = []
        
    def _log(self, message: str):
        """记录日志"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] {message}"
        self.log_lines.append(log_line)
        # 安全打印，避免 GBK 编码错误
        try:
            print(log_line)
        except UnicodeEncodeError:
            print(log_line.encode('utf-8', errors='replace').decode('utf-8', errors='replace'))
    
    def _write_log(self):
        """写入日志文件"""
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(self.log_lines))
            self._log(f"日志已写入: {self.log_file}")
    
    def _load_page_nodes(self, page_json: Path) -> List[Dict[str, Any]]:
        """加载单页节点并预处理"""
        with open(page_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        nodes = data.get('nodes', [])
        page_num = data.get('page', 0)
        
        # 过滤与预处理
        valid_nodes = []
        for node in nodes:
            # 跳过 page_raw_text (通常是整页拼接,易重复)
            if node.get('content_type') == 'page_raw_text':
                continue
            
            # 过滤低置信度 image_ocr
            conf = node.get('ocr_confidence', 1.0)
            if conf < self.confidence_threshold:
                self._log(f"  丢弃低置信度节点: page={page_num}, conf={conf:.3f}, content_preview={node.get('content', '')[:30]}")
                continue
            
            # 过滤页脚/页眉噪声
            content = node.get('content', '').strip()
            is_footer = False
            for pattern in self.FOOTER_PATTERNS:
                if re.match(pattern, content):
                    self._log(f"  丢弃页脚/页眉: page={page_num}, content={content[:50]}")
                    is_footer = True
                    break
            if is_footer:
                continue
            
            # 提取bbox信息
            bbox = node.get('bbox', {})
            if isinstance(bbox, dict):
                node['_bbox_top'] = bbox.get('top', 0)
                node['_bbox_left'] = bbox.get('left', 0)
                node['_bbox_height'] = bbox.get('bottom', 0) - bbox.get('top', 0)
            else:
                node['_bbox_top'] = 0
                node['_bbox_left'] = 0
                node['_bbox_height'] = 10
            
            valid_nodes.append(node)
        
        # 页内排序: 先按top,再按left
        valid_nodes.sort(key=lambda n: (n['_bbox_top'], n['_bbox_left']))
        
        return valid_nodes
    
    def _is_heading(self, node: Dict[str, Any], avg_height: float) -> tuple[bool, str]:
        """
        判断是否为标题
        Returns: (is_heading, reason)
        """
        content = node.get('content', '').strip()
        if not content:
            return False, ""
        
        content_type = node.get('content_type', '')
        if content_type == 'heading':
            return True, "content_type=heading"
        
        # 1. 关键词命中
        for keyword in self.HEADING_KEYWORDS:
            if keyword in content:
                return True, f"keyword={keyword}"
        
        # 2. 编号样式匹配
        for pattern in self.NUMBERING_PATTERNS:
            if re.match(pattern, content):
                return True, f"numbering={pattern}"
        
        # 3. 短行判断
        if len(content) <= self.short_line_threshold:
            # 不以句末标点结尾
            if not any(content.endswith(mark) for mark in self.SENTENCE_END_MARKS):
                return True, f"short_line(len={len(content)})"
        
        # 4. 字号突变(bbox_height)
        height = node.get('_bbox_height', 10)
        if avg_height > 0 and height / avg_height >= self.height_ratio_threshold:
            return True, f"height_突变({height:.1f} vs avg={avg_height:.1f})"
        
        return False, ""
    
    def _is_list_item(self, node: Dict[str, Any]) -> tuple[bool, str]:
        """
        判断是否为列表项
        Returns: (is_list, prefix)
        """
        content = node.get('content', '').strip()
        if not content:
            return False, ""
        
        for pattern in self.LIST_PREFIXES:
            match = re.match(pattern, content)
            if match:
                return True, match.group()
        
        return False, ""
    
    def _should_break(
        self,
        current_chunk: Dict[str, Any],
        node: Dict[str, Any],
        avg_height: float
    ) -> tuple[bool, str]:
        """
        判断是否应该切断当前chunk,开始新chunk
        Returns: (should_break, reason)
        """
        if not current_chunk:
            return False, ""
        
        # 1. 标题是强边界
        is_heading, heading_reason = self._is_heading(node, avg_height)
        if is_heading:
            return True, f"heading({heading_reason})"
        
        # 2. 列表起始(缩进变化)
        is_list, list_prefix = self._is_list_item(node)
        if is_list:
            # 如果当前chunk不是列表,则断开
            if current_chunk.get('type') != 'list':
                return True, f"list_start({list_prefix})"
        
        # 3. 段间距突变
        last_node = current_chunk.get('_last_node')
        if last_node:
            gap = node['_bbox_top'] - (last_node['_bbox_top'] + last_node['_bbox_height'])
            if gap >= self.min_gap_threshold:
                return True, f"large_gap({gap:.1f}px)"
        
        # 4. 上一节点以强句末标点结尾
        if last_node:
            last_content = last_node.get('content', '').strip()
            if last_content and any(last_content.endswith(mark) for mark in self.SENTENCE_END_MARKS):
                # 且当前节点不是明显续接(如"但"、"若"、"且"等)
                curr_content = node.get('content', '').strip()
                if not curr_content.startswith(('但', '若', '如果', '且', '并', '同时')):
                    return True, "sentence_end"
        
        return False, ""
    
    def _merge_chunk(self, nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """将一组节点合并为一个chunk"""
        if not nodes:
            return {}
        
        # 合并文本
        content_parts = []
        for node in nodes:
            text = node.get('content', '').strip()
            if text:
                # 去除单行内的多余空格与换行
                text = re.sub(r'\s+', ' ', text)
                content_parts.append(text)
        
        content = ' '.join(content_parts)
        
        # 收集页码范围
        pages = sorted(set(node.get('source_page', 0) for node in nodes))
        
        # 计算bbox范围
        bboxes = [node.get('bbox', {}) for node in nodes if node.get('bbox')]
        if bboxes and isinstance(bboxes[0], dict):
            bbox_range = {
                'left': min(b.get('left', 0) for b in bboxes),
                'top': min(b.get('top', 0) for b in bboxes),
                'right': max(b.get('right', 0) for b in bboxes),
                'bottom': max(b.get('bottom', 0) for b in bboxes),
            }
        else:
            bbox_range = {}
        
        # 平均置信度
        confidences = [node.get('ocr_confidence', 1.0) for node in nodes]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 1.0
        
        # 判断类型
        chunk_type = 'paragraph'
        first_node = nodes[0]
        if first_node.get('content_type') == 'heading':
            chunk_type = 'heading'
        elif self._is_list_item(first_node)[0]:
            chunk_type = 'list_item'
        
        return {
            'content': content,
            'type': chunk_type,
            'source_pages': pages,
            'bbox_range': bbox_range,
            'confidence_avg': round(avg_confidence, 3),
            'node_count': len(nodes),
            'meta': {
                'first_page': pages[0] if pages else 0,
                'last_page': pages[-1] if pages else 0,
                'indent_x': first_node.get('_bbox_left', 0),
                'height_avg': sum(n.get('_bbox_height', 10) for n in nodes) / len(nodes)
            }
        }
    
    def clean_document(self, doc_dir: Path, output_file: Path) -> Dict[str, Any]:
        """
        清洗整个文档
        Args:
            doc_dir: 文档目录 (包含 pages/ 子目录)
            output_file: 输出文件路径 (cleaned_chunks.json)
        Returns:
            统计信息
        """
        self._log(f"开始清洗文档: {doc_dir.name}")
        
        pages_dir = doc_dir / 'pages'
        if not pages_dir.exists():
            self._log(f"错误: pages目录不存在: {pages_dir}")
            return {}
        
        # 收集所有page json文件
        page_files = sorted(pages_dir.glob('page_*.json'), key=lambda p: int(p.stem.split('_')[1]))
        self._log(f"找到 {len(page_files)} 个页面文件")
        
        # 全局变量
        all_nodes = []
        total_dropped = 0
        
        # 逐页加载
        for page_file in page_files:
            page_num = int(page_file.stem.split('_')[1])
            nodes = self._load_page_nodes(page_file)
            
            before_count = len(nodes)
            # 统计被过滤的节点数
            with open(page_file, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
                raw_count = len([n for n in raw_data.get('nodes', []) if n.get('content_type') != 'page_raw_text'])
            dropped = raw_count - before_count
            total_dropped += dropped
            
            all_nodes.extend(nodes)
            self._log(f"  页 {page_num}: 加载 {before_count} 节点 (丢弃 {dropped})")
        
        self._log(f"总计加载 {len(all_nodes)} 节点 (丢弃 {total_dropped})")
        
        # 计算平均高度(用于标题检测)
        heights = [n.get('_bbox_height', 10) for n in all_nodes]
        avg_height = sum(heights) / len(heights) if heights else 10.0
        self._log(f"平均bbox高度: {avg_height:.2f}")
        
        # 增量式合并
        chunks = []
        current_chunk = None
        current_nodes = []
        
        for idx, node in enumerate(all_nodes):
            # 判断是否应该切断
            should_break, reason = self._should_break(current_chunk, node, avg_height)
            
            if should_break:
                # flush当前chunk
                if current_nodes:
                    chunk = self._merge_chunk(current_nodes)
                    chunks.append(chunk)
                    self._log(f"  创建chunk #{len(chunks)}: type={chunk['type']}, pages={chunk['source_pages']}, len={len(chunk['content'])}, reason={reason}")
                
                # 开始新chunk
                current_nodes = [node]
                current_chunk = {
                    'type': 'unknown',
                    '_last_node': node
                }
            else:
                # 追加到当前chunk
                current_nodes.append(node)
                if current_chunk:
                    current_chunk['_last_node'] = node
                else:
                    current_chunk = {'_last_node': node}
        
        # flush最后一个chunk
        if current_nodes:
            chunk = self._merge_chunk(current_nodes)
            chunks.append(chunk)
            self._log(f"  创建chunk #{len(chunks)}: type={chunk['type']}, pages={chunk['source_pages']}, len={len(chunk['content'])}")
        
        # 添加chunk id
        for i, chunk in enumerate(chunks, 1):
            chunk['id'] = i
        
        # 统计
        stats = {
            'total_pages': len(page_files),
            'total_nodes': len(all_nodes),
            'dropped_nodes': total_dropped,
            'total_chunks': len(chunks),
            'chunk_types': {
                'heading': len([c for c in chunks if c['type'] == 'heading']),
                'paragraph': len([c for c in chunks if c['type'] == 'paragraph']),
                'list_item': len([c for c in chunks if c['type'] == 'list_item']),
            },
            'avg_chunk_length': sum(len(c['content']) for c in chunks) / len(chunks) if chunks else 0,
        }
        
        self._log(f"清洗完成:")
        self._log(f"  总页数: {stats['total_pages']}")
        self._log(f"  总节点: {stats['total_nodes']}")
        self._log(f"  丢弃节点: {stats['dropped_nodes']}")
        self._log(f"  生成chunks: {stats['total_chunks']}")
        self._log(f"  - heading: {stats['chunk_types']['heading']}")
        self._log(f"  - paragraph: {stats['chunk_types']['paragraph']}")
        self._log(f"  - list_item: {stats['chunk_types']['list_item']}")
        self._log(f"  平均chunk长度: {stats['avg_chunk_length']:.1f} 字符")
        
        # 写入输出文件
        output_data = {
            'doc_name': doc_dir.name,
            'cleaned_at': datetime.now().isoformat(),
            'stats': stats,
            'chunks': chunks
        }
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        self._log(f"输出已写入: {output_file}")
        
        # 写入日志
        self._write_log()
        
        return stats


class SectionAggregator:
    """二级聚合器：将 heading 间的内容打包成 section"""
    
    def __init__(self, log_callback=None):
        self.log_callback = log_callback or print
    
    def _log(self, message: str):
        self.log_callback(message)
    
    def aggregate_sections(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        将 chunks 按 heading 分组为 sections
        每个 section 包含一个 heading + 后续所有非 heading chunks
        """
        sections = []
        current_section = None
        
        for chunk in chunks:
            if chunk['type'] == 'heading':
                # 保存上一个 section
                if current_section:
                    sections.append(self._finalize_section(current_section))
                
                # 开始新 section
                current_section = {
                    'heading_chunk': chunk,
                    'content_chunks': []
                }
            else:
                # 追加到当前 section
                if current_section is None:
                    # 文档开头没有 heading，创建默认 section
                    current_section = {
                        'heading_chunk': None,
                        'content_chunks': []
                    }
                current_section['content_chunks'].append(chunk)
        
        # 保存最后一个 section
        if current_section:
            sections.append(self._finalize_section(current_section))
        
        self._log(f"\n二级聚合完成: 生成 {len(sections)} 个 sections")
        return sections
    
    def _finalize_section(self, section_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成最终 section 结构"""
        heading_chunk = section_data['heading_chunk']
        content_chunks = section_data['content_chunks']
        
        # 标题信息
        if heading_chunk:
            heading_text = heading_chunk['content']
            heading_pages = heading_chunk['source_pages']
        else:
            heading_text = "(文档前言)"
            heading_pages = []
        
        # 合并内容
        all_chunks = [heading_chunk] if heading_chunk else []
        all_chunks.extend(content_chunks)
        
        # 收集页码范围
        all_pages = []
        for chunk in all_chunks:
            all_pages.extend(chunk['source_pages'])
        all_pages = sorted(set(all_pages))
        
        # 合并文本
        content_parts = []
        if heading_chunk:
            content_parts.append(f"## {heading_text}")
        
        for chunk in content_chunks:
            text = chunk['content'].strip()
            if chunk['type'] == 'list_item':
                text = f"- {text}"
            content_parts.append(text)
        
        full_content = '\n\n'.join(content_parts)
        
        # 统计
        chunk_type_counts = {}
        for chunk in content_chunks:
            ctype = chunk['type']
            chunk_type_counts[ctype] = chunk_type_counts.get(ctype, 0) + 1
        
        section = {
            'heading': heading_text,
            'content': full_content,
            'source_pages': all_pages,
            'page_range': {
                'first': all_pages[0] if all_pages else 0,
                'last': all_pages[-1] if all_pages else 0
            },
            'chunk_count': len(content_chunks),
            'chunk_types': chunk_type_counts,
            'heading_chunk_id': heading_chunk['id'] if heading_chunk else None,
            'content_chunk_ids': [c['id'] for c in content_chunks]
        }
        
        return section


def main():
    """测试入口"""
    import sys
    from pathlib import Path
    
    if len(sys.argv) < 2:
        print("用法: python text_cleaner.py <doc_dir>")
        print("示例: python text_cleaner.py output/quick_run_test/RoboMaster...")
        sys.exit(1)
    
    doc_dir = Path(sys.argv[1])
    if not doc_dir.exists():
        print(f"错误: 目录不存在: {doc_dir}")
        sys.exit(1)
    
    output_file = doc_dir / 'cleaned_chunks.json'
    log_file = doc_dir / 'cleaner.log'
    
    cleaner = TextCleaner(
        confidence_threshold=0.1,
        short_line_threshold=20,
        height_ratio_threshold=1.3,
        min_gap_threshold=15.0,
        log_file=log_file
    )
    
    stats = cleaner.clean_document(doc_dir, output_file)
    
    # 二级聚合：生成 sections
    print("\n" + "="*60)
    print("开始二级聚合 (section aggregation)...")
    print("="*60)
    
    # 读取刚生成的 chunks
    with open(output_file, 'r', encoding='utf-8') as f:
        chunks_data = json.load(f)
    
    aggregator = SectionAggregator(log_callback=print)
    sections = aggregator.aggregate_sections(chunks_data['chunks'])
    
    # 写入 sections 文件
    sections_file = doc_dir / 'cleaned_basic_part.json'
    sections_data = {
        'doc_name': doc_dir.name,
        'cleaned_at': datetime.now().isoformat(),
        'stats': {
            'total_sections': len(sections),
            'total_chunks': len(chunks_data['chunks']),
            'avg_chunks_per_section': len(chunks_data['chunks']) / len(sections) if sections else 0
        },
        'sections': sections
    }
    
    with open(sections_file, 'w', encoding='utf-8') as f:
        json.dump(sections_data, f, ensure_ascii=False, indent=2)
    
    print(f"\nSections 已写入: {sections_file}")
    
    print("\n" + "="*60)
    print("清洗完成!")
    print(f"输出文件 (chunks): {output_file}")
    print(f"输出文件 (sections): {sections_file}")
    print(f"日志文件: {log_file}")
    print("="*60)


if __name__ == '__main__':
    main()
