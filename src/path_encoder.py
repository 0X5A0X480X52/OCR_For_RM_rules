"""路径编码器模块 - 构建文档结构树并生成层级路径"""
import re
from typing import List, Dict, Any, Optional, Tuple
from config import NUMBERING_MAPPING


class PathEncoder:
    """路径编码器，基于文档结构生成层级编码"""
    
    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.node_count = 0
        self.block_counter = 0  # 自动块计数器
        self.current_path_stack = []  # 路径栈，用于维护当前层级
        
    def detect_heading_level(self, text: str, font_size: float = 0, 
                            avg_font_size: float = 12.0) -> Tuple[Optional[str], Optional[int]]:
        """检测标题及其层级
        
        Returns:
            (numbering, level): 编号字符串和层级（None 表示非标题）
        """
        text = text.strip()
        
        if not text or len(text) > 200:
            return None, None
        
        # 模式1: 数字编号 "1.2.3"
        pattern1 = r'^(\d+(?:\.\d+)*)[\.、\s]+'
        match1 = re.match(pattern1, text)
        if match1:
            numbering = match1.group(1)
            level = numbering.count('.') + 1
            return numbering, level
        
        # 模式2: 中文章节 "第X章", "第X节"
        pattern2 = r'^第([一二三四五六七八九十百\d]+)(章|节|条|款|项)'
        match2 = re.match(pattern2, text)
        if match2:
            num_text = match2.group(1)
            section_type = match2.group(2)
            
            # 转换中文数字为阿拉伯数字
            num = self._chinese_to_arabic(num_text)
            
            # 根据类型确定层级
            level_map = {"章": 1, "节": 2, "条": 3, "款": 4, "项": 5}
            level = level_map.get(section_type, 1)
            
            return str(num), level
        
        # 模式3: 附录、表、图等
        pattern3 = r'^(附录|表|图|Table|Fig)[^\d]*(\d+(?:\.\d+)*|\w+)'
        match3 = re.match(pattern3, text, re.IGNORECASE)
        if match3:
            prefix = match3.group(1)
            suffix = match3.group(2)
            
            # 使用映射表
            prefix_lower = prefix.lower()
            for key, value in NUMBERING_MAPPING.items():
                if key.lower() in prefix_lower:
                    if isinstance(value, int):
                        # 附录类：900+编号
                        try:
                            appendix_num = int(suffix) if suffix.isdigit() else ord(suffix.upper()) - ord('A') + 1
                            numbering = str(value + appendix_num)
                            return numbering, 1
                        except:
                            pass
                    else:
                        # 表格/图片类：标记类型
                        return f"{value}.{suffix}", 2
        
        # 模式4: 字母编号 "(a)", "A."
        pattern4 = r'^[（\(]?([a-zA-Z])[）\)]\.?\s+'
        match4 = re.match(pattern4, text)
        if match4:
            letter = match4.group(1).upper()
            num = ord(letter) - ord('A') + 1
            return str(num), 3  # 字母编号通常是第3层
        
        # 模式5: 短文本 + 大字体 = 可能是标题
        if len(text) < 80 and font_size > avg_font_size * 1.2:
            # 无明确编号的标题，返回特殊标记
            return "heading", None
        
        return None, None
    
    def _chinese_to_arabic(self, chinese_num: str) -> int:
        """将中文数字转换为阿拉伯数字"""
        if chinese_num.isdigit():
            return int(chinese_num)
        
        chinese_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
            '百': 100, '千': 1000
        }
        
        result = 0
        temp = 0
        
        for char in chinese_num:
            if char in chinese_map:
                val = chinese_map[char]
                if val >= 10:
                    temp = temp * val if temp else val
                    result += temp
                    temp = 0
                else:
                    temp = val
        
        result += temp
        return result if result else 1
    
    def build_path(self, numbering: str, level: Optional[int]) -> str:
        """根据编号和层级构建路径
        
        Args:
            numbering: 编号字符串（如 "1.2", "3", "heading"）
            level: 层级（1=章, 2=节, 3=条...）
        
        Returns:
            路径字符串（如 "001.002.003"）
        """
        if numbering == "heading" or level is None:
            # 无编号标题，使用自动编号
            return self._build_auto_path()
        
        # 解析编号为数字列表
        if '.' in numbering:
            parts = numbering.split('.')
        else:
            parts = [numbering]
        
        # 转换为3位数字格式
        path_parts = []
        for part in parts:
            try:
                num = int(part) if part.isdigit() else 1
                path_parts.append(f"{num:03d}")
            except:
                path_parts.append(part)
        
        # 更新路径栈
        if level:
            # 调整栈深度到当前层级
            self.current_path_stack = path_parts[:level]
        
        return ".".join(path_parts)
    
    def _build_auto_path(self) -> str:
        """为无编号内容生成自动路径（.blk.NNN）"""
        self.block_counter += 1
        
        # 如果有父路径，在父路径后添加 .blk.NNN
        if self.current_path_stack:
            parent_path = ".".join(self.current_path_stack)
            return f"{parent_path}.blk.{self.block_counter:03d}"
        else:
            # 顶层自动块
            return f"blk.{self.block_counter:03d}"
    
    def add_block_path(self) -> str:
        """为普通文本块添加路径（在当前路径下添加 .blk.NNN）"""
        return self._build_auto_path()
    
    def get_parent_path(self, path: str) -> Optional[str]:
        """计算父路径"""
        if not path:
            return None
        
        # 移除 .blk.NNN 后缀
        if ".blk." in path:
            path = path.rsplit(".blk.", 1)[0]
        
        # 获取父路径
        parts = path.split('.')
        if len(parts) <= 1:
            return None
        
        return ".".join(parts[:-1])
    
    def increment_node_count(self):
        """增加节点计数"""
        self.node_count += 1
    
    def get_node_count(self) -> int:
        """获取当前文档的节点总数"""
        return self.node_count
    
    def reset_for_new_section(self, level: int):
        """重置块计数器（进入新章节时）"""
        # 保留到指定层级的路径
        if level <= len(self.current_path_stack):
            self.current_path_stack = self.current_path_stack[:level]
        self.block_counter = 0
