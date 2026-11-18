# Instalar em um PC Windows novo

Guia para o código publicado em https://github.com/patrickbotarick/Leonida-Clip-Studio . Não é necessário ter Codex, VS Code, Adobe Premiere, conta OpenAI, CUDA ou placa NVIDIA para usar o fluxo básico local.

## 1. Instalar três pré-requisitos

Use **Windows 10/11 de 64 bits, arquitetura x64**. ARM64 não foi validado. Os instaladores abaixo são executados por você; o projeto não instala programas globais ou drivers automaticamente.

| Pré-requisito | O que instalar | Link oficial |
|---|---|---|
| Python | **Python 3.12 x64**, com pip e venv. Marque **Add Python to PATH** e mantenha o Python Launcher quando oferecido. Não use Python 32 bits, 3.13/3.14 ou o Python embutido no Blender para este lock validado. | [Python para Windows](https://www.python.org/downloads/windows/) · [instalador x64 da versão 3.12.10](https://www.python.org/downloads/release/python-31210/) |
| Node.js | **24 LTS x64**, incluindo npm e a opção de PATH padrão. A linha 22 é aceita a partir de 22.12. Não é necessário instalar ferramentas de compilação adicionais do Node. | [Node.js](https://nodejs.org/en/download) |
| Runtime Microsoft | **Microsoft Visual C++ Redistributable v14 x64**, necessário às bibliotecas nativas de transcrição/PyAV. Se já estiver instalado, use a opção de atualização/reparo oferecida pelo instalador. Não é o Visual Studio completo. | [Microsoft — versões suportadas e download x64](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist/) |

Python 3.12.10 é uma opção com instalador tradicional Windows x64; versões de manutenção posteriores da linha 3.12 podem ser obtidas pelos canais oficiais que as disponibilizem. A versão usada no teste local foi 3.12.14, com o mesmo ABI 3.12. Feche e reabra os terminais depois de instalar Python/Node. Reinicie o Windows se o instalador do runtime solicitar.

Para conferir no Prompt de Comando ou PowerShell:

```text
py -3.12 --version
node --version
npm.cmd --version
```

Espaço: reserve pelo menos **5 GB livres** para ferramentas/pacotes/cache inicial, mais espaço para seus vídeos e exportações. Memória: 8 GB é um ponto de partida prático; transcrição de modelos maiores pode precisar de mais. O fluxo padrão usa CPU e duas threads; os testes desta máquina não são garantia de desempenho de outro hardware.

## 2. Baixar e extrair o projeto

1. Abra o [repositório](https://github.com/patrickbotarick/Leonida-Clip-Studio).
2. Clique **Code → Download ZIP**.
3. Extraia **todos** os arquivos para uma pasta local curta, por exemplo `C:\LeonidaClipStudio`. Não execute de dentro do ZIP, da pasta Program Files ou de uma unidade de rede.
4. A pasta correta contém `README.md`, `backend`, `frontend`, `scripts` e os arquivos `.bat`.

Git é opcional. Se preferir e já tiver Git instalado:

```powershell
git clone https://github.com/patrickbotarick/Leonida-Clip-Studio.git C:\LeonidaClipStudio
```

## 3. Configurar uma vez

Dê dois cliques em **Configurar Leonida Clip Studio.bat**. Mantenha a janela aberta e aguarde a mensagem **Configuracao concluida**. A primeira configuração exige internet e pode levar vários minutos.

O script:

- Confere Python 3.12 x64 e Node/npm compatíveis.
- Cria `.venv` na própria pasta do projeto, sem pacotes globais.
- Instala as versões fixadas em `backend/requirements-lock.txt`, usando wheels binários. Não exige MSVC Build Tools para compilar dependências.
- Baixa FFmpeg/FFprobe portáteis para `.tools`, compara o SHA256 publicado e testa o executável. Reutiliza o pacote local em configurações posteriores.
- Executa `npm ci` a partir de `frontend/package-lock.json` e compila a interface em `frontend/dist`.
- Importa efetivamente Faster Whisper, CTranslate2, PyAV, ONNX Runtime e demais módulos; verifica FFmpeg/FFprobe, encoders H.264/AAC, interface e gravação na pasta de dados.

Não copie `.venv`, `node_modules` ou `.tools` deste computador de trabalho para casa: recrie-os pelo script. Não copie o banco para substituir um banco já existente sem backup. A instalação básica **não baixa pesos Whisper** e não usa serviços de IA pagos.

Se Python não estiver no PATH, abra PowerShell na pasta e indique o executável instalado:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\configurar.ps1 -PythonExe 'C:\caminho\Python312\python.exe' -DownloadFFmpeg
```

O Bypass acima aplica-se somente a esse processo; não altera a política global do Windows. O caminho é um exemplo: use o arquivo real da instalação Python 3.12. Não é necessário executar o aplicativo como administrador.

## 4. Abrir, testar e encerrar

1. Dê dois cliques em **Abrir Leonida Clip Studio.bat**. O navegador abrirá em `http://127.0.0.1:8765`.
2. Crie um projeto com um MP4 H.264/AAC curto. O arquivo é referenciado, sem duplicação automática.
3. Se quiser testar sem transcrição pesada, importe um SRT/CSV na aba Texto, crie um corte manual, salve, aprove e use Exportar.
4. Para encerrar, execute **Encerrar Leonida Clip Studio.bat** ou pressione Ctrl+C na janela do serviço. Fechar apenas o navegador não encerra o serviço.
5. Para diagnosticar, execute **Verificar Leonida Clip Studio.bat**. O diagnóstico deve mostrar `ok: true`.

Depois da instalação, reprodução, importação de texto, análise local, edição e exportação funcionam offline. O navegador continua dependendo dos codecs disponíveis: MKV/MOV/WEBM podem ser lidos pelo FFprobe sem serem reproduzíveis no player. Para o primeiro teste, use MP4 H.264/AAC.

## 5. Ativar transcrição e IA opcionais

- **Faster Whisper local:** selecione as faixas em Áudio e, em Texto, escolha Tiny/CPU/Econômico. Use o botão de download e autorize obter os pesos do Hugging Face. Tiny ocupa aproximadamente 75 MB. Teste um trecho de até 30 s primeiro. Após o download, o modelo é reutilizado offline.
- **GPU:** não é requisito. A máquina de desenvolvimento usou CPU para Whisper; GPU depende de bibliotecas CUDA/cuDNN compatíveis. Não instale CUDA por tentativa para conseguir abrir o app. Consulte o diagnóstico e mantenha CPU se não houver bibliotecas validadas.
- **OpenAI:** requer conta/chave e cobrança do próprio provedor; não acompanha este projeto. A chave é informada no painel por execução, não em arquivos ou no GitHub. Autorize envio de texto antes de analisar.
- **Ollama:** servidor/modelo local são opcionais e separados. O projeto não os instala. Os adaptadores têm testes de contrato; inferência real depende da sua configuração.
- **Premiere:** só é necessário para importar/revisar o XML. Não é necessário para criar MP4, CSV/JSON/TXT ou SRT.

## Problemas comuns

| Sintoma | Ação |
|---|---|
| Python ausente/abre Microsoft Store | Instale Python 3.12 x64 de fato; feche/reabra o terminal. Use `-PythonExe` se necessário. Um alias WindowsApps não é uma instalação Python. |
| Python/venv de versão errada ou pasta copiada de outro PC | Com o serviço fechado, renomeie somente a pasta `.venv` desse projeto e configure novamente com Python 3.12 x64. Preserve `.local`, que contém projetos. |
| DLL ausente, WinError 126/127, falha em CTranslate2/ONNX/PyAV | Instale/repare o Visual C++ Redistributable x64 pelo link Microsoft. Não baixe DLLs avulsas de sites de terceiros. Execute Verificar novamente. |
| Node/npm não reconhecido | Instale Node 24 LTS x64 com npm/PATH; abra uma nova janela de terminal. |
| Download/checksum FFmpeg falhou | Confira internet/proxy e execute Configurar novamente. O pacote não é instalado quando o checksum diverge. |
| Instalação pip sem wheel compatível | Confirme Python **3.12 x64**. O lock exige pacotes binários dessa plataforma. Não tente resolver instalando um compilador global. |
| Interface não compilada/tela inicial ausente | Execute Configurar e confira a saída de `npm ci`/build. A pasta `frontend/dist` é gerada localmente e não vem versionada. |
| Porta 8765 ocupada | Use Encerrar para a instância deste projeto. Não mate um processo desconhecido. Porta alternativa: `.\.venv\Scripts\python.exe scripts\launch.py --port 8766`. |
| Vídeo movido | Use relocalizar mídia. Copiar só o banco não copia o vídeo original; ele deve existir no PC de casa. |
| Permissão/espaço de disco na exportação | Escolha uma pasta local existente e gravável, com espaço para novos MP4. O app cria uma subpasta por lote e não sobrescreve anteriores. |
| Proxy corporativo/certificado | Configure a rede/certificados pelo canal apropriado. Não desative validação TLS nem proteção do Windows para instalar. |

## Dados e atualização

`.local` guarda projetos SQLite, modelos, caches e exportações padrão. Essa pasta não é publicada no GitHub. Faça backup de `.local/projects.sqlite3` com o serviço encerrado e mantenha os originais disponíveis. Para transportar projetos, copie o backup de dados conscientemente e use relink se os caminhos mudarem.

Antes de atualizar, encerre o app e faça backup. Atualize os fontes sem apagar `.local`; rode Configurar novamente para sincronizar dependências/build. Não execute duas instâncias sobre a mesma pasta de dados. Um ZIP novo em outra pasta começa com um banco vazio, o que é esperado.

## O que foi comprovado

Na Fase 1F foi feita uma cópia dos fontes sem `.venv`, `.tools`, `node_modules`, `dist`, banco ou modelos. O instalador recriou esses componentes e aprovou todos os imports nativos/encoders. É um teste de instalação isolada no mesmo Windows, que já possui os três pré-requisitos globais; **não substitui um teste em VM ou no PC de casa**. Os modelos e dados privados não acompanham o repositório. A CI Windows repete instalação/build/testes sem baixar modelos.
