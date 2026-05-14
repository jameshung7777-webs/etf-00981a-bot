# post-commit：在倉庫根目錄將目前分支 push 到 origin（供 Windows / 中文路徑使用）
$ErrorActionPreference = "Continue"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $repoRoot
$branch = (git symbolic-ref -q --short HEAD 2>$null)
if ([string]::IsNullOrWhiteSpace($branch)) { exit 0 }
git remote get-url origin *>$null
if ($LASTEXITCODE -ne 0) { exit 0 }
& git push -u origin $branch.Trim()
if ($LASTEXITCODE -eq 0) { exit 0 }
# 遠端若有新提交，先 rebase 再推一次（與 Actions 常見情境一致）
& git pull --rebase origin $branch.Trim()
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& git push -u origin $branch.Trim()
exit $LASTEXITCODE
