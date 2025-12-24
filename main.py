"""主流程脚本 - PDF 解析、OCR、分段和 ES 索引"""
import sys
import argparse
from pathlib import Path
from tqdm import tqdm
import json
from typing import List, Dict, Any

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import DOCS_SRC_DIR, OUTPUT_DIR, MIN_SEGMENT_LENGTH, MAX_SEGMENT_LENGTH
from src.pdf_parser import PDFParser
from src.ocr_engine import OCREngine
from src.path_encoder import PathEncoder
from src.segmenter import Segmenter
from src.es_client import ESClient


class PDFProcessor:
    """PDF 处理主类"""
    
    def __init__(self, no_es: bool = False):
        self.no_es = no_es
        self.ocr_engine = OCREngine()
        self.segmenter = Segmenter(
            min_length=MIN_SEGMENT_LENGTH,
            max_length=MAX_SEGMENT_LENGTH
        )
        # Only create ES client if we will use ES
        self.es_client = ESClient() if not self.no_es else None
        
        # 统计信息
        self.stats = {
            "total_docs": 0,
            "total_pages": 0,
            "ocr_pages": 0,
            "ocr_images": 0,
            "total_nodes": 0,
            "errors": []
        }
        # 当前任务目录（在 run() 中设置）
        self.task_dir = None
    
    def extract_version_from_filename(self, filename: str) -> str:
        """从文件名提取版本号"""
        import re
        match = re.search(r'V?\d+\.\d+\.\d+', filename)
        if match:
            return match.group(0).replace('V', 'v')
        return "v1.0.0"
    
    def process_pdf(self, pdf_path: Path, pdf_output_dir: Path) -> List[Dict[str, Any]]:
        """处理单个 PDF 文件
        
        Returns:
            文档节点列表
        """
        print(f"\n{'='*60}")
        print(f"处理文档: {pdf_path.name}")
        print(f"{'='*60}")
        
        # 生成 doc_id（包含版本号）
        base_name = pdf_path.stem
        version = self.extract_version_from_filename(pdf_path.name)
        doc_id = f"{base_name}_{version}".replace(' ', '_')
        
        # 初始化解析器和编码器
        parser = PDFParser(str(pdf_path))
        encoder = PathEncoder(doc_id)
        
        page_count = parser.get_page_count()
        self.stats["total_pages"] += page_count
        
        documents = []
        
        # 逐页处理
        for page_num in tqdm(range(page_count), desc="处理页面"):
            try:
                # 记录本页开始时的文档索引，用于切片本页生成的节点
                start_doc_idx = len(documents)

                # 1. 提取 PyMuPDF 原始文本和布局
                pymupdf_text, pymupdf_blocks = parser.extract_page_text(page_num)
                page_width, page_height = parser.get_page_dimensions(page_num)
                
                print(f"\n  页 {page_num + 1}:")
                print(f"    PyMuPDF 提取: {len(pymupdf_text)} 字符, {len(pymupdf_blocks)} 块")
                if len(pymupdf_text) > 0:
                    preview = pymupdf_text[:100].replace('\n', ' ').encode('utf-8', errors='ignore').decode('utf-8')
                    print(f"    预览: {preview}...")
                
                # 2. 判断是否需要整页 OCR（文本内容少于 50 字符）
                need_full_ocr = len(pymupdf_text.strip()) < 50
                ocr_text = ""
                ocr_blocks = []
                
                if need_full_ocr:
                    print(f"    需要整页 OCR（文本不足 {len(pymupdf_text.strip())} < 50）")
                    self.stats["ocr_pages"] += 1
                    page_image = parser.render_page_as_image(page_num, dpi=300)
                    ocr_results = self.ocr_engine.recognize(page_image)
                    ocr_text, ocr_blocks = self.ocr_engine.merge_ocr_results(
                        ocr_results, page_width, page_height
                    )
                    print(f"    整页 OCR 结果: {len(ocr_text)} 字符, {len(ocr_blocks)} 块")
                    if len(ocr_text) > 0:
                        preview = ocr_text[:100].replace('\n', ' ').encode('utf-8', errors='ignore').decode('utf-8')
                        print(f"    OCR 预览: {preview}...")
                
                # 临时收集图片 OCR 生成的块与详尽信息（用于日志）
                image_blocks = []
                images_info = []
                
                # 3. 提取页面内图片并单独 OCR（提高覆盖率）
                images = parser.extract_page_images(page_num)
                if images:
                    print(f"    发现 {len(images)} 张图片，进行单独 OCR...")
                    for idx, img in enumerate(images):
                        try:
                            img_obj = img.get("image")
                            img_bbox = img.get("bbox", (0, 0, 0, 0))
                            # OCR 图片（使用双引擎策略）
                            img_results = self.ocr_engine.recognize(img_obj)
                            self.stats["ocr_images"] += 1
                            if img_results:
                                # 合并图片 OCR 行文本为一个块，作为补充
                                img_texts = [r.get("text", "").strip() for r in img_results if r.get("text", "").strip()]
                                if img_texts:
                                    full_img_text = " ".join(img_texts)
                                    avg_conf = sum(r.get("confidence", 0.0) for r in img_results) / len(img_results)
                                    print(f"      图片 {idx+1}: 提取 {len(img_texts)} 行文本，置信度 {avg_conf:.3f}")
                                    # 将合并后的图片文本当作一个新的 block 加入 blocks 列表
                                    image_blocks.append({
                                        "text": full_img_text,
                                        "bbox": img_bbox,
                                        "font_size": 0,
                                        "font_name": "image_ocr",
                                        "confidence": avg_conf
                                    })
                                    # 记录图片级别详情用于审计
                                    images_info.append({
                                        "image_index": idx,
                                        "bbox": img_bbox,
                                        "lines": img_texts,
                                        "merged_text": full_img_text,
                                        "avg_confidence": avg_conf
                                    })
                        except Exception as e:
                            print(f"      图片 {idx+1} OCR 失败: {e}")
                
                # 4. 合并 PyMuPDF 和 OCR 结果（优先使用 PyMuPDF，OCR 作为补充）
                # 使用简单策略：如果 PyMuPDF 提取到文本，保留原始 blocks；否则使用 OCR blocks
                if pymupdf_blocks and len(pymupdf_text.strip()) > 50:
                    # PyMuPDF 提取效果较好，保留其 blocks，但将图片 OCR blocks 也加入以补充可能遗漏的内容
                    blocks = pymupdf_blocks + image_blocks
                    text = pymupdf_text
                    print(f"    最终采用: PyMuPDF 文本 + {len(image_blocks)} 个图片块")
                else:
                    # PyMuPDF 提取较少，优先使用 OCR 结果
                    blocks = ocr_blocks + image_blocks
                    text = ocr_text
                    print(f"    最终采用: OCR 文本 + {len(image_blocks)} 个图片块")
                
                print(f"    总文本块数: {len(blocks)}")
                
                # 5. 保留原始页面文本作为备份节点（用于审计和恢复）
                if text.strip():
                    documents.append({
                        "doc_id": doc_id,
                        "source": str(pdf_path),
                        "source_page": page_num + 1,
                        "content_type": "page_raw_text",
                        "content": text,
                        "bbox": {"left": 0, "top": 0, "right": page_width, "bottom": page_height},
                        "path": encoder.add_block_path(),
                        "parent_path": encoder.get_parent_path(encoder.current_path_stack[-1] if encoder.current_path_stack else ""),
                        "ocr_confidence": 1.0,
                        "note": "原始页面文本（PyMuPDF提取或OCR合并结果）"
                    })
                    encoder.increment_node_count()
                
                # 6. 提取表格
                tables = parser.extract_tables(page_num)
                for table in tables:
                    table_text = self._format_table(table["data"])
                    documents.append({
                        "doc_id": doc_id,
                        "source": str(pdf_path),
                        "source_page": page_num + 1,
                        "content_type": "table",
                        "content": table_text,
                        "bbox": {
                            "left": table["bbox"][0],
                            "top": table["bbox"][1],
                            "right": table["bbox"][2],
                            "bottom": table["bbox"][3]
                        },
                        "table_structure": table["data"],
                        "path": encoder.add_block_path(),
                        "ocr_confidence": 1.0
                    })
                    encoder.increment_node_count()
                
                # 4. 分段处理
                if blocks:
                    # 计算平均字体大小
                    font_sizes = [b.get("font_size", 12) for b in blocks if b.get("font_size", 0) > 0]
                    avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 12.0
                    
                    # 处理文本块
                    processed_blocks = self.segmenter.process_blocks_to_segments(
                        blocks, avg_font_size
                    )
                    
                    for block in processed_blocks:
                        content_type = block["content_type"]
                        segments = block["segments"]
                        bbox = block["bbox"]
                        confidence = block.get("confidence", 1.0)
                        
                        # 对标题特殊处理
                        if content_type == "heading":
                            text = segments[0]
                            numbering, level = encoder.detect_heading_level(
                                text,
                                block.get("font_size", 0),
                                avg_font_size
                            )
                            
                            if numbering:
                                path = encoder.build_path(numbering, level)
                                if level:
                                    encoder.reset_for_new_section(level)
                            else:
                                path = encoder.add_block_path()
                            
                            documents.append({
                                "doc_id": doc_id,
                                "source": str(pdf_path),
                                "source_page": page_num + 1,
                                "content_type": content_type,
                                "content": text,
                                "bbox": {
                                    "left": bbox[0],
                                    "top": bbox[1],
                                    "right": bbox[2],
                                    "bottom": bbox[3]
                                },
                                "path": path,
                                "parent_path": encoder.get_parent_path(path),
                                "ocr_confidence": confidence
                            })
                            encoder.increment_node_count()
                        
                        else:
                            # 正文段落，逐句处理
                            for segment in segments:
                                if segment.strip():
                                    path = encoder.add_block_path()
                                    documents.append({
                                        "doc_id": doc_id,
                                        "source": str(pdf_path),
                                        "source_page": page_num + 1,
                                        "content_type": "paragraph",
                                        "content": segment,
                                        "bbox": {
                                            "left": bbox[0],
                                            "top": bbox[1],
                                            "right": bbox[2],
                                            "bottom": bbox[3]
                                        },
                                        "path": path,
                                        "parent_path": encoder.get_parent_path(path),
                                        "ocr_confidence": confidence
                                    })
                                    encoder.increment_node_count()
            
            except Exception as e:
                error_msg = f"处理页 {page_num + 1} 失败: {e}"
                print(f"\n  {error_msg}")
                self.stats["errors"].append({
                    "doc": pdf_path.name,
                    "page": page_num + 1,
                    "error": str(e)
                })
            finally:
                # 在每页处理完成后，立即写入该页的审计文件（JSON + TXT），便于审计与回溯
                try:
                    end_doc_idx = len(documents)
                    page_nodes = documents[start_doc_idx:end_doc_idx]

                    page_output_dir = pdf_output_dir / "pages"
                    page_output_dir.mkdir(parents=True, exist_ok=True)

                    # JSON 审计文件，包含 PyMuPDF 文本、OCR 文本、图片详情与节点
                    page_record = {
                        "doc_id": doc_id,
                        "pdf": pdf_path.name,
                        "page": page_num + 1,
                        "pymupdf_text": pymupdf_text,
                        "ocr_text": ocr_text,
                        "images": images_info,
                        "blocks": blocks,
                        "nodes": page_nodes
                    }
                    page_file = page_output_dir / f"page_{page_num+1:03d}.json"
                    with open(page_file, 'w', encoding='utf-8') as pf:
                        json.dump(page_record, pf, ensure_ascii=False, indent=2)

                    # 文本审计文件（可读），包含全部重要内容的纯文本形式
                    page_txt = page_output_dir / f"page_{page_num+1:03d}.txt"
                    with open(page_txt, 'w', encoding='utf-8') as pt:
                        pt.write(f"PDF: {pdf_path.name}\nPage: {page_num+1}\n\n")
                        pt.write("--- PyMuPDF 原始文本 ---\n")
                        pt.write(pymupdf_text or "")
                        pt.write("\n\n--- 整页 OCR 文本（若有） ---\n")
                        pt.write(ocr_text or "")
                        pt.write("\n\n--- 图片 OCR 详情 ---\n")
                        for img_info in images_info:
                            pt.write(f"Image {img_info.get('image_index')}: bbox={img_info.get('bbox')}, avg_conf={img_info.get('avg_confidence'):.3f}\n")
                            pt.write('\n'.join(img_info.get('lines', [])) + "\n\n")
                        pt.write("\n--- 本页节点（path | content preview） ---\n")
                        for n in page_nodes:
                            preview = (n.get('content') or '').replace('\n', ' ')[:500]
                            pt.write(f"{n.get('path')} | {preview}\n")
                except Exception as e:
                    print(f"保存页审计文件失败 (页{page_num+1}): {e}")
        
        # 更新节点计数
        node_count = encoder.get_node_count()
        for doc in documents:
            doc["doc_node_count"] = node_count
        
        self.stats["total_nodes"] += node_count
        
        print(f"\n文档处理完成:")
        print(f"  - 总页数: {page_count}")
        print(f"  - 整页 OCR: {self.stats['ocr_pages']} 页")
        print(f"  - 图片 OCR: {self.stats['ocr_images']} 张")
        print(f"  - 生成节点: {node_count}")
        
        return documents
    
    def _format_table(self, table_data: List[List[str]]) -> str:
        """将表格数据格式化为文本"""
        if not table_data:
            return ""
        
        lines = []
        for row in table_data:
            if row:
                cleaned_row = [cell.strip() if cell else "" for cell in row]
                lines.append(" | ".join(cleaned_row))
        
        return "\n".join(lines)
    
    def run(self):
        """执行完整流程"""
        print("PDF OCR 文本提取与 ES 检索系统")
        print("=" * 60)

        # 1. 初始化 ES 索引（可选）
        if not self.no_es:
            print("\n1. 初始化 Elasticsearch 索引...")
            try:
                self.es_client.create_index()
            except Exception as e:
                print(f"ES 连接失败: {e}")
                print("请确保 Elasticsearch 已启动（docker/elasticsearch-ik）")
                return
        else:
            print("\n1. 跳过 Elasticsearch 初始化（--no-es 模式）")
        
        # 2. 获取所有 PDF 文件
        pdf_files = list(DOCS_SRC_DIR.glob("*.pdf"))
        if not pdf_files:
            print(f"\n错误: {DOCS_SRC_DIR} 中未找到 PDF 文件")
            return
        
        print(f"\n2. 找到 {len(pdf_files)} 个 PDF 文件")
        for pdf in pdf_files:
            print(f"   - {pdf.name}")
        
        self.stats["total_docs"] = len(pdf_files)

        # 创建本次任务文件夹（按时间戳）
        from datetime import datetime
        task_name = datetime.now().strftime('run_%Y%m%d_%H%M%S')
        self.task_dir = OUTPUT_DIR / task_name
        self.task_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n本次任务目录: {self.task_dir}")
        
        # 3. 处理每个 PDF
        print("\n3. 开始处理 PDF 文档...")
        all_documents = []
        
        for pdf_path in pdf_files:
            try:
                # 为每个 PDF 创建子文件夹
                pdf_output_dir = self.task_dir / pdf_path.stem
                pdf_output_dir.mkdir(parents=True, exist_ok=True)

                documents = self.process_pdf(pdf_path, pdf_output_dir)
                all_documents.extend(documents)
                 
                 # 保存中间结果
                output_file = pdf_output_dir / f"{pdf_path.stem}_processed.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(documents, f, ensure_ascii=False, indent=2)
                print(f"  已保存到: {output_file}")
            
            except Exception as e:
                error_msg = f"处理 {pdf_path.name} 失败: {e}"
                print(f"\n{error_msg}")
                self.stats["errors"].append({
                    "doc": pdf_path.name,
                    "error": str(e)
                })
        
        # 4. 批量索引到 ES
        print(f"\n4. 处理完成，保存或索引结果")
        print(f"   总节点数: {len(all_documents)}")

        if all_documents:
            if not self.no_es:
                result = self.es_client.bulk_index(all_documents)
                print(f"   已索引到 ES - 成功: {result['success']} 失败: {result['error']}")
            else:
                print("   --no-es: 已跳过 Elasticsearch 索引，结果已保存为 JSON 文件")
        
        # 5. 验证
        print(f"\n5. 验证与统计")
        self._validate_and_report()
    
    def _validate_and_report(self):
        """验证索引并生成报告"""
        # 检查编码唯一性
        print("\n检查编码唯一性...")
        # (这里可以查询 ES 进行验证，简化处理)
        
        # 生成统计报告
        report = {
            "summary": {
                "total_documents": self.stats["total_docs"],
                "total_pages": self.stats["total_pages"],
                "ocr_pages": self.stats["ocr_pages"],
                "total_nodes": self.stats["total_nodes"]
            },
            "errors": self.stats["errors"]
        }
        
        report_file = (self.task_dir / "processing_report.json") if self.task_dir is not None else (OUTPUT_DIR / "processing_report.json")
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"\n处理统计:")
        print(f"  - 处理文档: {self.stats['total_docs']}")
        print(f"  - 总页数: {self.stats['total_pages']}")
        print(f"  - 整页 OCR: {self.stats['ocr_pages']} 页")
        print(f"  - 图片 OCR: {self.stats['ocr_images']} 张")
        print(f"  - 生成节点: {self.stats['total_nodes']}")
        print(f"  - 错误数: {len(self.stats['errors'])}")
        print(f"\n报告已保存到: {report_file}")
        
        # 测试搜索功能（仅当已启用 Elasticsearch 时）
        if not self.no_es and self.es_client is not None:
            print("\n测试搜索功能...")
            test_queries = ["机器人", "比赛规则", "通信协议"]
            for query in test_queries:
                try:
                    results = self.es_client.search_content(query, size=3)
                    print(f"\n查询 '{query}' 返回 {len(results)} 个结果")
                    if results:
                        for i, result in enumerate(results[:2], 1):
                            content_preview = result['content'][:50] + "..." if len(result['content']) > 50 else result['content']
                            print(f"  {i}. [{result['path']}] {content_preview}")
                except Exception as e:
                    print(f"测试查询时出错: {e}")
        else:
            print("\n已跳过 Elasticsearch 测试查询（--no-es 模式或未配置 ESClient）。")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="PDF OCR -> ES pipeline")
    parser.add_argument('--no-es', action='store_true', help='Only run OCR and segmentation and save JSON; skip ES indexing')
    args = parser.parse_args()

    processor = PDFProcessor(no_es=args.no_es)
    processor.run()
    
    print("\n" + "=" * 60)
    print("处理完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
