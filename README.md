# Leonida Clip Studio

Ferramenta local da **BTRK Studio**, inicialmente para o canal Código Leonida. Versão **0.1.0 — piloto consolidado até a Fase 1F**.

O projeto executa importação por referência, reprodução, identificação/seleção/escuta de faixas, transcrição local com Faster Whisper, análise sonora e sugestões classificadas com evidências. A decupagem visual permite ajustar e revisar cortes com waveform real. Exporta cortes aprovados em MP4, relatórios/legendas e XML FCP7 para revisão no Premiere.

## Instalar no PC de casa

**Comece pelo [guia de instalação Windows do zero](docs/INSTALL_WINDOWS.md).** Ele inclui links oficiais e soluções para dependências ausentes.

1. Instale **Python 3.12 x64**, **Node.js 24 LTS x64** (com npm) e **Microsoft Visual C++ Redistributable x64**.
2. Baixe **Code → Download ZIP** deste repositório e extraia para uma pasta local, como `C:\LeonidaClipStudio`.
3. Execute **Configurar Leonida Clip Studio.bat** e aguarde a mensagem de conclusão. Ele recria as dependências locais e baixa/verifica FFmpeg/FFprobe.
4. Execute **Abrir Leonida Clip Studio.bat**. Para diagnóstico, use **Verificar Leonida Clip Studio.bat**.

Codex, VS Code, Git, Premiere, GPU/CUDA e chaves de IA **não são necessários** para o fluxo básico. A primeira configuração exige internet; baixar modelo Whisper é uma etapa opcional e explícita na interface. Nunca copie `.venv`/`node_modules` de outro PC.

## Iniciar após a configuração

1. Dê dois cliques em **`Abrir Leonida Clip Studio.bat`**.
2. O navegador padrão abrirá em **http://127.0.0.1:8765**. Mantenha a janela do serviço aberta.
3. Clique em **Novo projeto**, selecione o vídeo no Windows ou cole seu caminho absoluto e clique em **Criar projeto**.
4. Em **Áudio**, escute cada faixa pelo botão de fones. A prévia tem até 30 segundos e começa na posição atual do vídeo. Marque as faixas desejadas; a seleção fica salva, sem presumir qual contém a voz.
5. Em **Texto**, importe SRT ou CSV e clique em um trecho para ir ao instante correspondente. Uma nova importação substitui a transcrição anterior; exporte o texto antes de substituir se quiser guardar uma cópia.
6. Para encerrar, use **Ctrl+C** na janela do serviço ou **`Encerrar Leonida Clip Studio.bat`**. Fechar apenas a aba do navegador mantém o serviço aberto.

As dependências do aplicativo ficam na pasta do projeto; Python/Node/runtime Microsoft são os pré-requisitos do Windows. A aplicação funciona offline após a configuração. Não é necessário iniciar um servidor Vite separado: FastAPI serve a interface compilada e a API na mesma origem.

Para transcrição automática, abra **Texto → Transcrição local**, escolha perfil/modelo, idioma e limite de threads. Tiny já está instalado neste computador. Em outra instalação, o botão de download exige autorização explícita para obter os pesos públicos do Hugging Face; nenhuma mídia é enviada. Selecione as faixas em **Áudio** antes de transcrever. Duas ou mais faixas são misturadas com normalização. A opção de até 30 s permite testar antes de processar a gravação completa. Se já existir texto, confirme sua substituição; falha/cancelamento preservam a versão anterior. Guia completo: [Fase 1B](docs/PHASE_1B.md).

Para encontrar momentos, abra **Análise → Configurar análise**. O padrão é **Heurísticas locais · offline**, sem API. Escolha tipo de conteúdo, finalidade, durações e margens de contexto; ative medidas sonoras nas faixas selecionadas ou analise somente a transcrição. O resultado mostra sugestões com evidências, inferências e ganchos separados. Filtros, prévia do intervalo e relatório JSON estão disponíveis. OpenAI/Ollama são opcionais e exigem autorização de envio de texto por execução. [Guia da Fase 1C](docs/PHASE_1C.md).

Para revisar, use **Decupagem**, abaixo do player: selecione uma região, ajuste IN/OUT ou arraste suas bordas e clique em **Salvar ajuste**. Use os botões de status para aprovar/rejeitar, ou crie, divida e una cortes. Escolha uma faixa e clique em **Gerar waveform**; o envelope PCM fica em cache. Ajustes não salvos bloqueiam a saída e alterações das fontes. [Guia da Fase 1D](docs/PHASE_1D.md).

Para entregar os cortes, clique em **Exportar** no editor. Selecione os aprovados, formatos e faixas, confira a prévia e exporte para uma pasta nova por lote. Há recodificação H.264/AAC, cópia rápida aproximada com confirmação, XML FCP7 e CSV/JSON/TXT/SRT. O padrão salva em `.local/exports`; o original permanece intacto. [Guia da Fase 1E](docs/PHASE_1E.md).

## Disponível nesta entrega

- Interface em português com identidade Leonida/BTRK, página de projetos, monitor de origem, painel de áudio/texto/mídia, régua de navegação e diagnóstico.
- MP4, MKV, MOV e WEBM importados via FFprobe, com duração, resolução, FPS racional, codecs, tamanho e metadados de cada faixa de áudio.
- Caminho absoluto normalizado para o original. Sem upload, cópia automática ou alteração do vídeo.
- Vídeo servido por intervalos HTTP (`Range`, resposta 206), permitindo seek sem carregar a mídia inteira em memória.
- Player com reprodução/pausa, ±5 s, velocidade, volume, navegação por segundos ou HH:MM:SS e legenda sincronizada.
- Faixas identificadas por título/handler quando disponível, índice real do stream, canais e frequência. Seleção múltipla persistente e escuta independente por prévias AAC.
- Uma tarefa FFmpeg por vez, duas threads por prévia, fila limitada, progresso obtido do FFmpeg, cancelamento e cache por mídia/faixa/posição.
- Projetos em SQLite, reabertura e relocalização de originais movidos. Arquivo alterado é detectado antes da reprodução/extração.
- Importação SRT e CSV (UTF-8/BOM ou Windows-1252), com validação de intervalos e texto, limite de 10 MiB e 100 mil trechos.
- Faster Whisper local, modelos Tiny/Base/Small, perfis econômico/equilibrado/alta qualidade, CPU int8, detecção automática/português/inglês, limite de 1–4 threads e teste de trecho.
- Vídeos longos transcritos em blocos de 300 s com 5 s de contexto em cada lado; WAV temporário mono 16 kHz, timestamps globais, progresso medido, processo cancelável e cache por fonte/configuração/modelo.
- Histórico de tarefas em SQLite, identificação de interrupção ao reabrir e revisão transacional do projeto. Texto novo só é aplicado após sucesso; faixas/texto/mídia ficam protegidos contra edição durante a transcrição.
- Exportação da transcrição em SRT, CSV, TXT e JSON por download no navegador.
- Backend restrito a loopback, proteção de origem/Host e cabeçalho para mutações, sem CORS aberto ou envio automático para provedores externos.
- Análise sonora real por faixa: energia RMS/picos, variações e silêncio, com curvas agregadas. Processamento PCM em fluxo, cache e cancelamento.
- Heurísticas locais de texto/áudio, perfis de conteúdo, sugestões com timestamps globais, categorias, confiança estimada, score editorial de 0–100 e deduplicação.
- Provedores OpenAI (Responses/JSON Schema) e Ollama local, com consentimento, blocos sobrepostos, validação de IDs/tempos e chave apenas em memória. Seus contratos HTTP foram testados; inferência ao vivo nesses provedores ainda precisa de validação com uma configuração autorizada.

- Exportações aprovadas individuais/em lote: MP4 recodificado ou rápido, faixas/canais separados, prévia vinculada à revisão, destino próprio, progresso/cancelamento, publicação em pasta nova e histórico persistido.
- XML xmeml/FCP7 com timebase racional, IN/OUT de origem, sequência consolidada/original, canais selecionados e marcadores; JSON/CSV/TXT e SRT individual/da sequência, com manifesto de metadados medidos. Validação nativa Premiere pendente.

## Limitações importantes

- **Importação e reprodução são capacidades diferentes.** FFprobe lê os quatro contêineres, mas a reprodução depende dos codecs do navegador. O cenário validado visualmente é MP4 H.264/AAC. Ainda não há proxy/transcodificação automática para mídias incompatíveis.
- O player usa a faixa padrão escolhida pelo navegador. A seleção múltipla salva é para processamento futuro; ela não troca o áudio do player. A escuta individual acontece em um player separado de até 30 s.
- Arrastar um vídeo no navegador não revela seu caminho absoluto. O gesto abre a importação; use o seletor nativo ou cole o caminho. A aplicação não copia o vídeo para contornar essa restrição.
- CSV aceita `Start,End,Text`, `Start Time,End Time,Transcript`, `Start Timecode,End Timecode,Text` ou equivalentes `Início,Fim,Texto`, separados por vírgula, ponto e vírgula ou tabulação. Exportações Premiere variam por versão/idioma; formatos não reconhecidos devem ser convertidos ou exportados como SRT.
- Timestamps numéricos representam segundos; `HH:MM:SS,mmm` e `HH:MM:SS:FF` são aceitos. Timecode com frames usa o FPS da mídia; **drop-frame `;` e offset de timecode de sequência ainda não são suportados**. Os tempos precisam estar relativos ao início do arquivo original.
- MP4 recodificado foi validado em CFR com quadros/amostras reais. Cópia rápida é aproximada e pode incluir o quadro-chave anterior. XML exige CFR confirmado, usa timecode zero/NDF e ainda precisa de importação real no Premiere; VFR/offsets exigem validação própria.
- Sem análise visual. Áudio isolado gera apenas sugestões genéricas de evento sonoro, com confiança baixa; não comprova gritos, sustos ou jogadas. Scores não preveem viralização.
- CPU/Tiny foi validado de verdade. GPU foi detectada, mas a inferência CUDA falhou por ausência de `cublas64_12.dll`; a interface desabilita GPU quando cuBLAS/cuDNN não podem ser carregadas. Nenhum driver ou biblioteca de sistema foi instalado.
- Modelos Base/Small e seus perfis estão disponíveis para download/configuração, mas o benchmark desta máquina cobriu Tiny. Transcrição automática pode conter erros e precisa de revisão. Não há diarização ou tradução.
- O teste de importação XML no Premiere foi interrompido por Escape antes da importação. O XML foi validado estruturalmente; não há promessa de compatibilidade completa. Não há MP4 de sequência concatenada, legendas embutidas ou reenquadramento vertical automático.
- Os testes sintéticos de mais de 2 h validam importação, waveform, cancelamento e exportação perto do final; não equivalem a um benchmark de gravação OBS pesada.
- Prévias ficam em `.local/previews`, transcrições em cache em `.local/transcription/cache` e modelos em `.local/models`. Ainda não há cota/limpeza pela interface. Caches descartáveis podem ser apagados manualmente **com o serviço encerrado**. Não apague o banco de projetos. Modelos são reutilizados offline.
- A instalação está destinada ao uso local por um usuário. Não exponha a porta a redes externas.

## Configurar em outro computador Windows

Requisitos: Windows 10/11 x64, Python **3.12 x64**, Node.js **24 LTS x64** (ou 22.12+) com npm e **Microsoft Visual C++ Redistributable x64**. Git é opcional para executar. Baixe ferramentas globais manualmente se necessário; os scripts não instalam drivers nem ferramentas de sistema.

Com Python e Node disponíveis, execute **`Configurar Leonida Clip Studio.bat`**. O script cria `.venv`, instala pacotes nela, baixa FFmpeg/FFprobe portáteis para `.tools`, verifica SHA256, instala `frontend/node_modules` e compila a interface. O download inicial exige internet.

Também pode executar pelo PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\configurar.ps1 -DownloadFFmpeg
```

Se o Python não estiver no PATH:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\configurar.ps1 -PythonExe 'C:\Python312\python.exe' -DownloadFFmpeg
```

`ExecutionPolicy Bypass` aplica-se somente ao processo desse comando; não altera a política global. `.venv`, `.tools` e `node_modules` não são portáveis/versionados: recrie-os na outra máquina. A pasta de dados não deve ser aberta simultaneamente por duas instâncias; o launcher utiliza bloqueio de arquivo.

## Configurações locais

As variáveis de `.env.example` são referências; o aplicativo **não carrega `.env` automaticamente**. Defina variáveis no ambiente antes de iniciar, por exemplo:

```powershell
$env:FFMPEG_PATH = 'C:\Ferramentas\ffmpeg\bin\ffmpeg.exe'
$env:FFPROBE_PATH = 'C:\Ferramentas\ffmpeg\bin\ffprobe.exe'
$env:LEONIDA_DATA_DIR = 'D:\Leonida\dados'
.\.venv\Scripts\python.exe .\scripts\launch.py
```

A resolução de FFmpeg/FFprobe prioriza caminho explícito, PATH e, por último, `.tools`. O diretório de dados padrão é `.local`, contendo SQLite e caches. No modo local, transcrições não saem do computador e nenhuma chave é necessária. Para OpenAI, informe a chave apenas no painel por execução; ela não é salva em projeto, cache, log ou relatório. Selecionar um provedor opcional não envia texto sem consentimento e ação explícita de análise.

Ao relocalizar, tamanho, mtime e duração iguais preservam o texto. Uma mídia diferente limpa transcrição, cortes e faixas selecionadas para evitar referências inválidas. Essa identificação usa metadados, não hash completo do vídeo, para não ler arquivos extensos à toa; faça backup de `.local/projects.sqlite3` com o serviço encerrado.

## Desenvolvimento e testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd run build --prefix frontend
.\.venv\Scripts\python.exe scripts/verificar.py
```

Para desenvolvimento com atualização automática, em dois terminais:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
npm.cmd run dev --prefix frontend
```

Vite encaminha `/api` ao backend. O launcher é o fluxo recomendado para usuários. O seletor nativo requer Windows. O script de encerramento acompanha o launcher; um uvicorn iniciado manualmente deve ser encerrado no terminal em que foi aberto.

Para uma mídia sintética identificada (sem dados reais):

```powershell
.\.venv\Scripts\python.exe scripts/gerar_fixture.py
```

Importe os arquivos resultantes em `.local/fixtures`. Com o serviço aberto, `scripts/smoke.py` valida a API real usando esses arquivos e mantém um projeto claramente chamado **VALIDAÇÃO SINTÉTICA**. Os testes pytest usam armazenamento temporário isolado.

Para validar ASR real offline com Tiny já instalado e uma voz pt-BR já disponível no Windows:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/validar_transcricao.py
$env:LEONIDA_TEST_ASR = '1'
.\.venv\Scripts\python.exe -m pytest -q
```

Os testes opcionais não baixam modelos/vozes. No ambiente preparado, a bateria completa passou com **150 testes**, incluindo inferência nativa e análise sonora real. Sem `LEONIDA_TEST_ASR=1`, os três testes ASR nativos são explicitamente marcados como ignorados; os demais continuam disponíveis. Contratos OpenAI/Ollama usam respostas HTTP controladas: não fazem chamadas externas reais.

`scripts/validar_analise.py` gera uma fixture identificada com duas faixas de pulsos e texto sintético, executa análise real local e verifica persistência/cache. Não apresenta esse texto como fala reconhecida ou acontecimento real. Relatório em `.local/analysis-smoke.json`.

## Documentação

- [Instalação Windows do zero](docs/INSTALL_WINDOWS.md)
- [Consolidação — Fase 1F](docs/PHASE_1F.md)
- [Decupagem — Fase 1D](docs/PHASE_1D.md)
- [Exportações — Fase 1E](docs/PHASE_1E.md)
- [Arquitetura e decisões](docs/ARCHITECTURE.md)
- [Transcrição local — Fase 1B](docs/PHASE_1B.md)
- [Análise e evidências — Fase 1C](docs/PHASE_1C.md)
- [Diagnóstico do computador](docs/ENVIRONMENT.md)
- [Status de desenvolvimento e arquivos](docs/DEVELOPMENT_STATUS.md)
- [Roadmap](docs/ROADMAP.md)
- [Testes, evidências e pendências manuais](docs/TESTING.md)
- [Alterações](CHANGELOG.md)

Status: **GO COM RESSALVAS para o piloto local**, incluindo importação, transcrição CPU, análise, edição e exportações. A instalação isolada passou sem dependências locais prévias. XML tem testes estruturais; a validação nativa no Premiere permanece uma ressalva, assim como VFR/CUDA e provedores ao vivo. Veja [Fase 1F](docs/PHASE_1F.md).
