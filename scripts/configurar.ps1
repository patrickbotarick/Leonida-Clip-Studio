param([string]$PythonExe = '', [switch]$DownloadFFmpeg)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
function Assert-Exit([string]$step) { if ($LASTEXITCODE -ne 0) { throw "$step falhou (codigo $LASTEXITCODE)." } }
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Use Windows 10/11 x64. Consulte docs/INSTALL_WINDOWS.md.' }
if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw 'Instale Node.js 24 LTS x64: https://nodejs.org/en/download . Reabra o terminal. Consulte docs/INSTALL_WINDOWS.md.'
}
& node -e 'let [a,b]=process.versions.node.split(''.'').map(Number);process.exit((a===24||(a===22&&b>=12))&&process.arch===''x64''?0:1)'
Assert-Exit 'Node.js x64 (24 LTS ou 22.12+)'
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    $candidates = @()
    if ($PythonExe) { $candidates += ,@($PythonExe) }
    $candidates += ,@('py', '-3.12')
    $candidates += ,@('python')
    $candidates += ,@('python3.12')
    $workingPython = $null
    foreach ($candidate in $candidates) {
        try {
            $executable = $candidate[0]
            $arguments = @($candidate | Select-Object -Skip 1)
            & $executable @arguments -c 'import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize(''P'')==8' 2>$null
            if ($LASTEXITCODE -eq 0) { $workingPython = $candidate; break }
        } catch { }
    }
    if (-not $workingPython) { throw 'Python 3.12 x64 ausente. Instale em https://www.python.org/downloads/windows/ ou informe -PythonExe C:\caminho\python.exe. Veja docs/INSTALL_WINDOWS.md. Nenhuma instalacao global foi feita.' }
    $executable = $workingPython[0]
    $arguments = @($workingPython | Select-Object -Skip 1)
    & $executable @arguments -m venv .venv
    Assert-Exit 'Criacao do ambiente Python'
}
& '.venv/Scripts/python.exe' -c 'import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize(''P'')==8, ''Recrie .venv usando Python 3.12 x64; nao copie de outro PC.'''
Assert-Exit 'Python 3.12 x64'
& '.venv/Scripts/python.exe' -m pip install --require-virtualenv --only-binary=:all: -r backend/requirements-lock.txt
Assert-Exit 'Dependencias Python'
if ($DownloadFFmpeg -and -not ((Get-ChildItem -LiteralPath '.tools/ffmpeg' -Recurse -Filter 'ffmpeg.exe' -ErrorAction SilentlyContinue) -and (Get-ChildItem -LiteralPath '.tools/ffmpeg' -Recurse -Filter 'ffprobe.exe' -ErrorAction SilentlyContinue))) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    New-Item -ItemType Directory -Force '.tools' | Out-Null
    $toolsRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '.tools'))
    $stage = Join-Path $toolsRoot ('.download-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stage | Out-Null
    $archive = Join-Path $stage 'ffmpeg.zip'
    $url = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
    Write-Host 'Baixando FFmpeg portatil apenas para .tools...'
    try {
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $archive
    $checksum = (Invoke-WebRequest -UseBasicParsing -Uri "$url.sha256").Content
    if ($checksum -is [byte[]]) { $checksum = [Text.Encoding]::UTF8.GetString($checksum) }
    $expected = ([regex]::Match([string]$checksum, '[a-fA-F0-9]{64}')).Value
    if (-not $expected -or (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected) { throw 'Checksum FFmpeg invalido. Arquivo nao extraido.' }
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $stage 'unpacked')
    $ffmpeg = Get-ChildItem -LiteralPath (Join-Path $stage 'unpacked') -Recurse -Filter 'ffmpeg.exe' | Select-Object -First 1
    if (-not $ffmpeg -or -not (Test-Path -LiteralPath (Join-Path $ffmpeg.Directory.FullName 'ffprobe.exe'))) { throw 'Pacote FFmpeg incompleto.' }
    $package = [IO.Path]::GetFullPath($ffmpeg.Directory.Parent.FullName)
    if (-not $package.StartsWith($stage + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Pacote fora da pasta de preparacao.' }
    & $ffmpeg.FullName -version | Out-Null
    Assert-Exit 'Executavel FFmpeg'
    New-Item -ItemType Directory -Force '.tools/ffmpeg' | Out-Null
    $target = Join-Path $toolsRoot ('ffmpeg/' + $ffmpeg.Directory.Parent.Name + '-' + [guid]::NewGuid().ToString('N'))
    if (-not ([IO.Path]::GetFullPath($target)).StartsWith($toolsRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Destino FFmpeg invalido.' }
    Move-Item -LiteralPath $package -Destination $target
    Write-Host "SHA256 validado: $expected"
    } finally {
        $resolvedStage = [IO.Path]::GetFullPath($stage)
        if ($resolvedStage.StartsWith($toolsRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolvedStage -Leaf) -match '^\.download-[a-f0-9]{32}$') {
            Remove-Item -LiteralPath $resolvedStage -Recurse -Force
        }
    }
}
& npm.cmd ci --prefix frontend --cache .local/npm-cache
Assert-Exit 'Dependencias frontend'
& npm.cmd run build --prefix frontend
Assert-Exit 'Compilacao frontend'
& '.venv/Scripts/python.exe' scripts/verificar.py
Assert-Exit 'Verificacao de dependencias'
Write-Host 'Configuracao concluida. Abra Abrir Leonida Clip Studio.bat.' -ForegroundColor Green
