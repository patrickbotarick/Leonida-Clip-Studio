# Roadmap

| Fase | Estado | Entregas e condições de avanço |
|---|---|---|
| 0 — Fundação | Concluída nesta rodada | Diagnóstico, estrutura, React/TS/Vite, FastAPI/SQLite, identidade, scripts e documentação |
| 1A — Importação/reprodução | Funcional, com ressalvas de codec | Quatro contêineres via probe, referência original, múltiplas faixas, player para codecs do navegador, seleção e prévias. Falta proxy de reprodução incompatível e validação ampliada com OBS real |
| 1B — Transcrição | Funcional em CPU, com ressalvas | Faster Whisper em blocos, CPU int8, Tiny/Base/Small, idioma/perfis/threads, seleção/mixagem de faixas, download explícito, cache, cancelamento e tarefas persistidas. Tiny validado em inferência real; GPU bloqueada sem bibliotecas; ampliar testes com OBS real e modelos maiores |
| 1C — Motor de análise | Funcional local; provedores com ressalvas | Medições por faixa, heurísticas texto/áudio, perfis/finalidades/durações, classificação, evidências, contexto, deduplicação, cache e cancelamento. OpenAI/Ollama implementados com consentimento e testes de contrato; validação ao vivo pendente |
| 1D — Decupagem | Funcional com ressalvas de precisão do navegador | Timeline com zoom/pan, envelope PCM multirresolução por faixa, IN/OUT e arraste, marcação I/O, revisão, filtros, criação/divisão/união, histórico e preservação de ajustes na reanálise. 126 testes; ampliar validação com gravação OBS real e VFR |
| 1E — Exportação | Funcional local, XML com ressalvas | MP4 individual/lote preciso/rápido, faixas separadas, pastas exclusivas, progresso/cancelamento/recuperação, relatórios e legendas remapeadas. XML FCP7 estruturalmente testado; importação real Premiere pendente por interrupção da automação |
| 1F — Consolidação | Piloto validado com ressalvas | 150 testes locais, instalação isolada sem dependências locais prévias, verificação nativa de DLLs/encoders, recuperação de falha pós-publicação, documentação Windows do zero e CI. Importação real Premiere e hardware/VFR adicionais continuam ressalvas explícitas |

## Próxima rodada sugerida

1. Fase 1F: concluir importação do XML em um projeto de teste no Premiere, conferindo IN/OUT, sequência consolidada/original, links, marcadores e canais OBS.
2. Testar gravações reais longas e VFR, offsets de timecode e taxas de amostragem variadas; manter restrições explícitas onde não houver validação.
3. Consolidar usabilidade, falhas de disco/permissões, interrupções durante publicação, cotas de cache/exportações e medições de desempenho.
4. Validar fluxos opcionais OpenAI/Ollama com configuração autorizada, sem confundir contratos controlados com inferência real.
