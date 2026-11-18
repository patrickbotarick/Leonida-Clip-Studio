# Arquitetura — v0.1.0

## Componentes implementados

```text
Navegador local · React + TypeScript
           │ HTTP mesma origem /api · localhost
           ▼
FastAPI + Uvicorn · 127.0.0.1:8765
  ├── main.py          contratos, validação HTTP e arquivos com Range
  ├── database.py      projetos SQLite/WAL, documentos JSON por projeto
  ├── media.py         caminhos, assinaturas e metadados FFprobe
  ├── transcripts.py   SRT/CSV, timestamps, geração SRT
  ├── jobs.py          fila de prévias FFmpeg, estado/progresso/cancelamento
  ├── processes.py     processos controlados e Job Objects Windows
  ├── processing.py    fila pesada persistida e aplicação transacional
  ├── transcription.py / transcription_worker.py · contratos e ASR isolado
  ├── analysis.py / audio_analysis.py · sugestões e medições por faixa
  ├── analysis_providers.py / analysis_worker.py · provedores e processo analítico
  └── config.py        raiz, versão e armazenamento local
           │
           ├── original: somente leitura, referenciado pelo caminho
           ├── .local/projects.sqlite3: persistência
           └── .local/previews: cache AAC descartável
```

Produção local usa `frontend/dist` servido pelo próprio FastAPI. Vite é uma ferramenta de desenvolvimento/compilação; não integra o runtime necessário para abrir a versão compilada. Não há Docker, nuvem, servidor remoto ou backend Node.

## Decisões desta rodada

1. **SQLite com documento JSON por projeto:** mantém metadados, streams, texto e campos de cortes/configurações/exportações juntos. Projetos recebem `schema_version=1` e revisão monotônica; escritas conferem a revisão em transação. `processing_jobs` guarda o histórico de tarefas pesadas. O launcher limita uma instância por diretório de dados; a API protege projetos em transcrição contra mutações conflitantes. A listagem de projetos extrai somente metadados/contagem de texto via SQLite, sem materializar todos os textos. Ainda não há framework de migrações entre versões futuras.
2. **Sem upload de vídeo:** importação por seletor Windows ou caminho. Uma página de navegador não recebe caminhos absolutos ao arrastar arquivos; o gesto conduz à mesma importação, sem cópia oculta. Somente transcrições passam por multipart.
3. **FFprobe em thread de serviço:** endpoints síncronos FastAPI utilizam o thread pool, isolando subprocessos, SQLite e parsing da thread do loop ASGI. Tempo máximo de probe: 60 s. Não há cancelamento de probe pela interface nesta fase; prévias têm cancelamento explícito.
4. **Reprodução direta:** `FileResponse` entrega ranges de bytes. Não se carrega o vídeo completo, não se recodifica por padrão e não se muda o original. Não há conversão de codec/proxy ainda.
5. **Escuta de áudio em pequenos intervalos:** extrai até 30 s de um stream. Um executor de um worker, fila de até quatro tarefas e duas threads limitam concorrência. Até 100 registros de prévias são mantidos em memória. A transcrição possui fila pesada separada e aceita mistura normalizada dos streams explicitamente escolhidos.
6. **Progresso medido:** FFmpeg publica `out_time_us`, dividido pela duração efetiva da prévia. 100% só é gravado após saída bem-sucedida e finalização do arquivo. Sem porcentagens simuladas. Na fila, o progresso fica em zero.
7. **Cancelamento e encerramento:** evento de cancelamento encerra FFmpeg, aguarda o processo e remove o arquivo parcial. Job Object com `KILL_ON_JOB_CLOSE` garante encerramento do filho quando o processo principal termina abruptamente. Timeouts de probe/dialog também matam e aguardam o subprocesso. O launcher roda uma única instância de Uvicorn, monitorando um arquivo de encerramento com token aleatório por execução; não mata processos por nome/porta.
8. **Loop Windows:** `asyncio.SelectorEventLoop`, pois as chamadas a FFmpeg ocorrem em threads síncronas. A escolha evita o erro de conexão resetada do Proactor observado durante o primeiro teste com player aberto. HTTP keep-alive de 2 s e janela de shutdown de 5 s. Não se utiliza `asyncio` para subprocessos neste desenho.
9. **Cache barato de prévias:** SHA256 de caminho, tamanho, mtime, índice de áudio e instante inicial. O hash é da chave, não do conteúdo do vídeo. Uma alteração de arquivo detectada requer relocalização. ASR e análise têm suas próprias chaves incluindo texto/configurações/versões. Ainda não há coleta por quota/idade.
10. **Transcrição externa como caminho inicial leve:** UTF-8/Windows-1252; SRT e aliases de cabeçalhos CSV. Intervalos são validados dentro da duração da mídia. Timecode usa FPS racional convertido; drop-frame e offset de sequência não são inferidos. Legendas legitimamente sobrepostas são preservadas; isso é diferente da futura deduplicação de sugestões de cortes.
11. **Interface com dados reais:** estado inicial vazio, sem cards ou resultados de IA simulados. Arte decorativa da página inicial é CSS, sem se apresentar como waveform real. Projetos de validação são identificados como sintéticos. Transcrições são paginadas em 100 trechos; busca do trecho ativo usa busca binária; régua exibe até 1.000 marcações de texto.
12. **ASR e análise isolados:** Faster Whisper e motor de análise têm processos separados, supervisionados pela mesma fila pesada persistida de um worker (até duas tarefas ativas/enfileiradas). A análise processa PCM por stream e gera sugestões locais ou consulta provedores com consentimento. OpenAI usa Responses/JSON Schema, Ollama usa endpoint loopback e schema; ambos têm validação de contrato, com inferência ao vivo ainda pendente. Ver [PHASE_1B.md](PHASE_1B.md) e [PHASE_1C.md](PHASE_1C.md).
13. **Sugestões rastreáveis:** áudio produz apenas eventos genéricos; texto fornece IDs e citações da própria transcrição. Interpretações e ganchos são sugestões editoriais, não fatos visuais. Intervalos respeitam duração/contexto e são expandidos para unidades de frase; quando não cabem, são descartados. NMS por score remove sobreposições. Resultados são aplicados atomicamente após verificar fontes/revisão; novas transcrições, mídia diferente ou seleção de streams invalidam análise anterior.
14. **Segredos por execução:** `SecretStr` excluído do dump público, credencial apenas no controle em memória e em pipe stdin do worker. Não é colocada em arquivo de request, ambiente, argumentos, projeto ou cache. Erros dos provedores não propagam corpo bruto. URLs são fixas OpenAI/loopback e não há ferramentas de modelo.

## Segurança e privacidade

- Bind de servidor em `127.0.0.1`, Host permitido `127.0.0.1`/`localhost` e rejeição de Origin divergente da origem atual.
- Mutações exigem `X-Leonida-Client: 1`. Navegadores externos não podem enviar esse cabeçalho sem preflight/CORS, que não é habilitado.
- CSP bloqueia carregamento de scripts externos e enquadramento por terceiros; fontes/ícones/estilos não usam CDN.
- Caminhos de mídia nunca são concatenados a um shell. Subprocessos FFmpeg recebem lista de argumentos; o script fixo do diálogo não interpola entrada do usuário.
- Originais são somente lidos. Prévias usam nomes derivados/únicos e arquivos temporários próprios. Downloads de texto deixam escolha de destino/sobrescrita ao navegador.
- A exportação CSV protege textos que começam com `=`, `+`, `-` ou `@` com apóstrofo para reduzir interpretação como fórmula ao abrir em planilhas. Isso é uma transformação deliberada, não um round-trip textual exato para esses prefixos.
- Código e exportações não contêm credenciais. Ainda não existe armazenamento de chave API; implementar consentimento e armazenamento adequado antes de conectar provedores.
- Não existe telemetria implementada pelo aplicativo. No modo local, o fluxo após configuração permanece offline. OpenAI/Ollama só recebem texto mediante consentimento e ação explícita; áudio/vídeo não são enviados. `store=False` é configurado no OpenAI, sem prometer substituir as políticas de dados da conta/provedor.

## Próximas decisões

Fases 1B/1C introduziram tarefas persistidas, revisão, ASR e análise. Próximas decisões: edição/aprovação 1D, cotas/evicção de cache, retomada por checkpoints e validação dos provedores ao vivo. Antes de XML: testar NTSC/non-drop/drop-frame, VFR, canais de áudio, timebase e importação real no Premiere.

## Decupagem — Fase 1D

`editing.py` valida comandos create/update/status/split/merge/delete/undo/redo/restore. Cada POST `/api/projects/{id}/cuts` exige `expected_revision`; SQLite executa documento e diferenças de histórico na mesma transação. Revisão concorrente responde 409. Tabelas `cut_history` (últimos 100 comandos por projeto) e `cut_archives` (JSON zlib dos cortes/fontes resumidas) evitam guardar a transcrição inteira em cada comando. As diferenças preservam a ordem e IDs. Undo/redo verifica hashes do conjunto e do contexto antes de aplicar; uma nova ação elimina o ramo de redo.

Reanálise arquiva o conjunto anterior e preserva cortes manuais, editados, aprovados e rejeitados; sugestões novas que cruzam os preservados são descartadas. Alteração de faixa/transcrição arquiva o conjunto anterior, retém o trabalho manual/revisado como pendente, zera estimativas e marca evidências históricas. Mídia diferente limpa os cortes ativos e conserva o arquivo histórico. Fontes idênticas movidas são reconhecidas pelos metadados existentes, sem hash integral do arquivo. Restauração exige contexto compatível e arquiva o conjunto atual.

`waveform.py` e `waveform_worker.py`: FFmpeg fornece mono float32 a 16 kHz, reduzido em janelas de 128 amostras para pares min/max binários little endian. Níveis seguintes agregam pares de janelas, mantendo extrema. A construção lê no máximo cerca de 2 MiB de PCM por bloco; níveis são construídos em fluxo em disco. Aproximadamente 14,4 MB por faixa em duas horas, sem armazenar PCM integral. Manifest e níveis só se tornam disponíveis após publicação atômica da pasta. Cancelamento mata worker/FFmpeg pelo Job Object e remove staging. API escolhe um nível pela janela e lê no máximo 4.000 pares; nunca devolve a waveform inteira de uma gravação longa. Cache é indexado por mídia/assinatura/faixa/versão, sem alterar a revisão do projeto. Não substitui as medidas RMS/energia de 1C.

`CutEditor.tsx` mantém rascunho explícito com salvar/descartar; comunica bloqueio de saída/alteração de fontes ao componente principal e registra beforeunload. Comandos só atualizam estado local após confirmação da API. Player usa tempo absoluto e interrupção de prévia em OUT por eventos/rAF. Tempos não são arredondados no servidor para FPS; passo por FPS é apenas navegação nominal. A exportação precisa ainda pertence a 1E.

## Exportações — Fase 1E

`exports.py` contém schema de opções, validação de aprovação/revisão, plano vinculado por hash e relatórios/SRT. `premiere_xml.py` gera xmeml v5 de origem única com URI escapada, timebase racional, pontos em quadros, links e canais. O worker `export_worker.py` usa FFmpeg sequencialmente com duas threads de CPU e `-n`; mede progresso em `out_time_us`, faz probe independente dos MP4 e só conclui o manifesto após validar saídas. MP4 rápido busca um quadro-chave com leitura limitada de FFprobe, preserva codecs aceitos e é explicitamente aproximado.

A fila pesada existente compartilha recursos com ASR/análise/waveform e bloqueia mutações do projeto durante a exportação. Staging fica no mesmo volume do destino para publicação por rename em pasta exclusiva. `export_storage.py` valida arquivos/manifesto, publica e limpa somente staging com nome/caminho/marcador compatíveis. `database.record_export` insere histórico do projeto e tarefa concluída numa transação idempotente, sem regravar cortes/transcrição. Interrupção entre publicação e registro é recuperável pelo manifesto. Falha/cancelamento é anunciado após a limpeza normal, evitando que a interface veja término com temporários ainda em uso.

Rotas: POST `/api/projects/{id}/exports/plan`, POST `/api/projects/{id}/exports`, GET `/api/projects/{id}/exports` e GET `/api/exports/{job}/files/{filename}`. Download requer tarefa concluída e nome em allowlist, com resolução dentro da pasta publicada. A escolha da pasta Windows usa `/api/dialog/directory`. `ExportPanel.tsx` é um diálogo de opções/prévia, progresso/cancelamento e histórico/arquivos. Status global reconhece exportação; ao concluir, o projeto é recarregado sem perder revisão mais nova no estado principal. Exportações não usam API externa ou credenciais de IA.

Tempo absoluto de origem e tempo da sequência são distintos: sequência consolidada soma durações; modo original usa posições de origem. XML quantiza IN/OUT uma vez no FPS racional e deriva a duração por diferença. SRT individual intersecta a transcrição com cada corte, desconta origem e considera o deslocamento medido do MP4; SRT de sequência usa a mesma quantização do XML quando incluído. A montagem original rejeita sobreposições para XML/SRT. Os relatórios e manifesto preservam o intervalo aprovado e distinguem as medidas físicas do MP4, especialmente no stream copy.

## Consolidação — Fase 1F

O instalador valida Python 3.12 x64 e Node 24/22.12+ e não depende de caminhos do Codex. Pacotes binários Python, lockfiles e npm ci permitem recriar os ambientes. FFmpeg é extraído em staging exclusivo; movimentação/remoção verificam caminhos absolutos sob .tools. O verificador importa bibliotecas nativas e executa ferramentas, em vez de presumir que presença no disco significa capacidade de rodar. Runtime Visual C++ x64 é um pré-requisito documentado, sem instalação global silenciosa.

Manifestos de exportação também validam tamanho dos arquivos. Os flags cleanup_pending/publication_pending mantêm tarefas elegíveis para recuperação após status terminal, sem duplicar histórico nem apagar pastas publicadas. Uma falha de limpeza por permissão não derruba a identificação do processamento e permite tentar novamente ao reiniciar. A publicação permanece sem sobrescrita e restrita à pasta exclusiva.
