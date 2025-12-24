# 快速验证清洗聚合结果

Write-Host "======================================"
Write-Host "清洗聚合结果验证"
Write-Host "======================================"

$docDir = "output\quick_run_test\RoboMaster 2026 机甲大师超级对抗赛比赛规则手册V1.0.0（20251021）"

# 检查文件存在
$chunks = Join-Path $docDir "cleaned_chunks.json"
$sections = Join-Path $docDir "cleaned_basic_part.json"
$log = Join-Path $docDir "cleaner.log"

if (-not (Test-Path $chunks)) {
    Write-Host "❌ 未找到 cleaned_chunks.json"
    exit 1
}

if (-not (Test-Path $sections)) {
    Write-Host "❌ 未找到 cleaned_basic_part.json"
    exit 1
}

Write-Host "✓ 找到清洗输出文件`n"

# 读取统计
$chunksData = Get-Content $chunks -Encoding UTF8 | ConvertFrom-Json
$sectionsData = Get-Content $sections -Encoding UTF8 | ConvertFrom-Json

Write-Host "📊 一级清洗统计 (chunks):"
Write-Host "  - 总页数: $($chunksData.stats.total_pages)"
Write-Host "  - 总节点: $($chunksData.stats.total_nodes)"
Write-Host "  - 丢弃节点: $($chunksData.stats.dropped_nodes)"
Write-Host "  - 生成chunks: $($chunksData.stats.total_chunks)"
Write-Host "  - heading: $($chunksData.stats.chunk_types.heading)"
Write-Host "  - paragraph: $($chunksData.stats.chunk_types.paragraph)"
Write-Host "  - list_item: $($chunksData.stats.chunk_types.list_item)"
Write-Host "  - 平均chunk长度: $([math]::Round($chunksData.stats.avg_chunk_length, 1)) 字符`n"

Write-Host "📊 二级聚合统计 (sections):"
Write-Host "  - 总sections: $($sectionsData.stats.total_sections)"
Write-Host "  - 平均chunks/section: $([math]::Round($sectionsData.stats.avg_chunks_per_section, 1))`n"

# 验证页脚清除
$footerCount = ($chunksData.chunks | Where-Object { $_.content -match '©.*版权|版权所有' }).Count
Write-Host "🔍 页脚验证:"
if ($footerCount -eq 0) {
    Write-Host "  ✓ 所有页脚已清除 (0个版权信息残留)"
} else {
    Write-Host "  ⚠ 发现 $footerCount 个版权信息残留"
}

# 展示前3个sections
Write-Host "`n📖 前3个sections示例:"
for ($i = 0; $i -lt [Math]::Min(3, $sectionsData.sections.Count); $i++) {
    $sec = $sectionsData.sections[$i]
    $preview = $sec.content.Substring(0, [Math]::Min(60, $sec.content.Length))
    Write-Host "  [$($i+1)] $($sec.heading)"
    Write-Host "      页码: $($sec.page_range.first)-$($sec.page_range.last) | chunks: $($sec.chunk_count)"
    Write-Host "      内容: $preview...`n"
}

# 日志统计
if (Test-Path $log) {
    $logContent = Get-Content $log -Encoding UTF8
    $footerFiltered = ($logContent | Select-String "丢弃页脚").Count
    $lowConfFiltered = ($logContent | Select-String "丢弃低置信度").Count
    
    Write-Host "📝 日志记录:"
    Write-Host "  - 过滤页脚/页眉: $footerFiltered 次"
    Write-Host "  - 过滤低置信度节点: $lowConfFiltered 次"
}

Write-Host "`n======================================"
Write-Host "验证完成!"
Write-Host "======================================"
