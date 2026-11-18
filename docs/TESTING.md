# Testes e validação

## Resultado atual — Fase 1F

**150 testes aprovados em 32,09 s**, zero skips/falhas, com ASR Tiny real habilitado. JUnit: `.local/tests-phase1f.xml`. Uma cópia dos fontes sem ambientes/dados prévios foi configurada pelo script e passou em todos os imports nativos/encoders; sua suíte aprovou **147 testes e 3 skips ASR esperados em 26,57 s** (sem modelo baixado). `pip check`, instalação npm/build e auditoria npm aprovados; a auditoria reportou zero vulnerabilidades na rodada.

Quatro testes de consolidação cobrem arquivo publicado truncado, staging inacessível com limpeza pendente, falha do banco depois de publicar e recuperação idempotente, além de proteção da pasta vizinha. Resultados e limites da instalação limpa estão em [PHASE_1F.md](PHASE_1F.md). É uma instalação isolada no mesmo Windows, não uma VM/PC físico novo.

O projeto de testes aberto no Premiere ficou “Não está respondendo” durante a tentativa de focalização; a importação XML nativa não foi concluída. O usuário pediu usar esse projeto, e nenhum projeto novo foi criado/salvo pela automação. CI Windows foi adicionada; seus resultados remotos devem ser confirmados no GitHub após a publicação.

## Histórico — Fase 1E

**146 testes aprovados em 34,76 s**, sem skips/falhas, com `LEONIDA_TEST_ASR=1`. JUnit: `.local/tests-phase1e.xml`. Após o ajuste final do progresso, **20/20 testes de exportação aprovados em 6,02 s**, em `.local/tests-exports-final.xml`. TypeScript/Vite, compilação Python e `pip check` aprovados. Build: JS 310,86 kB (95,61 kB gzip), CSS 42,17 kB (9,95 kB gzip).

Os casos de 1E incluem MP4 real individual/lote, cópia rápida, faixas e canais separados, comparação de quadros de borda por PyAV, FFT independente para identidade/ordem dos streams, original intacto por hash da fixture, XML/rates/links/canais, SRT relativo/da sequência, CSV protegido, revisões/tokens inválidos, cancelamento real de worker/FFmpeg, falha sem publicação, colisão de destino e recuperação idempotente. Uma origem de 7.205 s foi exportada em 7201–7203 s, sem recodificar/carregar o vídeo inteiro.

Chrome: prévia de dois cortes aprovados/um pendente excluído, todos os formatos e confirmação CFR; exportação iniciada e lote de dez arquivos concluído/verificado por API/FFprobe. `.local/export-smoke.json`. Premiere abriu para teste autorizado, mas o controle visual foi interrompido por Escape antes da importação. XML nativo ainda não validado; não há captura visual final nesta rodada. [Detalhes e limites](PHASE_1E.md).

```powershell
$env:LEONIDA_TEST_ASR='1'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml=.local/tests-phase1e.xml
.\.venv\Scripts\python.exe -X utf8 scripts/validar_exportacao.py
npm run build --prefix frontend
```

## Histórico — Fase 1D

**126 testes aprovados em 27,01 s**, sem warnings/skips/falhas, com `LEONIDA_TEST_ASR=1`. JUnit: `.local/tests-phase1d.xml`. Build TypeScript/Vite e `pip check` aprovados. [Escopo completo da validação 1D](PHASE_1D.md#validação-executada).

Novos testes abrangem edição transacional, conflitos, revisão, split/merge/lacunas, undo/redo e limite de histórico, restauração, preservação na reanálise, envelope PCM calibrado com FFmpeg independente, cache/LOD e resposta limitada por viewport. Uma fixture MP4 com duas faixas e 7.205 s testa waveform longa, consulta final, edição durante geração e cancelamento real do worker. A inferência Tiny offline anterior também foi reexecutada.

Chrome real: waveform por faixa; edição/aprovação persistidas após reabrir; proteção de rascunhos; arraste de OUT, divisão em 20 s, união e undo restaurando estado aprovado. Layout em 1440 × 900. Evidência: `.local/phase1d-desktop.jpg`. Isso não valida precisão de exportação MP4/XML, que ainda pertence à Fase 1E.

```powershell
$env:LEONIDA_TEST_ASR='1'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml=.local/tests-phase1d.xml
npm run build --prefix frontend
.\.venv\Scripts\python.exe -m pip check
```

## Histórico — Fase 1C

**112 testes aprovados em 17,00 s** na execução final, sem warnings/skips, com `LEONIDA_TEST_ASR=1`. JUnit em `.local/tests-phase1c.xml`. São 71 casos anteriores e 41 novos casos/variações para contratos, análise e privacidade. Build TypeScript/Vite, verificação de dependências e `pip check` aprovados.

- PCM/FFmpeg reais em duas faixas: RMS, picos, silêncio, eventos e cache. O pico calculado foi comparado com `astats` do FFmpeg como referência independente, em vez de presumir o pico teórico após compressão AAC.
- Análise de áudio real sem transcrição: sugestões somente `evento_sonoro`, sem diálogo inventado, com score <50 e confiança ≤0,3.
- Heurísticas de texto, evidências exatas, intervalos globais, contexto/frases, durações inválidas e supressão de sobreposição.
- Pipeline local real, persistência, JSON, cache, troca de streams/texto invalidando resultados e cancelamento preservando sugestões anteriores (inclusive uma aprovada usada como fixture de contrato).
- Consentimento obrigatório, ausência de fontes/modelo, limite de blocos e respostas de provedor inválidas por IDs/tempo/schema, erro/refusal/incompletude.
- OpenAI/Ollama testados com `httpx.MockTransport`. Esses testes verificam os protocolos, não inferência real em serviço externo. Não houve transmissão de transcrições para provedores reais.
- Chave sentinela de teste ausente de request.json, argumentos, ambiente, projetos, histórico/erros; controle em memória limpo após execução.

Validação Chrome: três sugestões na fixture marcada como sintética; evidência textual e medida física separadas de inferência; filtro por categoria; formulário OpenAI sem autorização mantendo análise bloqueada; execução local com perfil Entrevista; duas curvas RMS com dois eventos por faixa; prévia iniciada em 11,500 s e parada observada em 29,521 s para OUT de 29,500 s. A prévia de navegador não é teste de precisão de corte/exportação.

Smoke em `.local/analysis-smoke.json`: 90 s/duas faixas, três sugestões e cache confirmado. A execução final levou cerca de 0,54 s com medições já em cache; não é benchmark de primeira execução nem de gravação real longa. Detalhes e limitações: [PHASE_1C.md](PHASE_1C.md).

Build da Fase 1C: aproximadamente 282,7 kB de JS (87,6 kB gzip), CSS 31,9 kB (7,8 kB gzip). O aviso de dependências de desenvolvimento Vite no histórico continua aplicável. Provedores ao vivo, gravação OBS longa e exportação ainda requerem validações próprias.

## Histórico — Fase 1B

**71 testes aprovados em 13,82 s**, sem warnings/skips, na execução com `LEONIDA_TEST_ASR=1`. Inclui os 45 testes anteriores e cobertura de fila persistida, revisões concorrentes, consentimento, modelos ausentes, opções/intervalos, cache, recuperação de interrupção, bloqueio de mutações durante ASR e recusa de GPU sem bibliotecas. Três testes usam Faster Whisper nativo: CPU/idioma/silêncio/mixagem/cache/exports, cancelamento do processo real e fala atravessando a fronteira de 300 s em vídeo de 320 s. Não há download automático nesses testes. Sem opt-in, esses três casos são ignorados com motivo explícito.

```powershell
$env:LEONIDA_TEST_ASR = '1'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml=.local/tests-phase1b.xml
```

Fala sintética pt-BR e modelo Tiny foram usados em um smoke offline separado. Primeira execução válida: cerca de 3,29 s para a fixture de 18 s, com três segmentos reconhecidos; a faixa silenciosa não gerou texto e a repetição utilizou cache. Um teste real na interface com uma thread também concluiu, persistiu preferências e permitiu seek em `00:00:05.940`. Detalhes, limites de benchmark e reprodução dos testes: [PHASE_1B.md](PHASE_1B.md).

O primeiro ensaio detectou incompatibilidade com PyAV 19; a dependência foi fixada em 16.1.0 antes da validação aprovada. O teste CUDA foi negativo por biblioteca cuBLAS ausente; não foi confundido com CPU/NVENC. A dependência `httpx2` agora está instalada pela cadeia do Hub e o warning histórico do TestClient deixou de ocorrer.

Build TypeScript/Vite atual: aproximadamente 267,9 kB de JS (83,5 kB gzip), CSS 28,3 kB (7,1 kB gzip). Verificação de dependências e `pip check` aprovados. A ressalva de segurança de dependências de desenvolvimento Vite descrita no histórico abaixo permanece aplicável.

## Histórico — primeira rodada

## Resultado automatizado

Comando executado em 18/11/2026:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.local/pytest-final --junitxml=.local/test-results.xml
```

**45 passed, 1 warning, 5,91 s**. O aviso é de depreciação do uso de `httpx` pelo TestClient da Starlette instalada, que recomenda migração futura para `httpx2`. Não houve falhas ou skips nessa execução. O JUnit gerado fica em `.local/test-results.xml` e não é versionado.

| Área | Evidência automatizada |
|---|---|
| Mídia multifaixa | FFmpeg gera MP4 H.264 com dois tons AAC independentes; FFprobe confirma duração, 320×180, 30000/1001 FPS, índices e 48 kHz |
| Quatro contêineres | Remux real para MKV/MOV e encode real VP9/Opus para WEBM, seguidos de importação via API |
| Vídeo extenso | Fonte sintética 16×16/1 FPS por 7.205 s; duração maior que duas horas e ausência correta de faixas de áudio |
| Reprodução por ranges | GET com `Range: bytes=0-99` retorna 206 e os 100 bytes exatos do original |
| Persistência | Salva/relê SQLite, enumera projetos, seleciona streams e confirma reabertura |
| Transcrição | SRT com BOM/CRLF/multilinha, CSV localizado com `;` e decimal `,`, Windows-1252 e timecode por frames |
| Validação de tempos | Segundos, HH:MM:SS, frames; rejeita negativos/NaN/infinito/drop-frame e intervalos invertidos ou além do vídeo |
| Integridade do texto | Importação inválida preserva a transcrição anterior; limite de 10 MiB; quatro formatos de exportação; round-trip SRT |
| Sobreposição de legendas | Preserva falas simultâneas legítimas e ordena por início; não confundir com futura deduplicação de cortes |
| Prévias | Extração AAC real de dois streams, resultados distintos, cache imediato na repetição, progresso final 100% |
| Cancelamento | FFmpeg real desacelerado no teste com `-re`, cancelado pelo endpoint; processo encerrado e nenhum parcial remanescente |
| Falha recuperável | Falha de criação de subprocesso injetada explicitamente; estado failed e mensagem compreensível |
| Arquivo ausente/alterado | Erro legível, relocalização idêntica preserva texto; arquivo alterado é detectado e dados incompatíveis são limpos |
| Segurança local | Rejeita Origin/Host externo e mutação sem cabeçalho local; acesso válido permanece funcional |
| Processos órfãos | No Windows, processo pai de teste cria filho, pai é morto, handle do filho confirma término por Job Object |
| Launcher real | Porta efêmera loopback, health/HTML por HTTP real, bloqueio da segunda instância, encerramento por PowerShell, remoção do registro e porta sem serviço |

Fixtures não são resultados fictícios do produto: são vídeos/tom/legendas sintéticos explicitamente criados para testar contratos. A falha de subprocesso é injetada somente no teste correspondente. Os demais testes de processamento invocam FFmpeg/FFprobe reais.

## Compilação e dependências

```powershell
npm.cmd run build --prefix frontend
.\.venv\Scripts\python.exe scripts/verificar.py
.\.venv\Scripts\python.exe -m pip check
powershell.exe -NoProfile -File scripts/configurar.ps1
```

- TypeScript estrito e Vite: **PASS**, sem avisos de CSS na compilação final.
- Build observado: JS aproximadamente 258,5 kB / gzip 80,6 kB; CSS 26,24 kB / gzip 6,64 kB.
- Python, FastAPI, Uvicorn, multipart, FFmpeg, FFprobe e build: **disponíveis**.
- `pip check`: **No broken requirements found**.
- Script de configuração: dependências locais + npm ci + build + verificação. Nenhum pacote global.
- FFmpeg ZIP: **SHA256 conferido**; ver ENVIRONMENT.md.
- FFmpeg NVENC H.264 640×360 por 1 s: **exit code 0**. Não é teste CUDA de Faster Whisper.

`npm audit --omit=dev --json` reportou **zero vulnerabilidades** no frontend de produção. A auditoria completa reportou quatro ocorrências de severidade alta na cadeia Vite → fdir/tinyglobby → picomatch. São consequências do mesmo [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf), ReDoS para globs extglob não confiáveis. O advisory não publicava patch, e a versão mais recente observada do picomatch era 4.0.7, ainda afetada. Não foi aplicado downgrade forçado do Vite. A aplicação compilada não executa Node/Vite em produção, não recebe globs do usuário e o dev server é restrito a loopback. Reavaliar o advisory ao atualizar as dependências.

## Smoke HTTP real

Com o launcher aberto:

```powershell
.\.venv\Scripts\python.exe scripts/gerar_fixture.py
.\.venv\Scripts\python.exe scripts/smoke.py
```

**PASS** para health, HTML, importação/referência, range 206, seleção da segunda faixa, upload SRT pela API, geração/entrega AAC, quatro exports e persistência. Relatório em `.local/smoke-result.json`. O script mantém um projeto chamado VALIDAÇÃO SINTÉTICA, usando apenas mídia gerada dentro de `.local/fixtures`.

## Validação visual executada no Chrome

- Página inicial vazia e layout desktop em viewport de teste 1440×900; também observada a adaptação no viewport menor original.
- Criação de projeto pela interface usando caminho absoluto para a fixture sintética de 12 s e dois streams.
- Player realmente reproduziu a imagem sintética; controles refletiram reprodução/pausa.
- Duas faixas, seus índices/codecs/canais/sample rate e seleção persistida foram exibidos.
- Botão de escuta da segunda faixa gerou prévia com progresso de fila/processamento, exibiu player de áudio, e o controle mudou de reproduzir para pausar ao iniciar.
- Recarregamento/reabertura preservou seleção e três trechos SRT importados pela API.
- Clique no trecho de 7 s posicionou player/régua em `00:00:07.000`.
- Primeiro encerramento com navegador aberto confirmou término, mas registrou reset de conexão Proactor e espera de conexões. O launcher foi ajustado para SelectorEventLoop/keep-alive menor; o teste integrado final de ciclo de vida passou sem traceback.

O upload pelo seletor de arquivo controlado pela extensão Chrome **não pôde ser concluído pela automação**, pois a extensão exigiu permissão adicional de acesso a URLs de arquivos. Nenhuma permissão de extensão foi alterada. A importação via API foi usada no smoke real, seguida de validação visual de texto e navegação; isso não equivale a declarar o diálogo de upload visualmente aprovado.

## Validação manual pendente

1. Abrir pelo `.bat` no navegador padrão habitual; validar seletor nativo de vídeo e seleção SRT/CSV sem automação.
2. Usar um vídeo OBS real autorizado, com duas ou mais faixas e duração extensa, observar RAM/CPU e testar nomes originais das faixas.
3. Testar diferentes codecs/contêineres no navegador; registrar quais exigirão proxy.
4. Importar CSV exportado pela versão de Premiere usada pelo editor; verificar cabeçalhos, FPS e referência temporal.
5. Mover o original com o serviço fechado, reabrir, relocalizar e confirmar timestamps; fazer backup antes de substituir a mídia por outra.
6. Futuramente validar cortes precisos, sobreposição de sugestões, aprovação/rejeição, xmeml e legendas remapeadas. **Essas funções ainda não existem e não têm testes alegados nesta rodada.**

A instalação do Premiere foi encontrada no inventário de aplicativos, mas não foi aberta: não há XML para importar nesta fase. A validação real no Premiere permanece obrigatória quando a fase 1E for implementada.
