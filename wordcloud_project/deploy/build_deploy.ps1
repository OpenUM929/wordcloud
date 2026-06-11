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

$ExcludeDirs = @("venv", "__pycache__", ".git", ".sessions", "plans", "doc",
                 "vendor_python_pkgs", "logs", "temp", "node_modules", "deploy",
                 ".pytest_cache", "inputs", "scripts", ".opencode", ".clinerules", "failed")
$ExcludeFiles = @("*.pyc", ".gitignore", "CACHEDIR.TAG", "README.md", "mermaid.min.js")

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

# ─── Build Source-Only ────────────────────────────────────────────
function Build-SourceOnly {
    Write-Step "[소스 전용] wordcloud-project.zip 생성"

    # ZIP 내부에 wordcloud_project/ 폴더가 포함되도록 _staging/wordcloud_project/ 구조로 복사
    $StagingRoot = Join-Path $DefaultOutput "_source_staging"
    $StagingDir  = Join-Path $StagingRoot "wordcloud_project"

    Remove-Item -LiteralPath $StagingRoot -Recurse -Force -Confirm:$false -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null

    Exec-Robocopy $ProjectRoot $StagingDir -ExcludeDirs $ExcludeDirs -ExcludeFiles $ExcludeFiles

    # ZIP 생성 — StagingDir 자체를 압축하여 zip 안에 wordcloud_project/ 폴더 포함
    if (Test-Path $SourceZipPath) { Remove-Item -LiteralPath $SourceZipPath -Force }
    Compress-Archive -Path $StagingDir -DestinationPath $SourceZipPath -CompressionLevel Optimal

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
        "venv", "__pycache__", ".git", ".sessions", "plans", "doc",
        "vendor_python_pkgs", "logs", "temp", "node_modules"
    )

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

    # Also create source zip alongside full package (wordcloud_project/ 폴더 포함 구조)
    Write-Step "  - wordcloud-project.zip 함께 생성"
    if (Test-Path $SourceZipPath) { Remove-Item -LiteralPath $SourceZipPath -Force }
    Compress-Archive -Path "$FullOutputDir\wordcloud_project" -DestinationPath $SourceZipPath -CompressionLevel Optimal
    Write-Host "    wordcloud-project.zip created (내부: wordcloud_project/)" -ForegroundColor Green

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
    echo [ERROR] wordcloud-project.zip 를 찾을 수 없습니다.
    echo         이 폴더에 ZIP 파일을 복사한 뒤 다시 실행하세요.
    pause
    exit /b 1
)

echo [1/3] 기존 wordcloud_project 폴더 삭제 중...
if exist "%~dp0wordcloud_project" (
    rmdir /s /q "%~dp0wordcloud_project"
)

echo [2/3] ZIP 압축 해제 중...
powershell -Command "Expand-Archive -Path '%ZIPFILE%' -DestinationPath '%~dp0' -Force"

echo [3/3] 완료!
echo        wordcloud_project\ 가 최신 버전으로 교체되었습니다.
echo        서버를 재시작하려면 start.bat 을 실행하세요.
echo.
pause
'@
    Set-Content -LiteralPath "$FullOutputDir\update.bat" -Value $updateBat -Encoding ASCII
    Write-Host "    update.bat created" -ForegroundColor Green
}

# ─── Main ─────────────────────────────────────────────────────────
Write-Host "Wordcloud Deployment Builder" -ForegroundColor Yellow
Write-Host ""

if ($Package) {
    Write-Host "[전체 패키지 모드] runtime + model + source" -ForegroundColor Cyan
    Build-FullPackage
} else {
    Write-Host "[소스 전용 모드] wordcloud-project.zip" -ForegroundColor Cyan
    Build-SourceOnly
}

Write-Host "`nBuild Complete" -ForegroundColor Green
