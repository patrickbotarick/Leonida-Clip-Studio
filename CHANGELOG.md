# Changelog

## 0.1.0 — Fase 1F · 18/11/2026

- Instalação Windows sem dependência do Codex, com Python 3.12 x64/Node compatíveis, wheels binários, FFmpeg em staging verificado e diagnóstico real de imports nativos/encoders.
- Guia de instalação do zero com Python, Node e Visual C++ Redistributable x64; diagnóstico por BAT, solução de problemas, backup/relink e configuração opcional de modelos/GPU/IA.
- Recuperação de arquivo exportado truncado, staging bloqueado e falha de registro após publicação; registro pendente recuperável inclusive após status de falha.
- 150 testes aprovados com ASR real. Instalação isolada aprovada e 147 testes sem modelos + 3 skips ASR esperados. Auditoria npm sem vulnerabilidades na rodada.
- CI Windows e normalização CRLF dos scripts para distribuição. Publicação autorizada para patrickbotarick/Leonida-Clip-Studio, sem dados/modelos/credenciais.
- Importação XML no Premiere permanece com ressalva: projeto de testes do usuário ficou sem responder; não foi encerrado à força nem foi criado projeto novo.


## 0.1.0 — Fase 1E · 18/11/2026

- Painel Exportar com seleção de cortes aprovados, faixas, formatos, pasta Windows, qualidade e prévia vinculada à revisão/opções.
- MP4 individual/lote H.264/AAC por CPU e modo rápido por quadro-chave mediante confirmação, mantendo faixas separadas; verificação de resolução, canais, duração e metadados finais.
- XML FCP7/xmeml v5, FPS racional/NTSC, pontos de origem, sequência consolidada/original, marcadores e canais de áudio; importação real no Premiere pendente, pois a automação foi interrompida por Escape.
- Relatórios CSV/JSON/TXT, SRT por clipe e sequência, recálculo de tempos, proteção de fórmulas no CSV e manifesto de exportação.
- Worker isolado/cancelável na fila existente, staging exclusivo, publicação sem sobrescrita, histórico transacional e recuperação de publicação interrompida. Corrigida corrida que anunciava falha antes da limpeza do staging.
- 146 testes aprovados, incluindo 20 de exportação; comparação de quadros com origem, identidade/ordem das faixas por FFT, corte após duas horas e cancelamento/recuperação. Build e dependências verificados.


## 0.1.0 — Fase 1D · 18/11/2026

- Editor de decupagem com timeline de origem, zoom/pan, waveform PCM min/max por faixa, marcação I/O, campos de timestamp e arraste de regiões/bordas.
- Criação, ajustes, revisão pendente/aprovada/rejeitada, divisão, união com autorização explícita de lacunas, seleção múltipla e filtros por status/categoria/duração/score.
- Histórico transacional de 100 comandos, undo/redo persistido, revisão otimista e proteção de rascunhos na interface.
- Arquivo comprimido de conjuntos anteriores e restauração compatível; reanálise preserva trabalho revisado/manual e evita sugestões sobrepostas a ele. Alteração de fontes invalida evidências e aprovação anteriores.
- Waveform em worker cancelável com PCM em fluxo, cache multirresolução e consultas limitadas a 4.000 pontos; teste real de 7.205 s.
- 126 testes aprovados e build de produção verificado. MP4/XML continuam para 1E.


## 0.1.0 — 2026-11-18

### Continuação — Fase 1C

- Medições reais de energia RMS, picos, variações e silêncio por faixa, com PCM em fluxo, cache de medições e curvas agregadas.
- Heurísticas locais de transcrição e eventos sem diálogo; perfis de conteúdo/finalidade, durações e margens configuráveis.
- Sugestões com categoria, timestamps, justificativa, gancho, pontuação/confiança estimativas, fontes verificáveis e inferências separadas. Nenhuma aprovação automática.
- Ajuste para segmentos/frases com pontuação/pausas, supressão de sobreposição, cache de resultados e invalidação ao alterar as fontes.
- Adaptadores OpenAI Responses/JSON Schema e Ollama local, consentimento por execução, blocos com sobreposição e validação de IDs/tempos. Chave OpenAI apenas em memória/stdin, excluída de persistência/logs/relatórios.
- Painel Análise, filtros, métricas, reprodução de intervalos com parada no OUT, marcações e relatório JSON. Aprovação/edição manual permanece para 1D.
- 112 testes aprovados, incluindo calibração de picos contra FFmpeg astats, análise real sem transcrição e testes de contrato/privacidade sem chamadas externas reais.

### Continuação — Fase 1B

- Faster Whisper 1.2.1 local em processo isolado, CPU int8, modelos Tiny/Base/Small, seleção de idioma e perfis/threads.
- Downloads de modelos separados da transcrição, mediante consentimento, com revisão fixa do repositório e validação real de carregamento. Tiny instalado localmente para testes.
- Extração incremental mono 16 kHz e mixagem de streams selecionados; blocos de cinco minutos com contexto sobreposto e timestamps globais.
- Fila ASR persistida, progresso medido, cancelamento inclusive durante carregamento, recuperação de interrupções e cache de resultados completos.
- Revisão transacional dos projetos, bloqueio de mutações conflitantes e listagem de projetos sem materializar todas as transcrições.
- Painel de transcrição, status de processamento global, opção de trecho de teste, confirmação para substituir texto e preferências persistidas após sucesso.
- PyAV fixado em 16.1.0 após teste real detectar incompatibilidade de Faster Whisper 1.2.1 com PyAV 19.
- CPU real validada com fala sintética pt-BR, silêncio, mixagem de duas faixas, idioma automático, cache, cancelamento e fronteira entre blocos; bateria expandida para 71 testes. CUDA indisponível por biblioteca cuBLAS ausente, sem alteração de drivers.

Primeira entrega executável do Leonida Clip Studio, BTRK Studio.

### Adicionado

- Fundação React/TypeScript/Vite, API FastAPI e banco SQLite local.
- Diagnóstico Windows/CPU/RAM/GPU, descoberta de FFmpeg/FFprobe e configuração isolada.
- Importação por caminho absoluto, metadados técnicos, múltiplas faixas, player e leitura por HTTP Range.
- Prévia de áudio selecionada, cache, fila de um worker, progresso real e cancelamento.
- Projetos recentes, persistência de seleção/transcrição, detecção de mídia ausente/alterada e relocalização.
- SRT/CSV externos, busca/paginação, timestamps globais e exportação JSON/CSV/TXT/SRT.
- Scripts Windows de configuração, verificação, inicialização e encerramento; Job Objects para processos filhos.
- Fixtures sintéticas, testes unitários/integrados e documentação de decisões e limitações.

### Ainda pendente

Corte/edição manual, aprovação, waveform de amostras, MP4 e XML Premiere. Motor local 1C está funcional; provedores opcionais aguardam validação ao vivo. Modelos ASR maiores e runtime GPU seguem com ressalvas.
