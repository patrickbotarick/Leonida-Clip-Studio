# Diagnóstico do ambiente

Executado em **18/11/2026**, no diretório raiz do projeto, sem instalar ferramentas globalmente.

| Item | Resultado observado |
|---|---|
| Windows | Kernel NT 10.0.26300; registro identifica Windows 10 Pro, DisplayVersion 26H2, build 26300 |
| PowerShell | 7.6.9; scripts de usuário também executados no Windows PowerShell (`powershell.exe`) |
| CPU | Intel Core i5-12400F de 12ª geração |
| Processadores lógicos | 12; contagem de núcleos físicos não obtida via CIM |
| RAM total | 34.189.082.624 bytes, aproximadamente 31,84 GiB / 32 GB instalados |
| RAM livre no diagnóstico | Aproximadamente 16,08 GiB; valor variável |
| GPU | NVIDIA GeForce RTX 3050, WDDM |
| VRAM | 6.144 MiB; cerca de 3.469 MiB já em uso no primeiro diagnóstico |
| Driver NVIDIA | 617.42 |
| CUDA anunciado pelo driver | CUDA UMD 13.4 (`nvidia-smi`); não prova existência das bibliotecas requeridas por CTranslate2 |
| Python no PATH | Aliases WindowsApps `python`/`py` encontrados, mas não executáveis neste contexto |
| Python utilizado | 3.12.14, runtime local existente no cache Codex; `.venv` criada no projeto |
| Outro Python encontrado | 3.13.13 embutido no Blender; não foi modificado nem utilizado como base |
| Node.js | 24.11.1 |
| npm | 11.6.2 |
| Git | 2.54.0.windows.1; repositório local inicializado, sem remoto/publicação |
| FFmpeg / FFprobe no PATH inicial | Ausentes |
| FFmpeg / FFprobe preparados | 9.0.2 essentials x64, portáteis em `.tools/ffmpeg` |

`Get-CimInstance` para SO/CPU/GPU foi bloqueado pelo ambiente de execução. Usaram-se registro, APIs do Node (`os.cpus`, `os.totalmem`), PowerShell e `nvidia-smi`. O nome de marketing do Windows acima é o texto do registro; não foi reinterpretado a partir do número de build.

## Hardware e configuração recomendada

O comando `ffmpeg -hwaccels` lista suporte compilado a CUDA, VAAPI, DXVA2, QSV, D3D11VA, D3D12VA e AMF. Essa listagem sozinha não valida todos esses recursos no computador.

Foi executado um teste real de **codificação H.264 por `h264_nvenc`**, usando uma fonte sintética 640×360/30 FPS por um segundo e saída nula: **exit code 0**. O primeiro ensaio em 128×128 foi rejeitado pelo encoder por dimensão inferior ao mínimo; a resolução foi corrigida para o teste válido. Nenhum arquivo de usuário foi utilizado.

No diagnóstico inicial, Faster Whisper/CTranslate2 ainda não haviam sido instalados/validados. Na continuação da Fase 1B, Faster Whisper 1.2.1/CTranslate2 4.9.0 foram instalados somente na `.venv`, e o modelo Tiny foi validado em CPU/int8 com fala sintética pt-BR. O perfil econômico usa duas threads; o limite configurável é 1–4 threads. A VRAM já ocupada reforça a escolha conservadora de CPU.

A detecção CTranslate2 encontrou uma GPU, mas a tentativa real de inferência CUDA falhou com `Library cublas64_12.dll is not found or cannot be loaded`. O diagnóstico verifica também `cudnn64_9.dll`; a opção GPU fica desabilitada quando essas bibliotecas não carregam. Nenhum driver, CUDA Toolkit ou cuDNN global foi instalado. NVENC funcional não implica Faster Whisper/CUDA funcional. Consulte [PHASE_1B.md](PHASE_1B.md).

## Origem e integridade das ferramentas

FFmpeg portátil obtido do distribuidor Windows indicado pela página oficial de [downloads FFmpeg](https://ffmpeg.org/download.html), em [Gyan builds](https://www.gyan.dev/ffmpeg/builds/). SHA256 do ZIP comparado ao arquivo publicado pelo distribuidor:

```text
60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba
```

Dependências Python foram instaladas somente em `.venv`; frontend somente em `frontend/node_modules`. Nenhum driver, PATH global, Python global, npm global ou serviço de sistema foi instalado/alterado.

O sandbox da sessão bloqueia sockets locais usados pelo asyncio. Testes integrados e servidor real foram executados com autorização de execução fora do sandbox, sempre com bind em loopback. Isso é uma característica do ambiente de desenvolvimento, não uma exigência de execução administrativa do produto. Os scripts não solicitam elevação de administrador.
