$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$dataRoot = if ($env:LEONIDA_DATA_DIR) { $env:LEONIDA_DATA_DIR } else { Join-Path $projectRoot '.local' }
$statePath = Join-Path $dataRoot 'run.json'
if (-not (Test-Path -LiteralPath $statePath)) { Write-Host 'Nenhuma instancia registrada.'; exit 0 }
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
if ($state.token -notmatch '^[a-f0-9]{32}$') { throw 'Registro de instancia invalido.' }
New-Item -ItemType File -Path (Join-Path $dataRoot "stop-$($state.token)") -Force | Out-Null
Write-Host 'Encerramento solicitado. O servico aguarda e encerra as tarefas filhas.'
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if (-not (Test-Path -LiteralPath $statePath)) { Write-Host 'Leonida Clip Studio encerrado.'; exit 0 }
    Start-Sleep -Milliseconds 500
}
Write-Error 'O servico nao confirmou o encerramento em 20 segundos. Verifique a janela da aplicacao. Nenhum processo alheio foi encerrado.'
