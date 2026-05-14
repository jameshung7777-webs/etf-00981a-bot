# 每日：抓取持股 → 若有 JSON 變更則 commit + push（本機工作排程器用）
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $RepoRoot

function Invoke-MainPy {
    param([string[]]$PyArgs)
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 (Join-Path $RepoRoot "main.py") @PyArgs
    } else {
        & python (Join-Path $RepoRoot "main.py") @PyArgs
    }
}

Invoke-MainPy -PyArgs @("--fetch-only")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

git add holdings_data.json holdings_data_*.json 2>$null
git diff --staged --quiet 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "[i] 無持股 JSON 變更，略過 commit/push"
    exit 0
}

$d = Get-Date -Format "yyyy-MM-dd"
git commit -m "chore: 排程儲存每日持股數據 $d"
$branch = (git symbolic-ref -q --short HEAD 2>$null)
if ([string]::IsNullOrWhiteSpace($branch)) {
    Write-Warning "不在任何分支上，無法 push"
    exit 1
}
git push -u origin $branch.Trim()
exit $LASTEXITCODE
