"""测试清洗模块"""
from pathlib import Path
from src.text_cleaner import TextCleaner

# 指定要清洗的 PDF 输出目录
pdf_dir = Path('output/quick_run_test/RoboMaster 2026 机甲大师超级对抗赛比赛规则手册V1.0.0（20251021）')

if not pdf_dir.exists():
    print(f"错误: 目录不存在: {pdf_dir}")
    exit(1)

output_file = pdf_dir / 'cleaned_chunks.json'
log_file = pdf_dir / 'cleaner.log'

print(f"开始清洗: {pdf_dir}")
print(f"输出文件: {output_file}")
print(f"日志文件: {log_file}")
print("=" * 60)

cleaner = TextCleaner(
    confidence_threshold=0.1,
    short_line_threshold=20,
    height_ratio_threshold=1.3,
    min_gap_threshold=15.0,
    log_file=log_file
)

try:
    stats = cleaner.clean_document(pdf_dir, output_file)
    print("\n" + "=" * 60)
    print("清洗完成!")
    print(f"生成 chunks: {stats.get('total_chunks', 0)}")
    print(f"输出文件: {output_file}")
    print(f"日志文件: {log_file}")
    print("=" * 60)
except Exception as e:
    print(f"\n清洗失败: {e}")
    import traceback
    traceback.print_exc()
