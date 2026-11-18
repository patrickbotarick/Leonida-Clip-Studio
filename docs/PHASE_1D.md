# Fase 1D — Decupagem visual

Entrega em 18/11/2026, versão 0.1.0. **GO COM RESSALVAS**: edição local não destrutiva funcional, sem precisão de quadro garantida pelo player. Exportação dos cortes pertence à Fase 1E.

## Como usar

1. Inicie por `Abrir Leonida Clip Studio.bat` e abra um projeto. O painel **Decupagem** fica abaixo do monitor de origem.
2. Escolha a faixa em **Waveform** e clique em **Gerar waveform**. É uma leitura real de PCM daquela faixa, independente da seleção usada na transcrição. O envelope completo fica em cache e a interface consulta apenas a janela visível. Tarefas mostram progresso e podem ser canceladas.
3. Clique numa região ou na lista de revisão para selecionar e posicionar o player. Zoom, deslocamento da janela, **Ver playhead** e **Ir** navegam por segundos absolutos do original.
4. Edite IN/OUT como segundos ou `HH:MM:SS.mmm`, ou arraste uma borda/região. **I** marca IN e **O** marca OUT na posição atual; atalhos não atuam em campos de edição. O passo ←/→ usa o FPS nominal. Espaço reproduz/pausa fora dos controles de formulário. Confirme em **Salvar ajuste**, ou **Descartar**.
5. A opção de alinhar à transcrição expande os pontos para os limites de frase detectados. Sem essa opção, os pontos manuais são mantidos e o editor avisa quando atravessam segmentos de fala.
6. **Corte manual** cria um rascunho. Para dividir, selecione um corte e posicione o playhead estritamente dentro dele. Para unir, marque de 2 a 20 cortes na lista; confira o intervalo proposto. Havendo espaços entre eles, é necessário marcar **Incluir eventuais lacunas**. A união inclui todo o conteúdo entre IN mínimo e OUT máximo; não remove lacunas do arquivo.
7. Os botões **Pendente**, **Aprovado** e **Rejeitado** aplicam revisão à seleção. Filtros por status, categoria, score, duração e texto não apagam nem revisam cortes. Seleções existentes continuam selecionadas ao filtrar; a contagem informa quantos cortes serão afetados.
8. **Desfazer/Refazer** (Ctrl+Z/Ctrl+Shift+Z fora dos campos) preserva as últimas 100 operações mesmo após reabrir. Uma nova operação após desfazer elimina o ramo de refazer. Remover um corte pode ser desfeito.

Rascunhos não são salvos automaticamente: saída de projeto/página interna e alterações de fontes são bloqueadas até salvar/descartar. Fechar/recarregar a aba aciona a proteção `beforeunload` do navegador. Projetos salvos usam revisões; um comando desatualizado recebe HTTP 409 e não sobrescreve outra alteração. Nesse caso, copie os valores que queira conservar, descarte o rascunho e reabra o projeto para obter a revisão atual.

## Semântica dos cortes e preservação

- Cortes manuais não recebem score/confiança inventados. Mudanças em IN/OUT retiram as estimativas antigas e devolvem o corte a pendente; evidências fora do intervalo passam a contexto anterior. Notas e título, sozinhos, não invalidam o intervalo revisado.
- Divisão/união cria novos IDs, registra os cortes de origem e exige revisão nova. Nenhuma dessas ações altera a mídia original.
- Sobreposições manuais são permitidas e indicadas na lista; o editor não remove silenciosamente trabalho revisado. União é uma ação explícita.
- Reanálise das mesmas fontes arquiva o conjunto anterior, preserva cortes manuais/editados/aprovados/rejeitados e descarta sugestões novas que cruzem esses intervalos. Sugestões novas permanecem pendentes. Limite de 1.000 cortes ativos.
- Troca de faixa ou transcrição arquiva o conjunto anterior, retém cortes manuais/revisados com status pendente e evidências históricas, e remove sugestões ainda não revisadas. Estimativas são invalidadas. Mídia diferente limpa os cortes ativos e mantém seu arquivo histórico.
- **Conjuntos anteriores** permite baixar JSON e restaurar conjuntos com contexto compatível. A restauração arquiva o conjunto atual e reinicia undo/redo. Os últimos 50 conjuntos aparecem na interface; não há expurgo automático. O JSON de histórico é consulta da decupagem, não exportação de vídeo/XML da Fase 1E.

## Implementação

`backend/editing.py`, `backend/waveform.py`, `backend/waveform_worker.py`, integração em `main.py`, `database.py`, `processing.py` e `frontend/src/CutEditor.tsx`. Waveform: mono/16 kHz, janelas base de 128 amostras (8 ms), pares float32 min/max em disco e níveis agregados por fator 2. Consultas de 4 a 4.000 pontos escolhem nível por viewport. Memória é limitada por blocos, sem carregar PCM de duas horas; cerca de 14,4 MB por faixa/duas horas em disco. Cache é separado das curvas RMS de 1C.

## Validação executada

**Automatizada:** 126 testes aprovados em 27,01 s, zero skips/falhas, com `LEONIDA_TEST_ASR=1`. Relatório `.local/tests-phase1d.xml`. Inclui os testes anteriores de importação, ASR Tiny offline, segurança local e análise, além de:

- IN/OUT inválido, duração inferior a um quadro nominal, aprovação e reabertura, conflito de revisão, histórico e ramificação de redo.
- Divisão, união adjacente, autorização de lacunas, IDs, score nulo, sobreposição e alinhamento opcional à frase.
- Arquivamento de fontes anteriores, restauração compatível/incompatível e preservação de revisão/manual na reanálise.
- Waveform real calibrada contra PCM decodificado independentemente; extrema preservados em todos os níveis; resposta limitada por pontos; cache reutilizado; geração sem incrementar revisão.
- Mídia sintética real de 7.205 s com duas faixas: cache de uma faixa abaixo de 15 MB, consulta no final da gravação, cancelamento da outra faixa durante decodificação, edição de corte permitida durante waveform e troca de fontes bloqueada.
- Histórico limitado a 100 operações e seleção inválida sem alterações parciais.

**Interface real no Chrome:** fixture de 90 s explicitamente sintética, geração/cache da waveform da faixa 1, seleção/seek, edição de OUT e aprovação, bloqueio de saída com rascunho, reabertura conservando revisão; arraste de OUT de 28,500 s para 27,166 s como rascunho (descartado), divisão em 20 s, união e dois desfazeres restaurando o corte aprovado. Layout desktop verificado em 1440 × 900; viewport temporário restaurado. Imagem em `.local/phase1d-desktop.jpg`. Os painéis de detalhes e lista têm rolagem interna no layout compacto.

Build TypeScript/Vite e `pip check` aprovados. Nenhum provedor externo foi chamado nem foi usado conteúdo real como se fosse fixture sintética.

## Ressalvas e próxima fase

O player usa o áudio padrão do navegador, mesmo quando outra faixa está exibida na waveform; escuta individual continua em **Áudio**. O envelope é mono e não representa canais separados, espectrograma, LUFS ou true peak. Arquivos sem áudio não fornecem waveform. Cache e históricos ainda não têm cota automática de disco. Identidade de fonte usa metadados/assinatura, não hash integral da mídia.

Seek, prévia limitada em OUT e passo por FPS nominal dependem do navegador; não comprovam corte preciso, timecode drop-frame nem VFR. Gravação OBS longa real ainda merece validação manual. A próxima fase é **1E**, para MP4 individual/lote, XML FCP7/Premiere e relatórios/legendas remapeadas, com testes próprios de precisão.
