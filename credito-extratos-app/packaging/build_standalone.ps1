# ============================================================================
# build_standalone.ps1
# ----------------------------------------------------------------------------
# Builds a self-contained ZIP for analysts who don't have Python installed.
#
# Output: dist\Analise_Extratos_v<versao>.zip
#
# The ZIP unpacks to:
#   Analise_Extratos_v<versao>\
#     Executar.bat   <-- analyst double-clicks this
#     LEIA-ME.txt
#     SECURITY.md
#     python\        <-- embeddable Python + all deps pre-installed
#     app\           <-- app.py, src\, config\, .streamlit\
#
# Usage:
#   .\packaging\build_standalone.ps1
#   .\packaging\build_standalone.ps1 -PythonVersion 3.11.9
#   .\packaging\build_standalone.ps1 -SkipDownload    # reuse cached python-embed
# ============================================================================

[CmdletBinding()]
param(
    [string]$PythonVersion = "3.11.9",
    [string]$ProjectRoot,
    [switch]$SkipDownload
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # speeds up Invoke-WebRequest

# Resolve script + project roots (avoid $ScriptRoot in default params -
# it's empty when the script is launched with -File on some shells).
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $ScriptRoot "..")).Path
}

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Read-AppVersion {
    $initPath = Join-Path $ProjectRoot "src\__init__.py"
    $line = Select-String -Path $initPath -Pattern '^__version__\s*=' | Select-Object -First 1
    if (-not $line) { throw "Nao encontrei __version__ em $initPath" }
    if ($line.Line -match '"([^"]+)"') { return $Matches[1] }
    throw "Nao consegui extrair __version__ de $initPath"
}

$AppVersion = Read-AppVersion
$PackageName = "Analise_Extratos_v$AppVersion"

$DistDir = Join-Path $ProjectRoot "dist"
$BuildDir = Join-Path $DistDir $PackageName
$CacheDir = Join-Path $DistDir "_cache"

$PythonEmbedZip = "python-$PythonVersion-embed-amd64.zip"
$PythonEmbedUrl = "https://www.python.org/ftp/python/$PythonVersion/$PythonEmbedZip"
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"

Write-Step "Versao do app: $AppVersion"
Write-Step "Pasta de saida: $BuildDir"

# ----------------------------------------------------------------------------
# 1. Clean and prepare directories
# ----------------------------------------------------------------------------
Write-Step "Limpando build anterior"
if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }
New-Item -ItemType Directory -Path $BuildDir | Out-Null
New-Item -ItemType Directory -Path $CacheDir -Force | Out-Null

$PythonDir = Join-Path $BuildDir "python"
$AppDir = Join-Path $BuildDir "app"
New-Item -ItemType Directory -Path $PythonDir | Out-Null
New-Item -ItemType Directory -Path $AppDir | Out-Null

# ----------------------------------------------------------------------------
# 2. Download (or reuse) Python embeddable
# ----------------------------------------------------------------------------
$CachedPython = Join-Path $CacheDir $PythonEmbedZip
$CachedGetPip = Join-Path $CacheDir "get-pip.py"

if (-not $SkipDownload -or -not (Test-Path $CachedPython)) {
    Write-Step "Baixando Python $PythonVersion embeddable"
    Invoke-WebRequest -Uri $PythonEmbedUrl -OutFile $CachedPython
}
if (-not $SkipDownload -or -not (Test-Path $CachedGetPip)) {
    Write-Step "Baixando get-pip.py"
    Invoke-WebRequest -Uri $GetPipUrl -OutFile $CachedGetPip
}

Write-Step "Extraindo Python embeddable para python\"
Expand-Archive -Path $CachedPython -DestinationPath $PythonDir -Force

# ----------------------------------------------------------------------------
# 3. Enable `import site` (required for pip / site-packages)
# ----------------------------------------------------------------------------
Write-Step "Habilitando 'import site' no python embeddable"
$PthFile = Get-ChildItem -Path $PythonDir -Filter "python*._pth" | Select-Object -First 1
if (-not $PthFile) { throw "Nao encontrei python*._pth em $PythonDir" }
$PthLines = Get-Content $PthFile.FullName | ForEach-Object {
    $_ -replace '^#\s*import\s+site', 'import site'
}
# IMPORTANT: write ASCII without BOM. Set-Content -Encoding utf8 on
# Windows PowerShell 5.1 emits UTF-8 WITH BOM, which corrupts python._pth
# (the BOM becomes part of the first sys.path entry, breaking 'encodings').
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($PthFile.FullName, ($PthLines -join "`r`n") + "`r`n", $Utf8NoBom)

# ----------------------------------------------------------------------------
# 4. Install pip into the embeddable
# ----------------------------------------------------------------------------
$PythonExe = Join-Path $PythonDir "python.exe"
Write-Step "Instalando pip no python embeddable"
& $PythonExe $CachedGetPip --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar pip" }

# ----------------------------------------------------------------------------
# 5. Install runtime dependencies into the embeddable
# ----------------------------------------------------------------------------
$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"
Write-Step "Instalando dependencias do app no python embeddable"
& $PythonExe -m pip install --no-warn-script-location -r $RequirementsFile
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar dependencias" }

# ----------------------------------------------------------------------------
# 6. Strip caches and unused files to shrink the package
# ----------------------------------------------------------------------------
Write-Step "Limpando caches e arquivos de teste"
Get-ChildItem -Path $PythonDir -Filter "__pycache__" -Recurse -Directory `
    | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $PythonDir -Filter "*.dist-info" -Recurse -Directory `
    | ForEach-Object { Remove-Item (Join-Path $_.FullName "RECORD") -Force -ErrorAction SilentlyContinue }
# Optional shrink: drop pip cache, test suites of large libs
$shrinkTargets = @(
    "Lib\site-packages\pip\_vendor\__pycache__",
    "Lib\site-packages\pandas\tests",
    "Lib\site-packages\numpy\tests",
    "Lib\site-packages\openpyxl\tests"
)
foreach ($t in $shrinkTargets) {
    $full = Join-Path $PythonDir $t
    if (Test-Path $full) { Remove-Item $full -Recurse -Force -ErrorAction SilentlyContinue }
}

# ----------------------------------------------------------------------------
# 7. Copy app code (excluding dev junk)
# ----------------------------------------------------------------------------
Write-Step "Copiando codigo do app"
$RobocopyExclude = @(
    "/XD", "__pycache__", ".pytest_cache", "samples", "tests", ".git",
    "dist", "packaging", ".github", "_cache",
    "/XF", "*.pyc", "*.pyo", "*.log"
)
$RobocopyArgs = @(
    $ProjectRoot, $AppDir,
    "app.py",
    "requirements.txt",
    "requirements-lock.txt",
    "pyproject.toml"
)
robocopy @RobocopyArgs /NFL /NDL /NJH /NJS /NP | Out-Null

# Copy directories explicitly (robocopy needs separate calls for nested dirs)
$dirsToCopy = @("src", "config", ".streamlit")
foreach ($dir in $dirsToCopy) {
    $src = Join-Path $ProjectRoot $dir
    $dst = Join-Path $AppDir $dir
    if (-not (Test-Path $src)) { continue }
    robocopy $src $dst /MIR `
        /XD "__pycache__" ".pytest_cache" `
        /XF "*.pyc" "*.pyo" "*.log" `
        /NFL /NDL /NJH /NJS /NP | Out-Null
}

# ----------------------------------------------------------------------------
# 8. Copy launcher + docs
# ----------------------------------------------------------------------------
Write-Step "Copiando launcher e documentos"
Copy-Item (Join-Path $ScriptRoot "launcher.bat") (Join-Path $BuildDir "Executar.bat") -Force
Copy-Item (Join-Path $ScriptRoot "LEIA-ME.txt") $BuildDir -Force

$SecurityMd = Join-Path $ProjectRoot "SECURITY.md"
if (Test-Path $SecurityMd) {
    Copy-Item $SecurityMd $BuildDir -Force
}

# Drop a version stamp the launcher can read (UTF-8 no BOM)
$VersionText = "$AppVersion`r`nBuilt: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $BuildDir "VERSION.txt"), $VersionText, $Utf8NoBom)

# ----------------------------------------------------------------------------
# 9. Zip
# ----------------------------------------------------------------------------
$ZipPath = Join-Path $DistDir "$PackageName.zip"
Write-Step "Gerando ZIP: $ZipPath"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

# Use .NET ZipFile (single-pass, robust against antivirus locks on
# python311.zip while Compress-Archive walks files twice).
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.GC]::Collect()
[System.GC]::WaitForPendingFinalizers()
Start-Sleep -Seconds 1
try {
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $BuildDir,
        $ZipPath,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $true   # includeBaseDirectory -> ZIP root holds the build folder
    )
} catch {
    Write-Warning "ZipFile.CreateFromDirectory falhou: $($_.Exception.Message)"
    Write-Warning "Tentando novamente apos 3s (antivirus pode estar varrendo)..."
    Start-Sleep -Seconds 3
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $BuildDir,
        $ZipPath,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $true
    )
}

# ----------------------------------------------------------------------------
# 10. Summary
# ----------------------------------------------------------------------------
$ZipSize = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
$BuildSize = [math]::Round(((Get-ChildItem $BuildDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB), 1)

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " BUILD CONCLUIDO" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host " ZIP    : $ZipPath ($ZipSize MB)"
Write-Host " Pasta  : $BuildDir ($BuildSize MB descompactado)"
Write-Host ""
Write-Host " Proximos passos:"
Write-Host "   1. Teste em pasta limpa: extraia o ZIP e clique em Executar.bat"
Write-Host "   2. Compartilhe o ZIP via OneDrive/SharePoint corporativo"
Write-Host "   3. Calcule o SHA256 se o time de TI pedir whitelist:"
Write-Host "        Get-FileHash '$ZipPath' -Algorithm SHA256"
Write-Host "============================================================" -ForegroundColor Green
