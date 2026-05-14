# 每日：僅發送 Telegram（本機工作排程器用，建議接在抓取之後）
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $RepoRoot

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 (Join-Path $RepoRoot "main.py") --send-only
} else {
    & python (Join-Path $RepoRoot "main.py") --send-only
}
exit $LASTEXITCODE
