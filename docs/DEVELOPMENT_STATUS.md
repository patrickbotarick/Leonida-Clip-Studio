# Status de desenvolvimento — 18/11/2026

**Versão 0.1.0. Status: GO COM RESSALVAS para Fases 0/1A/1B, análise local 1C, decupagem visual 1D, exportações 1E e consolidação 1F.**

O fluxo já gera sugestões de momentos com evidências reais de áudio/texto. Edição, revisão e exportações MP4/relatórios/SRT estão disponíveis; XML FCP7 foi gerado/testado estruturalmente, com validação nativa pendente. Entrega atual: [PHASE_1F.md](PHASE_1F.md); exportações: [PHASE_1E.md](PHASE_1E.md); edição: [PHASE_1D.md](PHASE_1D.md); análise: [PHASE_1C.md](PHASE_1C.md); transcrição: [PHASE_1B.md](PHASE_1B.md).

## Resultado disponível

| Funcionalidade | Estado |
|---|---|
| Projetos recentes, criação e reabertura | Implementado, dados reais em SQLite |
| Importação local sem duplicar mídia | Implementado por seletor Windows ou caminho absoluto |
| Metadados e múltiplas faixas | Implementado com FFprobe, quatro contêineres testados |
| Player e seek | Implementado; MP4 H.264/AAC validado visualmente no Chrome |
| Seleção de áudio e persistência | Implementado, nenhuma faixa presumida como voz |
| Escuta separada | Implementado com prévias AAC de até 30 s a partir da posição atual |
| Progresso/cancelamento de prévias | Implementado com subprocesso real; fila de um worker |
| Recuperação de mídia movida/alterada | Implementado com validação de assinatura por metadados |
| SRT/CSV externos e navegação por texto | Implementado e testado via API; visualização/seek validados no Chrome |
| JSON/CSV/TXT/SRT de transcrição | Implementado e testado |
| Diagnóstico e perfis de transcrição | Implementados; modelos/idioma/dispositivo/threads ajustáveis |
| Faster Whisper CPU | Funcional; Tiny validado em inferência real offline |
| Download de modelos, cache e cancelamento | Implementados; consentimento explícito, processos isolados e histórico SQLite |
| Revisões e recuperação de tarefas | Implementadas; resultados aplicados atomicamente e interrupções identificadas ao reabrir |
| Análise sonora e heurísticas locais | Implementadas, testadas com mídia real sintética e calibradas contra FFmpeg astats |
| Sugestões com evidências e inferências | Implementadas; score/confiança estimativos, margens, limites de frases e deduplicação |
| OpenAI/Ollama | Adaptadores implementados com consentimento; contratos HTTP testados, inferência ao vivo pendente |
| Filtros, prévia e relatório | Categoria/score/busca/ordenação, regiões na régua, reprodução do intervalo e JSON disponíveis |
| Timeline de edição, waveform de amostras e aprovação | Implementadas; zoom/pan, IN/OUT, arraste, criação/divisão/união, filtros, revisão e histórico de 100 comandos |
| Exportações MP4, relatórios e legendas | Implementadas, testes reais de quadro/áudio, lote e recuperação |
| XML FCP7/Premiere | Gerado/testado estruturalmente; importação nativa pendente, controle visual interrompido por Escape |

## Arquivos criados

```text
/
├── README.md / CHANGELOG.md / .gitignore / .env.example
├── Abrir Leonida Clip Studio.bat
├── Configurar Leonida Clip Studio.bat
├── Encerrar Leonida Clip Studio.bat
├── backend/
│   ├── __init__.py / config.py / database.py
│   ├── main.py / media.py / transcripts.py
│   ├── jobs.py / processes.py
│   ├── processing.py / transcription.py / transcription_worker.py
│   ├── analysis.py / audio_analysis.py / analysis_providers.py / analysis_worker.py
│   └── requirements.txt / requirements-dev.txt / requirements-lock.txt
├── frontend/
│   ├── package.json / package-lock.json / tsconfig.json
│   ├── index.html / vite.config.ts
│   └── src/main.tsx / src/styles.css / src/TranscriptionControls.tsx / src/AnalysisPanel.tsx
├── scripts/
│   ├── configurar.ps1 / encerrar.ps1 / verificar.py / launch.py
│   └── gerar_fixture.py / smoke.py / gerar_fala.ps1 / validar_transcricao.py / validar_analise.py
├── tests/
│   ├── conftest.py / test_api.py / test_transcripts.py
│   └── test_processes.py / test_launcher.py / test_processing.py / test_asr_integration.py
│       test_analysis.py / test_analysis_pipeline.py / test_analysis_providers.py
└── docs/
    ├── ARCHITECTURE.md / ROADMAP.md / ENVIRONMENT.md
    └── DEVELOPMENT_STATUS.md / TESTING.md / PHASE_1B.md / PHASE_1C.md
```

Dependências, build, SQLite, mídias de validação e cache existem apenas em diretórios ignorados: `.venv`, `.tools`, `.local`, `frontend/node_modules` e `frontend/dist`. Publicação autorizada pelo usuário para `patrickbotarick/Leonida-Clip-Studio`; apenas fontes, lockfiles, scripts, testes e documentação entram no Git. Dados, ferramentas, modelos e caches permanecem ignorados.

## Verificação

**150 testes aprovados**, com ASR nativo habilitado, análise sonora real, decupagem persistente, waveform longa, exportações e contratos controlados dos provedores. Build TypeScript/Vite, verificação de dependências e `pip check` aprovados. Smoke 1C: duas faixas/90 s, três sugestões, cache confirmado; cerca de 0,54 s na execução final com medições previamente em cache. A interface Chrome validou análise local, filtro por categoria, evidências, gráficos por faixa e prévia com parada no OUT. Veja [PHASE_1C.md](PHASE_1C.md) e [TESTING.md](TESTING.md).

## Ressalvas para GO

- Reproduzir os contêineres importados depende dos codecs do navegador; proxy automático ainda não existe.
- A escolha de arquivo/transcrição em diálogos nativos precisa de uma rodada manual do usuário. A automação de upload no Chrome ficou bloqueada pela configuração da extensão, sem alterar permissões. A API de importação SRT/CSV foi validada de verdade, e o texto persistido foi exibido e usado para seek na interface.
- Faster Whisper CPU/Tiny validado. A tentativa CUDA encontrou biblioteca cuBLAS ausente; GPU permanece desabilitada sem bibliotecas. NVENC do FFmpeg é um recurso separado, já validado.
- Modelos Base/Small e perfis correspondentes estão configuráveis, mas não foram baixados/benchmarkados nesta máquina. Não há cota de cache nem retomada por bloco parcial; tarefas interrompidas podem ser reexecutadas.
- Benchmark pesado, formatos específicos de CSV Premiere, VFR, offsets de timecode e XML real ainda precisam de trabalho.
- `npm audit` reexecutado na Fase 1F: zero vulnerabilidades reportadas. Resultados históricos estão em TESTING.md.
- OpenAI/Ollama não foram chamados com conta/modelo reais nesta rodada. O modo local está validado, mas contratos HTTP controlados não equivalem a validação ao vivo de cada modelo/provedor.
- Indicadores sonoros usam mono/8 kHz e janelas de 0,5 s, não LUFS/true peak. Não há análise visual nem previsão de viralização. Resultados aguardam revisão humana.

Fase 1F consolida o piloto e a instalação Windows. Persistem ressalvas específicas: importação XML no Premiere, VFR/timecodes, gravações OBS reais e configurações opcionais de GPU/provedores.

## Entrega 1D

126 testes automatizados aprovados, incluindo ASR Tiny real, waveform PCM comparada a uma decodificação independente, mídia sintética de 7.205 s, consultas limitadas por viewport e cancelamento de worker. TypeScript/Vite e pip check aprovados. Histórico por diferenças persistido; conflitos HTTP 409; fontes alteradas arquivam conjuntos e invalidam a revisão. Reanálise preserva cortes manuais/editados/aprovados/rejeitados e filtra sugestões que os sobreponham. Ver PHASE_1D.md para a distinção entre testes automatizados e validação visual.

Limites: 1.000 cortes ativos, 100 comandos de undo/redo; conjuntos históricos sem expurgo automático (interface mostra os últimos 50); cache de waveform sem cota automática; identidade da mídia por caminho/tamanho/mtime/metadados, não hash integral. Busca por FPS nominal não equivale a precisão de quadro/VFR.

## Entrega 1E

146 testes completos aprovados em 34,76 s; os 20 casos de exportação foram reexecutados após o ajuste final do contador de progresso, todos aprovados em 6,02 s. Recodificação comparada à origem por quadros decodificados e FFT dos streams; cópia rápida explicitamente aproximada; origem de 7.205 s testada com corte próximo ao final. MP4, XML, SRT individual/consolidado/original, relatórios, nomes/destino seguros e histórico implementados. Lote iniciado pelo Chrome com dois cortes aprovados, dois streams estéreo, seis formatos e dez arquivos, concluído e verificado no backend; um corte pendente foi excluído. `.local/export-smoke.json` contém o resumo.

Premiere instalado/aberto e uso do projeto de teste autorizado; o controle visual foi interrompido por Escape antes de importar o XML. Nenhum projeto existente foi modificado nem foi alegada validação nativa. Ver PHASE_1E.md para restrições de CFR, timecode zero/NDF, canais/cores e fontes de rede. Servidor local permanece disponível para o usuário; o Premiere não foi fechado à força após a interrupção.
