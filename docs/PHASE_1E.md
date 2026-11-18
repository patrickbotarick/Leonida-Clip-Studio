# Fase 1E — Exportações

Entrega em 18/11/2026, versão 0.1.0. **GO COM RESSALVAS** para exportação local. XML FCP7 gerado e validado estruturalmente; sua importação no Premiere continua pendente. Não há garantia de compatibilidade completa.

## Fluxo pela interface

1. Aprove os cortes no editor de decupagem. Salve ou descarte qualquer ajuste em aberto.
2. Clique em **Exportar**, ao lado de **Novo projeto**. O painel inclui somente cortes aprovados; selecione um para exportação individual ou vários para lote.
3. Selecione os formatos: MP4, XML FCP7, JSON, CSV, TXT e SRT. Os relatórios descrevem os intervalos aprovados; o manifesto também registra as características dos arquivos efetivamente produzidos.
4. Escolha as faixas de áudio de exportação. São independentes da seleção de transcrição e permanecem separadas no MP4. Sem seleção, o MP4 contém somente vídeo. Para XML, os canais selecionados referenciam a mídia original, com mapeamento explícito por canal.
5. Escolha o método MP4 e a qualidade. **Recodificar** é o padrão: H.264/AAC, duas threads de CPU, CRF 18/20/23 na interface, sem redimensionamento. **Cópia rápida** exige confirmação explícita e começa no quadro-chave anterior, podendo incluir conteúdo extra. A precisão e as legendas desse modo são aproximadas.
6. Para XML, confirme que a fonte usa FPS constante (CFR). Escolha **Consolidada**, para remover lacunas entre os cortes na sequência, ou **Original**, para preservar suas posições. Esse modo se aplica ao XML, relatório e SRT da sequência; não gera um MP4 concatenado.
7. Escolha uma pasta existente pelo seletor Windows ou cole seu caminho absoluto local. Deixe em branco para usar `.local/exports`. Cada lote cria uma subpasta nova com nome do projeto e ID único; não há substituição de arquivos anteriores.
8. Clique em **Atualizar prévia**, confira quantidade, duração, faixas, avisos e nomes dos arquivos. Qualquer alteração de opções/revisão invalida a prévia. Clique em **Exportar N corte(s) aprovado(s)** para iniciar.
9. O progresso vem do FFmpeg e do número de cortes. É possível cancelar ou fechar/reabrir o painel enquanto a tarefa continua. Os arquivos são publicados somente após a conclusão do lote. O histórico mostra os lotes concluídos e permite baixar arquivos já gravados na pasta.

## Arquivos produzidos

| Arquivo | Conteúdo e base de tempo |
|---|---|
| `001-titulo.mp4`, etc. | Um arquivo por intervalo aprovado; vídeo original e faixas selecionadas |
| `001-titulo.srt`, etc. | Legendas intersectadas com o corte e recalculadas relativamente ao clipe |
| `sequencia.xml` | xmeml versão 5/FCP7, referência ao original, IN/OUT de origem, posições de sequência, canais de áudio, links e marcadores nomeados |
| `sequencia.srt` | Legendas com tempos recalculados para a sequência consolidada ou original |
| `decupagem.json` | Cortes aprovados, origem/metadados, notas/evidências e mapeamento da sequência |
| `decupagem.csv` | Timestamps numéricos em segundos, título/categoria/status/score/nota e posições da sequência; BOM UTF-8 e proteção de células que iniciam fórmulas |
| `decupagem.txt` | Lista legível dos cortes e notas/transcrição relevante |
| `manifesto.json` | Revisão e opções usadas, cortes, avisos, arquivos/tamanhos e metadados medidos de cada MP4 |

Legendas que atravessam IN/OUT são limitadas ao intervalo; texto não é reescrito ou alinhado por palavra. Um segmento que cruza dois cortes pode aparecer em ambos, com seus tempos locais. Eventos vazios após arredondamento a milissegundos são descartados. Um projeto sem transcrição produz SRT vazio, sem texto inventado.

Quando XML está incluído, o SRT/relatório da sequência usa os mesmos pontos arredondados em quadros do XML. SRT individual acompanha o intervalo do MP4. No modo rápido, o ponto de origem do quadro-chave e o deslocamento de início do vídeo medido por FFprobe entram no cálculo, mas a sincronização continua aproximada. XML e relatório mantêm o intervalo aprovado, sem incorporar automaticamente o conteúdo extra do MP4 rápido.

## Precisão e restrições

- MP4 recodificado usa seek preciso do FFmpeg e mantém os timestamps via `fps_mode=passthrough`. Em CFR, os limites continuam discretizados nos quadros disponíveis: o último quadro anterior ao OUT tem sua duração inteira. A duração física pode diferir do intervalo solicitado por cerca de um quadro e/ou pacotes de áudio. A validação bloqueia desvio superior a dois quadros nominais ou 120 ms, o que for maior; isso é uma tolerância de verificação, não uma promessa de erro mínimo universal.
- A verificação pós-encode confirma vídeo legível, resolução, quantidade de faixas, canais e duração. Nomes/idioma das faixas são escritos; o manifesto informa os resultados medidos. Recodificação usa AAC e pode converter o formato de amostragem do codec de origem. Cópia rápida mantém os codecs suportados, sem misturar as faixas.
- MP4 rápido aceita H.264/HEVC/AV1/MPEG-4 e áudio AAC/MP3/AC3/EAC3/ALAC. Outros codecs exigem recodificação. Falha não dispara mudança automática de método nem sobrescreve lotes anteriores.
- Recodificação SDR de fontes HDR identificadas como PQ/HLG é bloqueada para evitar conversão de cor silenciosa. Não há tone mapping, reenquadramento vertical, aceleração NVENC nem escolha de encoder nesta fase.
- XML aceita FPS inteiro de 1–120 ou racional representável como timebase × 1000/1001. Foram testados 30000/1001 e 24000/1001. Pontos são arredondados ao quadro mais próximo, sem somar arredondamentos de durações independentes. Timecode inicial é zero/NDF; offsets de sequência e drop-frame não são representados.
- XML requer CFR confirmado, pixels quadrados, fonte progressiva ou field order desconhecida, canais conhecidos, até 32 canais de origem e taxa de amostragem comum entre faixas. A confirmação de CFR não faz análise exaustiva de timestamps para detectar VFR. Não use XML desta versão para uma fonte VFR sem conversão/validação apropriadas.
- Sobreposição aprovada é mantida entre arquivos individuais e repete conteúdo na sequência consolidada. XML/SRT no modo de posições originais rejeita sobreposição, para não criar uma montagem ambígua em uma única pista de vídeo.
- XML não copia nem embute o original. Mover a mídia exige relink no editor de destino. Caminhos usam URI de arquivo com escapes; arquivos em unidades de rede/UNC e diferentes configurações de áudio precisam de validação adicional no Premiere.
- Não há MP4 de sequência consolidada, legendas embutidas, transições ou preservação de efeitos de um NLE.

## Persistência, publicação e recuperação

`exports.py` produz um plano a partir da revisão atual, somente com cortes aprovados, limites válidos e seleção de streams existente. Um token do plano vincula projeto, revisão, fontes e opções. A fila pesada existente executa um único worker de cada vez e aceita até duas tarefas ativas/enfileiradas; alterações do projeto ficam bloqueadas enquanto ele exporta.

`export_worker.py` grava somente em `.leonida-ID.partial`, na pasta de destino, com um marcador de propriedade. Nenhum arquivo preexistente é aberto para escrita; FFmpeg usa `-n`. Cada arquivo é validado e o manifesto é concluído antes da publicação. `export_storage.py` valida o lote e renomeia a pasta no mesmo volume para um nome final único. No Windows, a operação falha se o destino já existir. O registro no projeto e a tarefa concluída são gravados juntos e de forma idempotente no SQLite.

Cancelamento encerra worker e FFmpeg pelo mecanismo existente de Job Objects. O estado terminal de falha/cancelamento só é anunciado após a limpeza normal do staging. A limpeza verifica nome esperado, caminho resolvido e marcador de propriedade, sem apagar a pasta de destino ou exportações anteriores. Se o serviço for interrompido, a inicialização limpa staging próprio ou recupera um lote já publicado pelo manifesto. Exportações não são apagadas automaticamente; ainda não há cota de disco/limpeza pela interface.

O histórico do projeto registra a revisão exportada, pasta e formatos. Ele não altera aprovação, transcrição ou original. Links de download aceitam somente nomes publicados no lote e mantêm o caminho dentro de sua pasta. Credenciais de provedores não entram no plano, relatórios ou manifesto.

## Validação executada

**Suíte completa: 146 testes aprovados em 34,76 s**, sem skips/falhas, com ASR Tiny nativo habilitado. JUnit em `.local/tests-phase1e.xml`. Após o ajuste final de contagem de progresso, os **20 testes de exportação passaram em 6,02 s**, com relatório `.local/tests-exports-final.xml`. TypeScript/Vite, compilação Python e `pip check` aprovados.

Testes de 1E:

- Lote MP4 real, exportação individual, seleção e ordem de duas faixas, vídeo sem áudio, CRF padrão, duração/FPS/resolução e ausência de modificação do original por hash na fixture.
- Quadros inicial/final comparados por PyAV aos quadros da origem, com tolerância à recodificação. Identidade das duas faixas confirmada independentemente por FFT em PCM (880/440 Hz na ordem escolhida).
- MP4 rápido real com quadro-chave anterior e conteúdo extra, condicionado à autorização explícita.
- XML parseável, timebase NTSC/racional, IN/OUT e posições em quadros, links válidos, URI escapada, marcadores e mapeamento mono/estéreo. O teste de mapeamento estéreo é estrutural; não comprova interpretação pelo Premiere.
- SRT relativo, falas atravessando bordas, sequência com/sem lacunas, CSV protegido, cortes pendentes/rejeitados excluídos, revisão/token inválidos, nomes reservados e sobreposição.
- Cancelamento de worker/FFmpeg real com leitura cadenciada para observar o processo em andamento, limpeza restrita ao lote e preservação de arquivo vizinho; falha do encoder sem publicação; recuperação idempotente de lote publicado; staging interrompido e colisão de destino.
- Origem sintética de 7.205 s: exportação de 7201–7203 s, dois quadros a 1 fps, XML com source IN 7201 e sequence IN zero, SRT relativo de 0–2 s. Não é benchmark de uma gravação OBS pesada.

**Chrome:** fixture dedicada em `.local/fixtures/Fase 1E - video sintetico 29.97 duas faixas stereo.mp4`, 640 × 360, 30000/1001, dois tons estéreo e legendas explicitamente sintéticos. A interface mostrou somente dois cortes aprovados, excluindo um pendente; permitiu escolher todos os seis formatos, confirmar CFR e conferir a prévia de dez arquivos. O lote foi iniciado pela interface e sua conclusão/arquivos foram conferidos no backend/FFprobe. Resumo persistido em `.local/export-smoke.json`.

**Premiere:** instalado e aberto para o teste, com uma janela de novo projeto `TEST`; o usuário autorizou seu uso. Antes de modificar/importar o projeto, o controle de aplicativos foi interrompido pela tecla Escape. As ações visuais foram encerradas. Não foi realizada importação do XML e nenhum resultado de compatibilidade no Premiere é alegado. Não há captura final da interface de exportação nesta rodada, porque a automação visual foi interrompida.

## Reproduzir o teste local

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/validar_exportacao.py
$env:LEONIDA_TEST_ASR='1'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml=.local/tests-phase1e.xml
npm run build --prefix frontend
```

O primeiro comando cria um projeto novo com mídia sintética; não altera projetos reais nem sobrescreve a fixture existente. Abra esse projeto no app e exporte pela interface. Em outra máquina, configure previamente Python/FFmpeg/dependências pelos scripts do projeto.

## Referências técnicas

- [FFmpeg: seek, stream copy, mapeamento e timestamps](https://www.ffmpeg.org/ffmpeg.html).
- [Apple: Final Cut Pro 7 XML — encoding de sequências](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/FinalCutPro_XML/Basics/Basics.html).
- [Apple: catálogo de elementos, rate, sourcetrack e pathurl](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/FinalCutPro_XML/Elements/Elements.html).

Próxima etapa: **Fase 1F**, consolidação, teste manual do XML no Premiere, gravações OBS reais, VFR/timecodes e desempenho/recuperação em cenários ampliados.
