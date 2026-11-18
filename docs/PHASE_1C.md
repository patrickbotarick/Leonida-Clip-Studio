# Fase 1C — motor de análise

Entrega da continuação v0.1.0 em **18/11/2026**. **GO COM RESSALVAS para o modo local**. OpenAI/Ollama têm adaptadores e testes de contrato; inferência ao vivo nesses provedores não foi realizada nesta rodada.

## Operação

1. Importe/reabra o vídeo. Se necessário, transcreva ou importe SRT/CSV pelo painel Texto.
2. Em Áudio, selecione as faixas desejadas. A análise sonora mede cada stream separadamente, mesmo se a transcrição foi feita com mixagem.
3. Abra **Análise → Configurar análise**. O padrão é heurística local/offline.
4. Selecione conteúdo (Gameplay, Live, Podcast, Entrevista, React, Informativo ou Genérico) e finalidade (Shorts, Reels, TikTok, melhores momentos ou decupagem).
5. Defina durações mínima/preferencial/máxima e margens antes/depois. São preferências de seleção; não geram exportação/reformatação vertical.
6. Ative medidas de áudio nas faixas escolhidas ou desative para usar somente texto. Sem texto, o modo local ainda identifica eventos sonoros genéricos. Sem nenhuma fonte, o pedido é rejeitado.
7. Execute e acompanhe a tarefa. Uma nova análise exige confirmação para substituir sugestões anteriores, aplicadas apenas após sucesso.
8. Revise os cards, filtre por categoria/score/busca e ordene por score/tempo. O botão de reprodução navega e pausa aproximadamente no OUT. Exporte o relatório JSON se desejar.

As sugestões ficam **aguardando revisão**. Aprovação/rejeição, ajuste manual IN/OUT, divisão/união e exportação de vídeo continuam para as Fases 1D/1E. O original não é alterado.

## Medições sonoras

FFmpeg decodifica o stream escolhido para **PCM mono/8 kHz em fluxo**. São lidas janelas de **0,5 s**, sem manter o áudio inteiro na memória. NumPy calcula RMS e pico em dBFS. Há limite de oito faixas por análise sonora e uma tarefa pesada por vez, com até duas tarefas ativas/enfileiradas na fila compartilhada com ASR/downloads.

- Silêncio: RMS abaixo do limiar configurado (padrão −45 dBFS), conservando intervalos de pelo menos 1 s.
- Energia alta: RMS acima de `max(−20, mediana ativa + 10 dB)` e pico acima de −12 dBFS.
- Variação brusca: aumento de RMS de pelo menos 12 dB com nível atual acima de −35 dBFS; entradas a partir do silêncio só geram esse sinal se forem suficientemente fortes (acima de −18 dBFS).
- Eventos são espaçados por pelo menos 2 s por faixa. Curvas de exibição têm no máximo 500 pontos, agregados por máximo de energia/pico.
- Palavras por minuto de mídia e número de trechos são derivados da transcrição. Não se apresentam como identificação acústica de falantes ou diarização.

Essas medidas são aproximações para decupagem: a conversão mono/8 kHz limita banda e pode alterar níveis/transientes. **Não são LUFS, true peak, medição multicanal original nem waveform de amostras.** “Silêncio” é abaixo do limiar nessa representação. Um som forte não prova que houve grito, susto ou ação interessante.

## Heurísticas e classificação

O modo local procura expressões explícitas de reação, humor, susto, divergência, falha, revelação, emoção, história, informação, tensão e fala sobre jogada. Regras são transparentes e não compreendem toda a narrativa, sarcasmo ou contexto visual. O perfil dá pequenos ajustes de peso às categorias pertinentes.

A pontuação textual parte de 35 e varia com expressões reconhecidas; o perfil acrescenta até 6 e medidas próximas de áudio podem acrescentar 8. Scores são limitados ao intervalo 0–100. Eventos somente sonoros recebem **32/38** e confiança **0,25**. Evidência textual local usa confiança **0,55**; provedores são limitados a **0,8**. Esses números são estimativas de priorização, não probabilidades calibradas nem previsões de viralização.

Cada sugestão inclui ID, título sugerido, categoria, IN/OUT/duração, descrição, justificativa, gancho sugerido, trecho relevante, score, confiança, evidências, inferências, avisos, provedor e status. Citações textuais são montadas da fonte original pelos IDs; não são aceitas citações inventadas pelo modelo. Medidas acústicas incluem stream, timestamp, RMS/pico e variação. Interpretações e títulos continuam sujeitos a erro e revisão.

Limites são expandidos para incluir segmentos completos; trechos adjacentes sem pontuação final e com pausa de até 1,2 s são agrupados para evitar frases partidas. Isso é uma heurística, não alinhamento linguístico perfeito. Se a unidade não cabe na duração máxima ou não pode satisfazer a mínima, a sugestão é descartada. Não se cortam frases artificialmente para forçar um resultado.

Antes do ajuste de contexto, a pré-seleção mantém até duas candidatas por faixa temporal de tamanho mínimo e até `max(200, máximo_de_sugestões × 20)` candidatas por score. Um índice temporal evita varrer toda a transcrição para cada intervalo. Depois, supressão por score remove sobreposições; evidências adicionais só entram se couberem no intervalo sobrevivente. Isso pode descartar um momento diferente muito próximo; ajuste durações e revise a gravação. Nenhum resultado também é válido.

## Provedores opcionais

**OpenAI:** endpoint fixo `https://api.openai.com/v1/responses`, JSON Schema estrito, `store=False`, sem ferramentas de modelo. Informe um modelo disponível na sua conta e a chave apenas para a execução. O cliente não usa chave do ambiente/arquivo e não altera conta/permissões. `store=False` não substitui as políticas de dados da conta/provedor. O uso pode gerar cobrança conforme sua conta.

**Ollama:** endpoints `/api/show` e `/api/chat` em `127.0.0.1`, porta configurável, modelo já instalado, schema JSON, duas threads e `keep_alive=0`. Nenhum modelo é baixado. Tags com “cloud” e metadados de execução remota conhecidos são rejeitados. Use um servidor/modelo local sob seu controle; o aplicativo não controla a configuração interna do serviço Ollama.

Ambos exigem **consentimento por execução antes de enviar a transcrição**. Vídeo/áudio e caminhos do arquivo não entram no payload do provedor. Enviam-se trechos com IDs e tempos globais, perfil/finalidade e instruções de análise. Blocos têm até 300 s de intervalo entre inícios, 80 trechos ou aproximadamente 12 mil caracteres de JSON, com sobreposição dos dois últimos trechos. Todo texto elegível é coberto; um trecho individual grande demais é rejeitado antes de enviar qualquer bloco.

A interface informa quantidade de caracteres/blocos e permite limite de até 200 blocos/requisições (padrão 100). Não é uma estimativa de tokens/custo, e sobreposição repete texto. Respostas são limitadas a 2 MiB, com timeout e tratamento de erro/refusal/incompletude. IDs citados precisam existir no bloco e intersectar o intervalo proposto; tempos são globais, não relativos ao bloco.

Não há retries automáticos ou reaproveitamento de blocos semânticos parciais após falha. Cancelar encerra o processo/cliente local, **sem garantir cancelamento de uma requisição já recebida pelo provedor ou seus custos**. Os testes desta rodada não fizeram chamadas reais a esses provedores; não é alegada compatibilidade validada com todos os modelos.

Referências consultadas: [Structured Outputs OpenAI](https://developers.openai.com/api/docs/guides/structured-outputs), [Structured Outputs Ollama](https://docs.ollama.com/capabilities/structured-outputs) e [API Chat Ollama](https://docs.ollama.com/api/chat).

## Segurança, persistência e cache

- Credencial `SecretStr` excluída do dump público. É mantida brevemente no controle em memória e enviada ao worker por stdin; não vai a argumentos, ambiente, request.json, SQLite, cache, log ou relatório. Controles são limpos após envio/cancelamento/fim.
- Erros HTTP não propagam o corpo bruto, credencial, headers ou prompt. Texto transcrito é tratado como dado não confiável; o modelo não recebe ferramentas/URLs configuráveis para executar instruções do conteúdo.
- URLs do OpenAI são fixas, redirects não são seguidos e proxies implícitos do ambiente são desabilitados. Ollama é limitado a loopback/porta; chave OpenAI não é enviada ao Ollama.
- Tarefas usam a fila persistida existente, com progresso por quantidade de áudio processado e blocos concluídos. Pesos de etapa são 60% áudio, 35% texto/provedor e restante validação; não estimam tempo restante. Etapas desativadas podem avançar de imediato.
- O resultado só é aplicado após verificar revisão e digest das fontes. Cancelamento/falha/interrupção preserva sugestões anteriores. A API bloqueia mutação das fontes durante o processamento.
- Nova transcrição, mídia diferente ou troca de streams invalida sugestões antigas. Configurações e resultados permanecem no projeto para reabrir depois.
- Medições por faixa ficam em `.local/analysis/audio-cache`, por caminho/tamanho/mtime/duração/stream. Resultados completos usam o cache compartilhado em `.local/transcription/cache`, com digest do texto/fontes, opções e versão do algoritmo. Consentimento e chave não mudam a chave do cache; provedores ainda exigem autorização para uma nova execução.
- Trabalho temporário usa a pasta protegida do supervisor existente em `.local/transcription/work`. A chave nunca é escrita ali. Continua sem quota/evicção de cache ou retomada de tarefa parcial.

## Validação desta entrega

**112 testes aprovados em 17,00 s** na execução final, com ASR nativo habilitado; build TypeScript/Vite e verificação de dependências aprovados. Os 41 novos casos/variações cobrem análise e provedores, além dos 71 anteriores.

1. FFmpeg/PCM reais em duas faixas; picos comparados com `astats` independente. Compressão AAC pode produzir transientes diferentes do pico teórico da senoide, por isso o teste usa a referência decodificada.
2. Fixture de 90 s com pulsos separados e texto sintético explicitamente identificado: três sugestões, duas faixas, dois eventos por faixa, persistência e cache. Smoke inicial demorou cerca de 0,74 s; execução final com medições em cache, cerca de 0,54 s. Não é benchmark de OBS real longo.
3. Áudio real sem transcrição gerou somente eventos genéricos, com confiança baixa e sem diálogo/ações inventados.
4. Texto puro sem áudio, limites/durações, blocos com sobreposição, referências falsas, NaN, schemas inválidos, supressão e rejeição de aprovação automática.
5. Cancelamento com processo controlado preservou sugestões anteriores, inclusive uma aprovada em fixture de contrato. A infraestrutura já tem testes nativos de cancelamento ASR/Job Objects.
6. `httpx.MockTransport` verificou OpenAI/Ollama, payloads, erro/refusal/incompletude, ausência de chave no corpo do prompt e bloqueio de modelo remoto conhecido. Não equivale a inferência ao vivo.
7. Chave sentinela ausente de arquivos, argumentos, ambiente, histórico, projetos e mensagens; controle em memória limpo.
8. Chrome: execução local com perfil Entrevista, filtro por categoria, evidências/inferências, curvas, prévia de 11,500 s a OUT 29,500 s (pausa observada em 29,521 s) e OpenAI sem consentimento mantendo execução bloqueada. Nenhuma chave real foi informada ou requisição externa executada.

Script reproduzível: `.venv/Scripts/python.exe -X utf8 scripts/validar_analise.py`. Relatórios: `.local/analysis-smoke.json` e `.local/tests-phase1c.xml`. Todos os arquivos gerados ficam ignorados pelo Git. Serviços de validação são encerrados pelo script do projeto.

## Próximo marco

**Fase 1D:** aprovação/rejeição, ajuste manual IN/OUT, criação/divisão/união de cortes, waveform de amostras e timeline completa de revisão. Depois, Fase 1E para MP4/XML e legendas remapeadas, com validação real no Premiere. Benchmark OBS longo, validação ao vivo dos provedores e quota de cache permanecem pendentes.
