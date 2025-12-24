"""OCR 引擎模块 - 双引擎策略（RapidOCR + PaddleOCR）"""
from typing import List, Dict, Any, Tuple
import inspect
from PIL import Image
import numpy as np
from config import OCR_CONFIDENCE_THRESHOLD, USE_GPU


class OCREngine:
    """OCR 引擎封装，支持 RapidOCR（优先）和 PaddleOCR（备用）"""
    
    def __init__(self):
        self.confidence_threshold = OCR_CONFIDENCE_THRESHOLD
        self.use_gpu = USE_GPU
        
        # 初始化 RapidOCR
        try:
            from rapidocr_onnxruntime import RapidOCR
            self.rapid_ocr = RapidOCR()
            print("RapidOCR 初始化成功")
        except ImportError:
            print("警告: RapidOCR 未安装，将只使用 PaddleOCR")
            self.rapid_ocr = None
        
        # 初始化 PaddleOCR（仅传入该版本支持的参数）
        try:
            from paddleocr import PaddleOCR
            # 构造候选参数，然后通过 inspect 签名过滤仅支持的参数
            candidate_kwargs = {
                # 禁用 angle cls 来避免部分版本内部调用 predict 时传递不兼容的 cls 参数
                "use_angle_cls": False,
                "lang": "ch",
                "use_gpu": self.use_gpu,
                "show_log": False
            }
            try:
                sig = inspect.signature(PaddleOCR.__init__)
                supported = set(sig.parameters.keys())
                # remove 'self' if present
                supported.discard('self')
                filtered = {k: v for k, v in candidate_kwargs.items() if k in supported}
            except Exception:
                filtered = candidate_kwargs

            self.paddle_ocr = PaddleOCR(**filtered)
            print("PaddleOCR initialized (filtered args):", filtered)
        except ImportError:
            print("Warning: PaddleOCR not installed")
            self.paddle_ocr = None
    
    def _run_rapid_ocr(self, image: Image.Image) -> Tuple[List[Dict[str, Any]], float]:
        """使用 RapidOCR 进行识别
        
        Returns:
            (results, avg_confidence): 识别结果和平均置信度
            results 格式: [{
                'text': str,
                'bbox': [x0, y0, x1, y1],
                'confidence': float
            }]
        """
        if self.rapid_ocr is None:
            return [], 0.0
        
        # 转换为 numpy 数组
        img_array = np.array(image)
        
        # 执行 OCR
        result, elapse = self.rapid_ocr(img_array)
        
        if not result:
            return [], 0.0
        
        # 解析结果
        ocr_results = []
        confidences = []
        
        for line in result:
            bbox_points = line[0]  # [[x0,y0], [x1,y1], [x2,y2], [x3,y3]]
            text = line[1]
            confidence = line[2]
            
            # 转换 bbox 为 [x0, y0, x1, y1] 格式
            x_coords = [p[0] for p in bbox_points]
            y_coords = [p[1] for p in bbox_points]
            bbox = [min(x_coords), min(y_coords), max(x_coords), max(y_coords)]
            
            ocr_results.append({
                "text": text,
                "bbox": bbox,
                "confidence": confidence
            })
            confidences.append(confidence)
        
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        return ocr_results, avg_confidence
    
    def _run_paddle_ocr(self, image: Image.Image) -> Tuple[List[Dict[str, Any]], float]:
        """使用 PaddleOCR 进行识别"""
        if self.paddle_ocr is None:
            return [], 0.0
        
        # 对超大图像进行下采样以加快识别并减少内存占用
        try:
            orig_w, orig_h = image.size
            max_dim = 1600
            if max(orig_w, orig_h) > max_dim:
                scale = max_dim / max(orig_w, orig_h)
                new_size = (int(orig_w * scale), int(orig_h * scale))
                image_for_ocr = image.resize(new_size, Image.LANCZOS)
            else:
                image_for_ocr = image
        except Exception:
            image_for_ocr = image

        # 转换为 numpy 数组
        img_array = np.array(image_for_ocr)
        
        # 执行 OCR，带多个兼容性回退策略以避免不同 PaddleOCR 版本导致的 TypeError
        try:
            result = self.paddle_ocr.ocr(img_array)
        except TypeError as e:
            # 兼容性问题：尝试不同的调用方式
            print(f"PaddleOCR.ocr TypeError: {e}; 尝试使用 PIL.Image 输入作为回退。")
            try:
                result = self.paddle_ocr.ocr(image)
            except Exception as e2:
                print(f"PaddleOCR.ocr(PIL) 失败: {e2}; 尝试重新初始化 PaddleOCR 并重试。")
                try:
                    from paddleocr import PaddleOCR
                    # 更保守的重试：仅传入最小化参数
                    self.paddle_ocr = PaddleOCR(lang='ch')
                    result = self.paddle_ocr.ocr(img_array)
                except Exception as e3:
                    print(f"PaddleOCR 重试失败: {e3}")
                    return [], 0.0
        except Exception as e:
            print(f"PaddleOCR.ocr 失败: {e}")
            return [], 0.0
        
        if not result:
            return [], 0.0
        
        # 针对不同版本的返回格式做兼容解析
        seq = result[0] if isinstance(result, list) and len(result) > 0 else result
        ocr_results = []
        confidences = []
        for line in seq:
            try:
                bbox_points = line[0]  # [[x0,y0], [x1,y1], [x2,y2], [x3,y3]]
            except Exception:
                bbox_points = None

            # 解析文本和置信度，兼容多种格式
            text = ""
            confidence = 0.0
            if isinstance(line[1], (list, tuple)) and len(line[1]) >= 2:
                text = line[1][0]
                confidence = float(line[1][1]) if line[1][1] is not None else 0.0
            else:
                # 可能是单字符串或其他结构
                try:
                    text = str(line[1])
                except Exception:
                    text = ""

            # 转换 bbox 为 [x0, y0, x1, y1] 格式
            try:
                if bbox_points and isinstance(bbox_points, (list, tuple)):
                    x_coords = [p[0] for p in bbox_points]
                    y_coords = [p[1] for p in bbox_points]
                    bbox = [min(x_coords), min(y_coords), max(x_coords), max(y_coords)]
                else:
                    bbox = [0, 0, 0, 0]  # 无法解析时给个默认值
            except Exception as e:
                print(f"解析 PaddleOCR bbox 时出错，使用默认 bbox: {e}; raw_line={line}")
                bbox = [0, 0, 0, 0]
            
            ocr_results.append({
                "text": text,
                "bbox": bbox,
                "confidence": confidence
            })
            confidences.append(confidence)
        
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        return ocr_results, avg_confidence
    
    def recognize(self, image: Image.Image, force_paddle: bool = False) -> List[Dict[str, Any]]:
        """双引擎 OCR 识别策略
        
        1. 优先使用 RapidOCR
        2. 如果平均置信度 < 阈值，使用 PaddleOCR 重新识别
        
        Args:
            image: PIL Image 对象
            force_paddle: 是否强制使用 PaddleOCR
        
        Returns:
            List[{
                'text': str,
                'bbox': [x0, y0, x1, y1],
                'confidence': float,
                'engine': 'rapid' | 'paddle'
            }]
        """
        if force_paddle or self.rapid_ocr is None:
            # 直接使用 PaddleOCR
            results, avg_conf = self._run_paddle_ocr(image)
            for r in results:
                r["engine"] = "paddle"
            print(f"  使用 PaddleOCR, 平均置信度: {avg_conf:.3f}")
            return results
        
        # 先使用 RapidOCR
        results, avg_conf = self._run_rapid_ocr(image)
        
        if avg_conf >= self.confidence_threshold:
            # 置信度足够，使用 RapidOCR 结果
            for r in results:
                r["engine"] = "rapid"
            print(f"  使用 RapidOCR, 平均置信度: {avg_conf:.3f}")
            return results
        
        # 置信度不足，使用 PaddleOCR 重新识别
        print(f"  RapidOCR 置信度低 ({avg_conf:.3f} < {self.confidence_threshold}), 使用 PaddleOCR 重新识别")
        results, avg_conf = self._run_paddle_ocr(image)
        for r in results:
            r["engine"] = "paddle"
        print(f"  PaddleOCR 平均置信度: {avg_conf:.3f}")
        return results
    
    def merge_ocr_results(self, ocr_results: List[Dict[str, Any]], 
                          page_width: float, page_height: float) -> Tuple[str, List[Dict[str, Any]]]:
        """合并 OCR 结果为文本块
        
        Args:
            ocr_results: OCR 识别结果
            page_width, page_height: 页面尺寸
        
        Returns:
            (full_text, blocks): 完整文本和文本块列表
        """
        if not ocr_results:
            return "", []
        
        # 按 Y 坐标排序（从上到下）
        sorted_results = sorted(ocr_results, key=lambda x: x["bbox"][1])
        
        # 合并为文本块（相邻行如果 Y 坐标接近则合并）
        blocks = []
        current_block = None
        y_threshold = page_height * 0.02  # 2% 页面高度作为行间距阈值
        
        for item in sorted_results:
            if current_block is None:
                current_block = {
                    "text": item["text"],
                    "bbox": item["bbox"],
                    "confidence": item["confidence"],
                    "engine": item.get("engine", "unknown")
                }
            else:
                # 判断是否与上一行接近
                prev_bottom = current_block["bbox"][3]
                curr_top = item["bbox"][1]
                
                if curr_top - prev_bottom < y_threshold:
                    # 合并到当前块
                    current_block["text"] += " " + item["text"]
                    # 扩展 bbox
                    current_block["bbox"] = [
                        min(current_block["bbox"][0], item["bbox"][0]),
                        min(current_block["bbox"][1], item["bbox"][1]),
                        max(current_block["bbox"][2], item["bbox"][2]),
                        max(current_block["bbox"][3], item["bbox"][3])
                    ]
                    # 更新置信度（平均值）
                    current_block["confidence"] = (
                        current_block["confidence"] + item["confidence"]
                    ) / 2
                else:
                    # 开始新块
                    blocks.append(current_block)
                    current_block = {
                        "text": item["text"],
                        "bbox": item["bbox"],
                        "confidence": item["confidence"],
                        "engine": item.get("engine", "unknown")
                    }
        
        if current_block:
            blocks.append(current_block)
        
        # 生成完整文本
        full_text = "\n".join([block["text"] for block in blocks])
        
        return full_text, blocks
