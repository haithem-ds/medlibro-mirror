# Create the GitHub repo and push this folder.
#
# Auth (pick one):
#   A) Interactive:  gh auth login
#   B) Token (CI / Cursor): set GH_TOKEN or GITHUB_TOKEN to a classic PAT with "repo" scope
#      (create at https://github.com/settings/tokens — do not paste tokens into chat)
#
# Usage: .\push-to-github.ps1 [repo-name]
# Default repo name: medlibro-mirror

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

$token = $env:GH_TOKEN
if (-not $token) { $token = $env:GITHUB_TOKEN }

if ($token) {
    Write-Host "Authenticating with GitHub using GH_TOKEN / GITHUB_TOKEN from environment..." -ForegroundColor DarkGray
    $token | gh auth login --with-token -h github.com
    if ($LASTEXITCODE -ne 0) {
        Write-Host "gh auth login --with-token failed. Check token scopes (needs repo)." -ForegroundColor Red
        exit 1
    }
} else {
    cmd /c "gh auth status >nul 2>&1"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Not logged in to GitHub. Choose one:" -ForegroundColor Yellow
        Write-Host "  1) Run:  gh auth login" -ForegroundColor Cyan
        Write-Host "  2) Or set env var GH_TOKEN (PAT with repo scope), then run this script again." -ForegroundColor Cyan
        Write-Host "See DEPLOY.md -> GitHub authentication." -ForegroundColor DarkGray
        exit 1
    }
}

$repo = if ($args.Count -ge 1 -and $args[0]) { $args[0] } else { "medlibro-mirror" }

cmd /c "git remote get-url origin >nul 2>&1"
if ($LASTEXITCODE -eq 0) {
    Write-Host "Remote 'origin' already exists. Pushing to existing remote..." -ForegroundColor Yellow
    git push -u origin main
    exit $LASTEXITCODE
}

gh repo create $repo --public --source=. --remote=origin --push --description "MedLibro offline mirror + Flask API (Docker/Render)"
