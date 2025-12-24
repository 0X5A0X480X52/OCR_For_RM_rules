"""PDF 解析模块"""
import fitz  # PyMuPDF
import pdfplumber
from pathlib import Path
from typing import List, Dict, Any, Tuple
from PIL import Image
import io


class PDFParser:
    """PDF 解析器，提取文本、布局和图片"""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        self.doc = fitz.open(str(self.pdf_path))
        self.pdfplumber_pdf = pdfplumber.open(str(self.pdf_path))
        
    def __del__(self):
        """清理资源"""
        if hasattr(self, 'doc'):
            self.doc.close()
        if hasattr(self, 'pdfplumber_pdf'):
            self.pdfplumber_pdf.close()
    
    def get_page_count(self) -> int:
        """获取总页数"""
        return len(self.doc)
    
    def extract_page_text(self, page_num: int) -> Tuple[str, List[Dict[str, Any]]]:
        """提取页面文本和布局信息
        
        Returns:
            (text, blocks): 文本内容和文本块列表
            blocks 格式: [{
                'text': str,
                'bbox': (x0, y0, x1, y1),
                'font_size': float,
                'font_name': str
            }]
        """
        page = self.doc[page_num]
        
        # 提取文本块及其格式信息
        blocks = []
        text_dict = page.get_text("dict")
        
        full_text = ""
        for block in text_dict.get("blocks", []):
            if block.get("type") == 0:  # 文本块
                block_text = ""
                block_bbox = block.get("bbox", (0, 0, 0, 0))
                
                for line in block.get("lines", []):
                    line_text = ""
                    font_sizes = []
                    font_names = []
                    
                    for span in line.get("spans", []):
                        span_text = span.get("text", "")
                        line_text += span_text
                        font_sizes.append(span.get("size", 0))
                        font_names.append(span.get("font", ""))
                    
                    block_text += line_text
                
                if block_text.strip():
                    blocks.append({
                        "text": block_text,
                        "bbox": block_bbox,
                        "font_size": max(font_sizes) if font_sizes else 0,
                        "font_name": font_names[0] if font_names else ""
                    })
                    full_text += block_text + "\n"
        
        return full_text.strip(), blocks
    
    def is_page_need_ocr(self, page_num: int) -> bool:
        """判断页面是否需要 OCR（文本内容少于 50 字符）"""
        text, _ = self.extract_page_text(page_num)
        return len(text.strip()) < 50
    
    def extract_page_images(self, page_num: int) -> List[Dict[str, Any]]:
        """提取页面中的图片
        
        Returns:
            List[{
                'image': PIL.Image,
                'bbox': (x0, y0, x1, y1),
                'image_index': int
            }]
        """
        page = self.doc[page_num]
        images = []
        
        image_list = page.get_images()
        for img_index, img_info in enumerate(image_list):
            xref = img_info[0]
            
            try:
                base_image = self.doc.extract_image(xref)
                image_bytes = base_image["image"]
                image = Image.open(io.BytesIO(image_bytes))
                
                # 获取图片在页面上的位置
                img_rects = page.get_image_rects(xref)
                if img_rects:
                    bbox = img_rects[0]  # 取第一个位置
                    images.append({
                        "image": image,
                        "bbox": tuple(bbox),
                        "image_index": img_index
                    })
            except Exception as e:
                print(f"提取图片失败 (页{page_num}, 图{img_index}): {e}")
        
        return images
    
    def render_page_as_image(self, page_num: int, dpi: int = 300) -> Image.Image:
        """将页面渲染为图片（用于整页 OCR）"""
        page = self.doc[page_num]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return img
    
    def extract_tables(self, page_num: int) -> List[Dict[str, Any]]:
        """提取页面中的表格
        
        Returns:
            List[{
                'data': List[List[str]],  # 表格数据
                'bbox': (x0, y0, x1, y1),
                'table_index': int
            }]
        """
        page = self.pdfplumber_pdf.pages[page_num]
        tables = []
        
        try:
            extracted_tables = page.extract_tables()
            for idx, table_data in enumerate(extracted_tables):
                if table_data:
                    # 尝试获取表格边界
                    table_obj = page.find_tables()[idx] if page.find_tables() else None
                    bbox = table_obj.bbox if table_obj else (0, 0, page.width, page.height)
                    
                    tables.append({
                        "data": table_data,
                        "bbox": bbox,
                        "table_index": idx
                    })
        except Exception as e:
            print(f"提取表格失败 (页{page_num}): {e}")
        
        return tables
    
    def get_page_dimensions(self, page_num: int) -> Tuple[float, float]:
        """获取页面尺寸 (width, height)"""
        page = self.doc[page_num]
        rect = page.rect
        return rect.width, rect.height
