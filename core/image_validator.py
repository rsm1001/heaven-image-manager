"""图片质量校验模块"""
from pathlib import Path
from typing import Tuple, List, Dict, Optional, Callable
from PIL import Image
from datetime import datetime
import threading
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.config import Config
from utils.logger import logger

# 损坏错误类型常量
ERROR_BROKEN_HEADER = "broken_header"
ERROR_DECODE_FAILED = "decode_failed"
ERROR_TRUNCATED = "truncated"
ERROR_SIZE_MISMATCH = "size_mismatch"
ERROR_UNKNOWN = "unknown"


class ImageValidationResult:
    """单张图片校验结果"""

    def __init__(self, path: Path, is_valid: bool,
                 error_type: str = None, error_msg: str = None):
        self.path = path
        self.is_valid = is_valid
        self.error_type = error_type
        self.error_msg = error_msg
        self.file_size_kb = 0
        self.checked_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if path.exists():
            self.file_size_kb = path.stat().st_size // 1024

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "name": self.path.name,
            "size_kb": self.file_size_kb,
            "is_valid": self.is_valid,
            "error_type": self.error_type,
            "error_msg": self.error_msg,
            "checked_time": self.checked_time
        }


class ImageValidator:
    """单张图片校验器"""

    @staticmethod
    def validate(path: Path) -> ImageValidationResult:
        """校验单张图片是否损坏

        Args:
            path: 图片路径

        Returns:
            ImageValidationResult: 校验结果
        """
        try:
            if not path.exists():
                return ImageValidationResult(
                    path, False, ERROR_UNKNOWN, "文件不存在"
                )

            # 检查文件大小是否异常（小于1KB的图片几乎肯定是损坏的）
            if path.stat().st_size < 1024:
                return ImageValidationResult(
                    path, False, ERROR_SIZE_MISMATCH, f"文件大小异常({path.stat().st_size}字节)"
                )

            # 使用PIL打开图片
            with Image.open(path) as img:
                # 验证图片头部完整性
                try:
                    img.verify()
                except Exception as e:
                    return ImageValidationResult(
                        path, False, ERROR_BROKEN_HEADER, f"图片头部损坏: {str(e)}"
                    )

            # 重新打开以强制解码（verify后需要重新打开）
            with Image.open(path) as img:
                try:
                    # 强制加载整个图片以触发解码
                    img.load()
                except EOFError as e:
                    return ImageValidationResult(
                        path, False, ERROR_TRUNCATED, f"图片数据截断: {str(e)}"
                    )
                except IOError as e:
                    return ImageValidationResult(
                        path, False, ERROR_DECODE_FAILED, f"图片解码失败: {str(e)}"
                    )
                except OSError as e:
                    # 某些PIL版本会将解码错误归类为OSError
                    return ImageValidationResult(
                        path, False, ERROR_DECODE_FAILED, f"图片解码失败(OSError): {str(e)}"
                    )
                except Exception as e:
                    return ImageValidationResult(
                        path, False, ERROR_UNKNOWN, f"未知错误: {str(e)}"
                    )

            # 校验通过
            return ImageValidationResult(path, True)

        except Exception as e:
            logger.error(f"校验图片失败 {path}: {e}")
            return ImageValidationResult(
                path, False, ERROR_UNKNOWN, f"校验异常: {str(e)}"
            )


class BatchValidator:
    """批量图片校验器"""

    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers
        self.is_running = False
        self.is_cancelled = False
        self._results: List[ImageValidationResult] = []
        self._lock = threading.Lock()
        self._completed_count = 0
        self._total_count = 0

    def validate_directory(self, directory: Path,
                          progress_callback: Callable = None,
                          completed_callback: Callable = None) -> List[ImageValidationResult]:
        """批量校验目录下所有图片

        Args:
            directory: 要校验的目录
            progress_callback: 进度回调 (current, total, current_file)
            completed_callback: 完成回调 (results)

        Returns:
            List[ImageValidationResult]: 所有校验结果
        """
        self.is_running = True
        self.is_cancelled = False
        self._results = []
        self._completed_count = 0

        # 扫描目录下所有图片文件
        image_files = []
        for ext in Config.IMAGE_EXTENSIONS:
            image_files.extend(directory.glob(f"*{ext}"))
            image_files.extend(directory.glob(f"*{ext.upper()}"))

        # 去重
        unique_files = []
        seen = set()
        for f in image_files:
            key = str(f.resolve())
            if key not in seen:
                seen.add(key)
                unique_files.append(f)

        self._total_count = len(unique_files)
        self._results = []

        if not unique_files:
            logger.info(f"目录中没有图片文件: {directory}")
            self.is_running = False
            return []

        logger.info(f"开始校验目录: {directory}, 图片数量: {self._total_count}")

        # 使用线程池并行校验
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(self._validate_with_result, f): f
                for f in unique_files
            }

            for future in as_completed(future_to_file):
                if self.is_cancelled:
                    break

                file_path = future_to_file[future]
                try:
                    result = future.result()
                    with self._lock:
                        self._results.append(result)
                        self._completed_count += 1
                        current = self._completed_count

                    if progress_callback:
                        progress_callback(current, self._total_count, file_path.name)

                except Exception as e:
                    logger.error(f"校验任务异常 {file_path}: {e}")
                    with self._lock:
                        self._completed_count += 1

        self.is_running = False
        logger.info(f"校验完成: 总计{self._total_count}, 损坏{len(self.get_corrupted())}")

        if completed_callback:
            completed_callback(self._results)

        return self._results

    def _validate_with_result(self, path: Path) -> ImageValidationResult:
        """校验单张图片并返回结果"""
        return ImageValidator.validate(path)

    def cancel(self):
        """取消校验"""
        self.is_cancelled = True
        self.is_running = False
        logger.info("校验已取消")

    def get_corrupted(self) -> List[ImageValidationResult]:
        """获取损坏图片列表"""
        return [r for r in self._results if not r.is_valid]

    def get_valid(self) -> List[ImageValidationResult]:
        """获取正常图片列表"""
        return [r for r in self._results if r.is_valid]

    def get_summary(self) -> dict:
        """获取校验汇总"""
        return {
            "total": self._total_count,
            "valid_count": len(self.get_valid()),
            "corrupted_count": len(self.get_corrupted()),
            "corrupted_rate": f"{len(self.get_corrupted()) / max(self._total_count, 1) * 100:.1f}%"
        }


class ValidationReportExporter:
    """校验报告导出器"""

    @staticmethod
    def export_json(results: List[ImageValidationResult],
                    output_path: Path) -> bool:
        """导出JSON格式报告

        Args:
            results: 校验结果列表
            output_path: 输出文件路径

        Returns:
            bool: 是否成功
        """
        try:
            report = {
                "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_count": len(results),
                "valid_count": len([r for r in results if r.is_valid]),
                "corrupted_count": len([r for r in results if not r.is_valid]),
                "images": [r.to_dict() for r in results]
            }

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            logger.info(f"JSON报告已导出: {output_path}")
            return True

        except Exception as e:
            logger.error(f"导出JSON报告失败: {e}")
            return False

    @staticmethod
    def export_txt(results: List[ImageValidationResult],
                   output_path: Path,
                   directory: Path = None) -> bool:
        """导出TXT格式报告

        Args:
            results: 校验结果列表
            output_path: 输出文件路径
            directory: 校验的目录

        Returns:
            bool: 是否成功
        """
        try:
            corrupted = [r for r in results if not r.is_valid]
            valid = [r for r in results if r.is_valid]

            lines = []
            lines.append("=" * 60)
            lines.append("图片质量校验报告")
            lines.append("=" * 60)
            lines.append(f"校验时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            if directory:
                lines.append(f"校验目录: {directory}")
            lines.append(f"总计校验: {len(results)} 张")
            lines.append(f"正常图片: {len(valid)} 张")
            lines.append(f"损坏图片: {len(corrupted)} 张")

            if corrupted:
                lines.append("")
                lines.append("-" * 60)
                lines.append("损坏图片列表:")
                lines.append("-" * 60)

                for i, r in enumerate(corrupted, 1):
                    lines.append(f"{i}. {r.path.name}")
                    lines.append(f"   路径: {r.path}")
                    lines.append(f"   大小: {r.file_size_kb} KB")
                    lines.append(f"   错误类型: {r.error_type}")
                    lines.append(f"   错误信息: {r.error_msg}")
                    lines.append(f"   校验时间: {r.checked_time}")
                    lines.append("")

            lines.append("=" * 60)
            lines.append("报告生成完毕")
            lines.append("=" * 60)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines))

            logger.info(f"TXT报告已导出: {output_path}")
            return True

        except Exception as e:
            logger.error(f"导出TXT报告失败: {e}")
            return False
