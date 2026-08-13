<#
.SYNOPSIS
    워드클라우드 배포 패키지 빌더
.DESCRIPTION
    기본: 소스만 배포 (wordcloud-source/ + wordcloud-project.zip)
    -Package: 전체 패키지 배포 (runtime + model + driver + source)
.PARAMETER Package
    전체 패키지 모드 (Python runtime + pip 패키지 + 모델 포함)
.PARAMETER OutputDir
    출력 경로 지정
.PARAMETER SkipDriver
    NVIDIA Driver 다운로드 생략 (전체 패키지 모드 한정)
.PARAMETER DriverUrl
    NVIDIA Driver 다운로드 URL
#>

param(
    [switch]$Package = $false,
    [string]$OutputDir = "",
    [switch]$SkipDriver = $false,
    [string]$DriverUrl = "https://us.download.nvidia.com/Windows/576.02/576.02-desktop-win10-win11-64bit-international-dch-whql.exe"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir/.."
$BasePythonPath = "$env:LOCALAPPDATA\Programs\Python\Python310"
$VenvPath = "$ProjectRoot\venv"
$ModelSource = if (Test-Path "$ProjectRoot\..\model") { Resolve-Path "$ProjectRoot\..\model" } else { "" }
$DefaultOutput = if ($OutputDir) { $OutputDir } else { "$ProjectRoot\.." }

$SourceZipPath = Join-Path $DefaultOutput "wordcloud-project.zip"
$FullOutputDir = Join-Path $DefaultOutput "wordcloud-internal"

$ExcludeDirs = @("venv", "__pycache__", ".git", ".sessions", "doc",
                 "vendor_python_pkgs", "logs", "temp", "node_modules", "deploy",
                 ".pytest_cache", "inputs", "scripts", ".opencode", ".clinerules", "failed",
                 "plans", "report", "default", "outputs", "processed_data",
                 # setup.py 빌드 잔재(옛 소스 사본 반입 방지 — 잔재 소스 트랩)
                 "build", "*.egg-info")
$ExcludeFiles = @("*.pyc", ".gitignore", "CACHEDIR.TAG", "README.md", "mermaid.min.js",
                  ".env", "*.jsonl", "*.zip", "flask_err.txt", "flask_out.txt")

function Write-Step {
    param([string]$Message)
    Write-Host "`n>>> $Message" -ForegroundColor Cyan
}

function Exec-Robocopy {
    param([string]$Source, [string]$Dest, [string[]]$ExcludeDirs = @(), [string[]]$ExcludeFiles = @())
    $args = @($Source, $Dest, "/E", "/NP", "/R:1", "/W:1")
    foreach ($ex in $ExcludeDirs) { $args += @("/XD", $ex) }
    foreach ($ef in $ExcludeFiles) { $args += @("/XF", $ef) }
    & robocopy @args
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
}

# ─── Sync VERSION.json (배포 정본: 모델 해시·학습일) ──────────────────
# 배포할 때마다 현재 model/hr_sentiment_finetuned 로 VERSION.json 을 재생성하고
# 모델 해시가 실제로 채워졌는지 확인한다. (구본이 그대로 실려 모달 학습일·무결성검사가
# 불일치로 뜨는 사고 방지 — VERSION.json 은 항상 이 빌드 단계가 정본으로 만든다.)
function Sync-Version {
    Write-Step "VERSION.json 동기화 (모델 해시·학습일 재생성)"
    $genScript = Join-Path $ProjectRoot "scripts\gen_version.py"
    if (-not (Test-Path $genScript)) {
        Write-Warning "gen_version.py 없음 — VERSION.json 동기화 생략"
        return
    }
    $py = if (Test-Path "$BasePythonPath\python.exe") { "$BasePythonPath\python.exe" } else { "python" }
    & $py $genScript
    if ($LASTEXITCODE -ne 0) { throw "gen_version.py 실패 ($LASTEXITCODE)" }

    # 검증: 모델 해시가 실제로 채워졌는지 (모델 누락 시 배포 후 무결성검사 불일치 예방)
    $vjson = Join-Path $ProjectRoot "VERSION.json"
    if (Test-Path $vjson) {
        $vi = Get-Content $vjson -Raw | ConvertFrom-Json
        if (-not $vi.model_sha256 -or $vi.model_sha256 -eq '-') {
            Write-Warning "  [!] 모델(model.safetensors)을 못 찾아 해시가 비었습니다 — 이대로 배포하면 무결성검사가 불일치로 뜹니다. 모델 경로 확인 후 재빌드하세요."
        } else {
            $shaShort = $vi.model_sha256.Substring(0, [Math]::Min(16, $vi.model_sha256.Length))
            Write-Host "  VERSION.json OK  학습일=$($vi.model_trained)  sha=$shaShort..  commit=$($vi.source_commit)" -ForegroundColor Green
        }
    }
}

# ─── Build Source-Only ────────────────────────────────────────────
function Build-SourceOnly {
    Write-Step "[소스 전용] wordcloud-project.zip 생성"

    # ZIP 내부에 wordcloud_project/ 폴더가 포함되도록 _staging/wordcloud_project/ 구조로 복사
    $StagingRoot = Join-Path $DefaultOutput "_source_staging"
    $StagingDir  = Join-Path $StagingRoot "wordcloud_project"

    Remove-Item -LiteralPath $StagingRoot -Recurse -Force -Confirm:$false -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null

    Exec-Robocopy $ProjectRoot $StagingDir -ExcludeDirs $ExcludeDirs -ExcludeFiles $ExcludeFiles

    # .clinerules/outputs/cr/ 복사 (zip 안에서는 기존 plans_routes.py 경로(.clinerules/docs/cr) 유지)
    $CRSource = Resolve-Path "$ProjectRoot/../.clinerules/outputs/cr" -ErrorAction Stop
    $CRDest = Join-Path $StagingRoot ".clinerules\docs\cr"
    New-Item -ItemType Directory -Path $CRDest -Force | Out-Null
    Copy-Item -Path "$CRSource\*" -Destination $CRDest -Recurse

    # ZIP 생성 — StagingRoot\*를 압축하여 zip 안에 wordcloud_project/ + .clinerules/ 포함
    if (Test-Path $SourceZipPath) { Remove-Item -LiteralPath $SourceZipPath -Force }
    Compress-Archive -Path "$StagingRoot\*" -DestinationPath $SourceZipPath -CompressionLevel Optimal

    $size = [math]::Round((Get-ChildItem $StagingDir -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1KB, 1)
    Write-Host "  소스 크기 : $size KB" -ForegroundColor Green
    Write-Host "  wordcloud-project.zip created (내부: wordcloud_project/)" -ForegroundColor Green

    Remove-Item -LiteralPath $StagingRoot -Recurse -Force -ErrorAction SilentlyContinue
}

# ─── Build Full Package ───────────────────────────────────────────
function Build-FullPackage {
    Write-Step "[전체 패키지] wordcloud-internal/ 생성"

    Remove-Item -LiteralPath $FullOutputDir -Recurse -Force -Confirm:$false -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path "$FullOutputDir\runtime\python" -Force | Out-Null
    New-Item -ItemType Directory -Path "$FullOutputDir\model" -Force | Out-Null
    New-Item -ItemType Directory -Path "$FullOutputDir\install_driver" -Force | Out-Null

    # 2. Python runtime
    Write-Step "  - Python runtime 복사"
    if (Test-Path $BasePythonPath) {
        $rt = "$FullOutputDir\runtime\python"
        New-Item -ItemType Directory -Path "$rt" -Force | Out-Null
        Copy-Item -LiteralPath "$BasePythonPath\python.exe" -Destination "$rt\"
        Copy-Item -LiteralPath "$BasePythonPath\pythonw.exe" -Destination "$rt\"
        Copy-Item -LiteralPath "$BasePythonPath\python310.dll" -Destination "$rt\"
        Copy-Item -LiteralPath "$BasePythonPath\python3.dll" -Destination "$rt\"
        Copy-Item -LiteralPath "$BasePythonPath\vcruntime140.dll" -Destination "$rt\"
        Copy-Item -LiteralPath "$BasePythonPath\vcruntime140_1.dll" -Destination "$rt\"
        New-Item -ItemType Directory -Path "$rt\DLLs" -Force | Out-Null
        New-Item -ItemType Directory -Path "$rt\Lib" -Force | Out-Null
        Exec-Robocopy "$BasePythonPath\DLLs" "$rt\DLLs"
        Exec-Robocopy "$BasePythonPath\Lib" "$rt\Lib" -ExcludeDirs @("site-packages", "__pycache__")
    } else {
        Write-Warning "Python not found at $BasePythonPath"
    }

    # 3. Pip packages
    Write-Step "  - pip 패키지 복사"
    if (Test-Path "$VenvPath\Lib\site-packages") {
        $rt = "$FullOutputDir\runtime\python"
        New-Item -ItemType Directory -Path "$rt\Lib\site-packages" -Force | Out-Null
        New-Item -ItemType Directory -Path "$rt\Scripts" -Force | Out-Null
        Exec-Robocopy "$VenvPath\Lib\site-packages" "$rt\Lib\site-packages"
        Exec-Robocopy "$VenvPath\Scripts" "$rt\Scripts"
    } else {
        Write-Warning "venv not found at $VenvPath"
    }

    # 4. Models
    Write-Step "  - 모델 복사"
    if ($ModelSource -and (Test-Path $ModelSource)) {
        Exec-Robocopy $ModelSource "$FullOutputDir\model"
    } else {
        Write-Warning "Model directory not found"
    }

    # 5. Source code
    Write-Step "  - 소스코드 복사"
    Exec-Robocopy $ProjectRoot "$FullOutputDir\wordcloud_project" -ExcludeDirs @(
        "venv", "__pycache__", ".git", ".sessions", "doc",
        "vendor_python_pkgs", "logs", "temp", "node_modules", "plans", "report"
    )

    # .clinerules/outputs/cr/ 복사 (dev와 동일한 zip 내부 위치, plans_routes.py 수정 불필요)
    $CRSource2 = Resolve-Path "$ProjectRoot/../.clinerules/outputs/cr" -ErrorAction Stop
    $CRDest2 = "$FullOutputDir\.clinerules\docs\cr"
    New-Item -ItemType Directory -Path $CRDest2 -Force | Out-Null
    Copy-Item -Path "$CRSource2\*" -Destination $CRDest2 -Recurse

    # 6. NVIDIA Driver
    Write-Step "  - NVIDIA Driver"
    if (-not $SkipDriver) {
        $DriverFile = "$FullOutputDir\install_driver\576.02-desktop-win10-win11-64bit-international-dch-whql.exe"
        if (-not (Test-Path $DriverFile)) {
            Write-Host "    Downloading..."
            try {
                Import-Module BitsTransfer -ErrorAction SilentlyContinue
                Start-BitsTransfer -Source $DriverUrl -Destination $DriverFile
            } catch {
                Write-Warning "Download failed"
            }
        } else {
            Write-Host "    Already downloaded"
        }
    }

    # 7. start.bat + README
    Write-Step "  - 실행 파일 생성"

    $startBat = @'
@echo off
title Wordcloud Server
chcp 65001 >nul
echo =============================
echo Starting Wordcloud Server...
echo =============================
echo.
cd /d "%~dp0"
set "PYTHONPATH=%~dp0wordcloud_project"
echo [1/2] Launching server...
start "" http://127.0.0.1:5001
cd wordcloud_project
"%~dp0runtime\python\python.exe" -m web.app
echo Server stopped.
pause
'@
    Set-Content -LiteralPath "$FullOutputDir\start.bat" -Value $startBat -Encoding ASCII

    $readme = @'
Wordcloud - Internal Network Deployment Package
================================================

[Prerequisites]
1. NVIDIA CUDA Driver
   Install the driver from install_driver/ folder first.
   Reboot is required after installation.

[How to Run]
1. Double-click start.bat
2. Browser will open http://127.0.0.1:5001 automatically
3. Press Ctrl+C to stop

[Update Source]
   Replace wordcloud_project/ folder with new wordcloud-source/ files.

[Notes]
- No Python installation required
- No internet connection required
- All data stored inside package folder
'@
    Set-Content -LiteralPath "$FullOutputDir\README.txt" -Value $readme -Encoding ASCII

    # Size summary
    Write-Host "`n  Full Package Size:" -ForegroundColor Green
    Get-ChildItem $FullOutputDir -Directory | ForEach-Object {
        $size = [math]::Round((Get-ChildItem $_.FullName -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
        Write-Host "    $($_.Name)`t$size MB"
    }

    # Also create source zip alongside full package (wordcloud_project/ + .clinerules/ 구조)
    Write-Step "  - wordcloud-project.zip 함께 생성"
    if (Test-Path $SourceZipPath) { Remove-Item -LiteralPath $SourceZipPath -Force }
    Compress-Archive -Path "$FullOutputDir\*" -DestinationPath $SourceZipPath -CompressionLevel Optimal
    Write-Host "    wordcloud-project.zip created (내부: wordcloud_project/ + .clinerules/)" -ForegroundColor Green

    # update.bat 생성
    $updateBat = @'
@echo off
title Wordcloud Updater
chcp 65001 >nul
echo ==========================================
echo   WordCloud Source Updater
echo ==========================================
echo.

set "ZIPFILE=%~dp0wordcloud-project.zip"
if not exist "%ZIPFILE%" (
    echo [ERROR] wordcloud-project.zip not found.
    echo         Copy the ZIP file here and run again.
    pause
    exit /b 1
)

echo [1/4] Removing old wordcloud_project...
if exist "%~dp0wordcloud_project" (
    rmdir /s /q "%~dp0wordcloud_project"
)

echo [2/4] Removing old .clinerules...
if exist "%~dp0.clinerules" (
    rmdir /s /q "%~dp0.clinerules"
)

echo [3/4] Extracting ZIP...
powershell -Command "Expand-Archive -Path '%ZIPFILE%' -DestinationPath '%~dp0' -Force"

echo [4/4] Done.
echo        wordcloud_project\ and .clinerules\ have been updated.
echo        Run start.bat to restart the server.
echo.
pause
'@
    Set-Content -LiteralPath "$FullOutputDir\update.bat" -Value $updateBat -Encoding ASCII
    Write-Host "    update.bat created" -ForegroundColor Green
}

# ─── Main ─────────────────────────────────────────────────────────
Write-Host "Wordcloud Deployment Builder" -ForegroundColor Yellow
Write-Host ""

# Regenerate+verify VERSION.json from the current model before any build mode.
# (ASCII comment on purpose: PS5.1 reads this file as cp949 and a multibyte char
#  at a comment line-end can swallow the next statement. Keep this line ASCII.)
Sync-Version

if ($Package) {
    Write-Host "[전체 패키지 모드] runtime + model + source" -ForegroundColor Cyan
    Build-FullPackage
} else {
    Write-Host "[소스 전용 모드] wordcloud-project.zip" -ForegroundColor Cyan
    Build-SourceOnly
}

Write-Host "`nBuild Complete" -ForegroundColor Green
