"""分段器模块 - 句子级语义分段"""
import re
import jieba
from typing import List, Dict, Any, Tuple


class Segmenter:
    """文本分段器，基于句子边界进行分段"""
    
    def __init__(self, min_length: int = 15, max_length: int = 500):
        self.min_length = min_length
        self.max_length = max_length
        
        # 中文句子终止符
        self.sentence_delimiters = r'[。！？；…\n]+'
        
        # 初始化 jieba（首次加载）
        jieba.initialize()
    
    def split_into_sentences(self, text: str) -> List[str]:
        """将文本分割为句子"""
        if not text:
            return []
        
        # 使用正则分割，保留分隔符
        sentences = re.split(f'({self.sentence_delimiters})', text)
        
        # 合并句子和分隔符
        result = []
        i = 0
        while i < len(sentences):
            if sentences[i].strip():
                sentence = sentences[i]
                # 添加后续的标点符号
                if i + 1 < len(sentences) and re.match(self.sentence_delimiters, sentences[i + 1]):
                    sentence += sentences[i + 1]
                    i += 2
                else:
                    i += 1
                result.append(sentence.strip())
            else:
                i += 1
        
        return result
    
    def merge_short_sentences(self, sentences: List[str]) -> List[str]:
        """合并过短的句子"""
        if not sentences:
            return []
        
        merged = []
        current = ""
        
        for sentence in sentences:
            if not sentence.strip():
                continue
            
            if not current:
                current = sentence
            elif len(current) < self.min_length:
                # 当前句子太短，合并
                current += sentence
            else:
                # 当前句子足够长，保存并开始新句
                merged.append(current)
                current = sentence
        
        if current:
            merged.append(current)
        
        return merged
    
    def split_long_segment(self, text: str) -> List[str]:
        """拆分过长的段落"""
        if len(text) <= self.max_length:
            return [text]
        
        # 先按句子分割
        sentences = self.split_into_sentences(text)
        
        # 重新组合，确保每段不超过最大长度
        segments = []
        current_segment = ""
        
        for sentence in sentences:
            if len(current_segment) + len(sentence) <= self.max_length:
                current_segment += sentence
            else:
                if current_segment:
                    segments.append(current_segment)
                
                # 如果单个句子太长，强制在标点处分割
                if len(sentence) > self.max_length:
                    parts = self._force_split_at_punctuation(sentence, self.max_length)
                    segments.extend(parts[:-1])
                    current_segment = parts[-1] if parts else ""
                else:
                    current_segment = sentence
        
        if current_segment:
            segments.append(current_segment)
        
        return segments
    
    def _force_split_at_punctuation(self, text: str, max_len: int) -> List[str]:
        """在标点处强制拆分长文本"""
        punctuations = '，,、；;：:'
        parts = []
        current = ""
        
        for char in text:
            current += char
            if len(current) >= max_len and char in punctuations:
                parts.append(current)
                current = ""
        
        if current:
            parts.append(current)
        
        return parts if parts else [text]
    
    def segment_text(self, text: str) -> List[str]:
        """完整的文本分段流程"""
        if not text or not text.strip():
            return []
        
        # 1. 分割为句子
        sentences = self.split_into_sentences(text)
        
        # 2. 合并短句
        sentences = self.merge_short_sentences(sentences)
        
        # 3. 拆分长段
        segments = []
        for sentence in sentences:
            if len(sentence) > self.max_length:
                segments.extend(self.split_long_segment(sentence))
            else:
                segments.append(sentence)
        
        return [s.strip() for s in segments if s.strip()]
    
    def compute_union_bbox(self, bboxes: List[List[float]]) -> List[float]:
        """计算多个 bbox 的并集
        
        Args:
            bboxes: List of [x0, y0, x1, y1]
        
        Returns:
            [x0, y0, x1, y1]
        """
        if not bboxes:
            return [0, 0, 0, 0]
        
        x0 = min(bbox[0] for bbox in bboxes)
        y0 = min(bbox[1] for bbox in bboxes)
        x1 = max(bbox[2] for bbox in bboxes)
        y1 = max(bbox[3] for bbox in bboxes)
        
        return [x0, y0, x1, y1]
    
    def is_heading(self, text: str, font_size: float = 0, 
                   avg_font_size: float = 12.0) -> bool:
        """判断是否为标题"""
        text = text.strip()
        
        # 短文本 + 有编号模式
        if len(text) < 80:
            heading_patterns = [
                r'^\d+(?:\.\d+)*[\.、\s]+',  # 数字编号
                r'^第[一二三四五六七八九十百\d]+(章|节|条|款|项)',  # 中文章节
                r'^[（\(]?[一二三四五六七八九十]\w{0,2}[）\)]',  # 中文序号
                r'^[（\(]?[a-zA-Z][）\)]',  # 字母序号
                r'^(附录|表|图|Table|Fig)',  # 附录/表图
            ]
            
            for pattern in heading_patterns:
                if re.match(pattern, text, re.IGNORECASE):
                    return True
            
            # 字体明显更大
            if font_size > avg_font_size * 1.2:
                return True
        
        return False
    
    def process_blocks_to_segments(self, blocks: List[Dict[str, Any]], 
                                    avg_font_size: float = 12.0) -> List[Dict[str, Any]]:
        """将文本块处理为分段，识别标题和正文
        
        Args:
            blocks: 文本块列表 [{
                'text': str,
                'bbox': [x0, y0, x1, y1],
                'font_size': float,
                'confidence': float (optional)
            }]
        
        Returns:
            List[{
                'text': str,
                'segments': List[str],
                'content_type': 'heading' | 'paragraph',
                'bbox': [x0, y0, x1, y1],
                'confidence': float
            }]
        """
        processed = []
        
        for block in blocks:
            text = block.get("text", "").strip()
            if not text:
                continue
            
            bbox = block.get("bbox", [0, 0, 0, 0])
            font_size = block.get("font_size", 0)
            confidence = block.get("confidence", 1.0)
            
            # 判断是否为标题
            is_heading = self.is_heading(text, font_size, avg_font_size)
            
            if is_heading:
                # 标题不分段
                processed.append({
                    "text": text,
                    "segments": [text],
                    "content_type": "heading",
                    "bbox": bbox,
                    "confidence": confidence
                })
            else:
                # 正文分段
                segments = self.segment_text(text)
                if segments:
                    processed.append({
                        "text": text,
                        "segments": segments,
                        "content_type": "paragraph",
                        "bbox": bbox,
                        "confidence": confidence
                    })
        
        return processed
