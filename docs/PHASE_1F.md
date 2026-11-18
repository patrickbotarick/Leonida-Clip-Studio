# Fase 1F — Consolidação do piloto e portabilidade Windows

18/11/2026 · versão 0.1.0 · **GO COM RESSALVAS** para o piloto local em CPU. A aprovação técnica refere-se aos fluxos testados abaixo; não equivale a certificar qualquer hardware/codec, VFR ou importação completa no Premiere.

## Entregas

- Instalador do projeto independente do Codex: Python 3.12 x64 e Node 24 LTS x64 (ou 22.12+) verificados antes de instalar. Removida a busca automática de runtime no cache do Codex; Python alternativo pode ser informado por `-PythonExe`.
- Dependências Python fixadas por lockfile e instaladas como wheels binários na `.venv`, sem compiladores/pacotes globais. Frontend por `npm ci`/lockfile. FFmpeg/FFprobe baixados em staging exclusivo, com SHA256, executável testado e limpeza com caminhos restritos.
- Diagnóstico que importa extensões nativas de verdade, identifica falha de DLL/runtime e testa FFmpeg/FFprobe, encoders H.264/AAC, frontend e gravação na pasta de dados. Novo **Verificar Leonida Clip Studio.bat**.
- [Guia Windows do zero](INSTALL_WINDOWS.md): links oficiais de Python/Node/Visual C++, instalação por ZIP, primeiro uso, modelos/IA opcionais, backup/relink e solução de problemas. Não exige Codex, VS Code, Git, GPU, CUDA ou Premiere para os fluxos locais básicos.
- Recuperação de exportações reforçada: tamanho dos arquivos validado contra o manifesto; erro após publicação mantém sinal de registro pendente; reinicialização recupera inclusive uma tarefa marcada como falha, sem duplicar o histórico. Staging bloqueado é sinalizado para repetir limpeza em nova inicialização, sem impedir a identificação do estado anterior.
- CI Windows com instalação real, build, `pip check`, auditoria npm, testes e JUnit. Inferência ASR é opt-in e não baixa modelos na CI.
- Repositório preparado para fontes/lockfiles/scripts/testes/documentos, mantendo `.local`, `.venv`, `.tools`, vídeos, modelos, caches e credenciais fora da publicação. Arquivos `.bat`/`.ps1` usam CRLF pelo `.gitattributes`.

## Verificação executada

| Verificação | Resultado |
|---|---|
| Suíte local com ASR Tiny real habilitado | **150 aprovados em 32,09 s**, zero falhas/skips |
| Instalação em cópia sem dependências locais prévias | Script concluído, todos os imports nativos e encoders aprovados |
| Suíte na instalação isolada, sem modelos | **147 aprovados e 3 skips ASR explícitos em 26,57 s**, zero falhas |
| Dependências Python | `pip check` aprovado no ambiente isolado |
| Frontend | `npm ci` e TypeScript/Vite aprovados |
| Segurança de dependências frontend | `npm audit`: zero vulnerabilidades reportadas na consulta da rodada |
| Mídia longa | Reexecutados testes de 7.205 s para importação, waveform, cancelamento e exportação perto do final |
| Recuperação ampliada | Testes novos de arquivo truncado, pasta bloqueada, falha de banco após publicação e pasta vizinha preservada |

Os relatórios locais estão em `.local/tests-phase1f.xml` e `.local/clean-room-phase1f/.local/clean-tests.xml`. Os testes do ambiente isolado não usaram `.venv`, FFmpeg, banco, modelos ou `node_modules` da instalação original. O cache de downloads do gerenciador de pacotes pode ser reutilizado, como numa instalação normal.

Esse ensaio ocorreu **no mesmo Windows com Python/Node/runtime Microsoft já disponíveis**, usando outra pasta e ambientes novos. Não é uma VM Windows recém-instalada nem um teste físico do PC de casa. A documentação lista esses pré-requisitos exatamente para permitir a reprodução em outra máquina. Nenhum programa global/driver foi instalado durante a rodada.

## Premiere: condição observada

O usuário orientou usar o projeto de testes já aberto, sem criar outro. Esse projeto foi mantido; nenhum projeto novo foi criado ou salvo pela automação. Ao tentar focalizar a janela, a automação recebeu timeout e o Windows expôs o título **“Não está respondendo”**. O processo não foi encerrado à força e os projetos reais não foram alterados.

Portanto, o XML permanece coberto por testes estruturais de frame rate, quadros, canais, referências, links e marcadores, mas a **importação nativa no Premiere não foi aprovada nesta rodada**. O aplicativo deixa essa ressalva explícita antes de exportar XML. Isso não impede os fluxos MP4/relatórios/SRT já testados.

## Limites que permanecem

- XML CFR/zero-NDF e seus canais precisam de conferência nativa; VFR, timecode de sequência, entrelaçamento e taxa de amostragem heterogênea não recebem promessa de compatibilidade.
- Gravações OBS reais longas/complexas e outras máquinas exigem medição própria; os testes longos usam mídias sintéticas identificadas.
- GPU/CUDA, modelos Base/Small e provedores OpenAI/Ollama ao vivo continuam opcionais, sem validação completa nesta configuração.
- Ainda não há cota/limpeza de cache pela interface, MP4 concatenado, proxy automático de reprodução incompatível ou reenquadramento vertical.
- Erros de disco/permissão são tratados sem sobrescrever arquivos existentes, mas espaço/disponibilidade do armazenamento continuam requisitos do Windows.

## Publicação e uso em casa

O usuário autorizou publicar o projeto em **patrickbotarick/Leonida-Clip-Studio** depois da validação. A publicação usa somente a árvore revisada de fontes e dependências declaradas. Dados locais, projeto Premiere, artefatos de teste e credenciais não acompanham o repositório. O histórico de CI deve ser consultado no GitHub para distinguir checks executados no runner remoto dos resultados locais relatados acima.

No PC de casa, siga o [guia de instalação](INSTALL_WINDOWS.md) e mantenha CPU/Tiny no primeiro teste de transcrição. Para abrir e exportar com transcrição externa, nenhum modelo/chave de IA é necessário.
