# Fase 1B — transcrição local

Entrega funcional de continuação da v0.1.0 em 18/11/2026. **GO COM RESSALVAS para CPU/Tiny**; CUDA não está operacional neste computador. SRT/CSV externos permanecem disponíveis.

## Como usar

1. Abra o `.bat` habitual, importe/reabra o vídeo e escute/selecione a voz principal no painel **Áudio**. Nenhum stream é presumido como voz.
2. Abra **Texto → Transcrição local**. Selecione perfil, modelo, idioma e threads.
3. O modelo **Tiny** já foi baixado para este computador. Em outra instalação ou ao selecionar Base/Small, marque a autorização de download e clique em **Baixar**. O download recebe somente pesos públicos de `Systran/faster-whisper-*` no Hugging Face. Não há envio de mídia/texto e nenhum token de conta é usado.
4. Use o teste de até 30 s a partir da posição atual para avaliar a qualidade. Desmarque para processar o vídeo completo.
5. Se existe transcrição, confirme explicitamente a substituição. Somente um resultado bem-sucedido altera o texto; falha/cancelamento/interrupção preservam o anterior.
6. Acompanhe a etapa e o progresso, ou cancele. A barra inferior também informa a tarefa durante navegação em outras partes da aplicação. Fechar a aba não encerra o processamento; encerrar o serviço cancela os processos.
7. Após sucesso, revise o texto e use a navegação sincronizada e exports JSON/CSV/TXT/SRT existentes.

| Perfil | Modelo padrão | Busca | Threads padrão |
|---|---|---|---|
| Econômico | Tiny (~75 MB) | beam 1 | 2 |
| Equilibrado | Base (~145 MB) | beam 3 | 4 |
| Alta qualidade | Small (~485 MB) | beam 5 | 4 |

Modelo e threads podem ser ajustados após escolher o perfil; limite de 1–4 threads. Todos são modelos multilíngues. Idioma automático é detectado por bloco; `pt` e `en` também podem ser definidos. Português utiliza o código `pt` do Whisper, sem modelo separado exclusivo para o Brasil. Não há diarização nem tradução.

## Arquitetura e fluxo

- `backend/transcription.py`: contratos Pydantic, perfis/catálogo, detecção de runtime, assinaturas, janelas temporais e normalização.
- `backend/processing.py`: supervisor de uma fila de trabalho pesado, histórico SQLite e aplicação transacional.
- `backend/transcription_worker.py`: processo Python isolado que carrega o modelo e invoca FFmpeg/Faster Whisper; pode ser morto durante carregamento/inferência. Job Objects propagam encerramento aos FFmpegs filhos no Windows.
- `frontend/src/TranscriptionControls.tsx`: configurações, consentimento, processamento, progresso e cancelamento.

Os streams escolhidos são convertidos para mono/16 kHz; múltiplos streams são misturados por `amix` com normalização. O vídeo original não é alterado. A transcrição usa blocos centrais de **300 s**, com até **5 s de contexto** de cada lado. Uma fala é atribuída ao bloco que contém o ponto médio do segmento. Timestamps são convertidos imediatamente para a origem global; duplicatas textuais sobrepostas são removidas. Não há garantia de identidade perfeita entre reconhecimentos na borda, nem de reconhecimento correto de uma frase longa que atravesse o contexto; revisão humana continua necessária.

Cada WAV temporário cobre no máximo 310 s (aproximadamente 10 MB em PCM mono/16 kHz/16 bits), sendo apagado antes do próximo. O modelo é carregado uma vez por tarefa e descarregado quando o processo termina. O texto incremental é checkpointado localmente; a transcrição visível é trocada atomicamente somente ao concluir. Checkpoints incompletos não são tratados como resultado válido.

O progresso usa posição de saída real do FFmpeg e fim dos segmentos emitidos pelo Whisper. Combina 10% de extração e 90% de transcrição dentro de cada bloco; **não é uma estimativa de tempo restante**. Silêncio/VAD pode fazer a porcentagem avançar ao terminar um bloco. Download usa contagem real de bytes/arquivos e estado de validação; quando o total não é estável, a interface mostra progresso indeterminado. 100% somente após sucesso e aplicação final.

## Persistência, cache e recuperação

- Projetos recebem `schema_version=1` e uma revisão monotônica. Atualizações conferem a revisão na mesma transação SQLite; conexões são explicitamente fechadas.
- `processing_jobs` guarda tipo, projeto, opções, etapa, progresso, estado e datas. Há um worker e no máximo duas tarefas ativas/enfileiradas de modelos/transcrição. Prévias continuam em sua fila leve separada.
- Enquanto uma transcrição está ativa, a API rejeita troca de faixas/texto/mídia do projeto; a revisão ainda impede sobrescrita em condições concorrentes.
- Na reabertura, tarefas `queued/running/cancelling` são marcadas como **interrompidas**, seus arquivos temporários próprios são removidos e o usuário pode iniciar novamente. Não existe retomada automática a partir de bloco parcial nesta fase.
- Cache completo considera caminho, tamanho/mtime/duração, streams, perfil/modelo/idioma/dispositivo/threads/trecho, revisão do modelo e versão do motor/algoritmo. A confirmação de substituição não muda o cache. Mídia alterada é detectada antes de aplicar resultados.
- Download ocorre em staging por tarefa, com revisão fixa obtida do repositório. Arquivos recebem tamanhos/SHA256 em manifesto; só após carregamento CPU bem-sucedido o modelo é movido à pasta definitiva. O catálogo usa manifesto/tamanhos para verificação leve, sem recalcular o hash do modelo a cada consulta. Pastas de modelo preexistentes não são sobrescritas.
- Preferências da transcrição bem-sucedida ficam no projeto; opções das tentativas ficam no histórico. Não há undo de substituição bem-sucedida: exporte o texto anterior se quiser conservá-lo.

Armazenamento: `.local/models`, `.local/transcription/work`, `.local/transcription/cache`, `.local/hf-cache` e SQLite. Tudo ignorado pelo Git. Não há cota/coleta de cache por idade ainda. Trabalhos temporários são removidos apenas após resolução do caminho e confirmação de que estão dentro do diretório de trabalho ASR.

## Offline, dependências e GPU

O processo de transcrição define `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` e `local_files_only=True`, usa tokenizer/modelo locais e desabilita telemetria do Hub. Downloads são tarefas distintas, exigem consentimento e usam `token=False`; não leem tokens pessoais implicitamente.

Dependências validadas: Faster Whisper **1.2.1**, CTranslate2 **4.9.0**, PyAV **16.1.0**, ONNX Runtime **1.32.0**. O pin PyAV é deliberado: PyAV 19 rejeitou o argumento `metadata_errors` usado pelo Faster Whisper 1.2.1 em um teste real. O lock registra o conjunto instalado; reavaliar essa restrição ao atualizar o motor.

A RTX 3050 é detectada (`get_cuda_device_count=1`), mas a tentativa real de inferência CUDA falhou por ausência de `cublas64_12.dll`. O diagnóstico também verifica `cudnn64_9.dll`. A UI/API bloqueiam CUDA se as bibliotecas não podem ser carregadas. A presença futura das bibliotecas habilita tentativa experimental, não significa validação concluída. CPU int8 é o caminho validado e padrão. Nenhum driver, CUDA Toolkit ou cuDNN global foi instalado.

Referências de API: [Faster Whisper oficial](https://github.com/SYSTRAN/faster-whisper), [CTranslate2](https://opennmt.net/CTranslate2/python/ctranslate2.html). A implementação foi também verificada contra as assinaturas/código dos pacotes efetivamente instalados.

## Evidências desta rodada

- Fala sintética pt-BR gerada com **Microsoft Maria Desktop**, voz já instalada no Windows. Nenhuma voz real foi gravada e nenhum serviço TTS externo foi usado.
- Fixture MP4 de **18 s**, primeira faixa silenciosa e segunda com fala. Tiny/CPU/int8/duas threads reconheceu três segmentos em aproximadamente **3,29 s** na primeira execução válida desse smoke. Isso não é benchmark generalizável para gravações longas, outros modelos ou toda a pipeline do produto.
- Faixa silenciosa produziu zero trechos; repetir a configuração da faixa de voz aplicou resultado em cache.
- Idioma automático identificou `pt` no teste nativo; quatro exports de transcrição foram verificados.
- Uma fixture real de **320 s** com fala aos **298 s** atravessou a fronteira de 300 s; o teste verificou dois blocos, conteúdo reconhecido e timestamps globais na região correta.
- Cancelamento do processo real Faster Whisper durante carregamento/processamento encerrou o processo e preservou texto anterior.
- Pela interface Chrome: execução real com **uma thread**, estados de fila/processamento/conclusão, três trechos salvos, confirmação de substituição, preferências reabertas, download Base bloqueado sem autorização e seek de um trecho gerado para **00:00:05.940**.
- Bateria completa: **71 testes aprovados em 13,82 s**, sem warnings/skips, na execução com `LEONIDA_TEST_ASR=1`; três deles invocam ASR nativo offline, incluindo mixagem de duas faixas. Testes de contratos/cache/falhas também têm doubles explicitamente identificados; eles não substituem os testes nativos.

Scripts: `gerar_fala.ps1` e `validar_transcricao.py`. Relatório do smoke em `.local/transcription-smoke.json`; JUnit em `.local/tests-phase1b.xml`. Os modelos precisam ser instalados explicitamente e a fixture criada antes dos testes opt-in. Sem a variável opt-in, esses três testes são ignorados com motivo explícito.

## Limitações e próximo marco

Ainda falta benchmark de duas horas de fala real/OBS, avaliação dos modelos Base/Small neste hardware, quota de cache e validação de runtime GPU compatível. Não há garantia de precisão textual nem diarização. A reprodução continua sujeita aos codecs do navegador; essa restrição é independente do processamento FFmpeg.

A continuação **Fase 1C** já foi implementada; consulte [PHASE_1C.md](PHASE_1C.md). O próximo marco é edição/validação manual da Fase 1D. Exportação de cortes e XML permanece na Fase 1E.
