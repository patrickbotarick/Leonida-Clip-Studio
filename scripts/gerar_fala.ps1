param([Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $available = @($voice.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo })
    $portuguese = $available | Where-Object { $_.Culture.Name -eq 'pt-BR' } | Select-Object -First 1
    if (-not $portuguese) { throw 'Voz de sintese pt-BR nao instalada. Este teste opcional requer uma voz ja disponivel; nenhuma voz sera baixada.' }
    $voice.SelectVoice($portuguese.Name)
    $voice.Rate = -1
    $voice.SetOutputToWaveFile($OutputPath)
    $voice.Speak('Este e um teste de transcricao local. O video permanece neste computador. Estamos verificando as faixas de audio.')
} finally { $voice.Dispose() }
