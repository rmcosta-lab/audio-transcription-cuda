# Transcricao de audio

Este repositorio contem um script Python para transcrever audio para Markdown usando `faster-whisper`.

O script gera:

- transcricao com timestamps;
- texto corrido;
- metadados do arquivo, modelo e idioma.

## Requisitos

- Python 3.10 ou superior
- `uv` instalado

Para instalar o `uv` no Windows PowerShell:

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

Depois feche e abra o terminal novamente. Documentacao oficial: https://docs.astral.sh/uv/

## Instalar dependencias automaticamente

Na raiz do repositorio:

```powershell
uv run transcrever_audio.py --help
```

O arquivo `transcrever_audio.py` declara a dependencia `faster-whisper`, entao o `uv` cria/usa um ambiente isolado automaticamente.

Se o download falhar com `invalid peer certificate: UnknownIssuer`, rode o `uv`
usando os certificados do Windows:

```powershell
uv --system-certs run transcrever_audio.py --help
```

Use o mesmo prefixo para executar a transcricao:

```powershell
uv --system-certs run transcrever_audio.py
```

O script tambem usa o armazenamento de certificados do Windows para baixar o
modelo do Hugging Face. Por isso, use `--system-certs` tambem na primeira
execucao, quando o modelo ainda nao estiver no cache:

```powershell
uv --system-certs run transcrever_audio.py --model medium --device cuda --compute-type float16
```

Se a rede corporativa usar um certificado proprio, ele precisa estar instalado
em `Autoridades de Certificacao Raiz Confiaveis` do Windows. Nao desative a
verificacao SSL para contornar esse erro.

Se aparecer `Library cublas64_12.dll is not found or cannot be loaded`, a
execucao esta tentando usar CUDA sem as bibliotecas NVIDIA necessarias. Rode
em CPU, que nao exige CUDA:

```powershell
uv --system-certs run transcrever_audio.py --device cpu --compute-type int8
```

## Configurar GPU NVIDIA no Windows

Para usar CUDA, e necessario ter uma GPU NVIDIA compativel, o driver NVIDIA
atualizado, CUDA 12.x e cuDNN 9 para CUDA 12. As versoes atuais do
`faster-whisper`/`ctranslate2` usam cuBLAS para CUDA 12 e cuDNN 9.

Primeiro, verifique se o driver e a GPU estao disponiveis:

```powershell
nvidia-smi
```

Se o comando nao existir ou nao listar uma GPU NVIDIA, nao sera possivel usar
CUDA neste computador.

Instale o CUDA Toolkit 12.x pelo instalador oficial:

https://developer.nvidia.com/cuda-downloads

Escolha `Windows`, `x86_64`, sua versao do Windows e o instalador `exe`.
Prefira CUDA 12.x para este projeto; nao e necessario instalar o toolkit CUDA
completo se a intencao for executar apenas em CPU.

Depois instale o cuDNN 9 para CUDA 12:

https://developer.nvidia.com/cudnn

Se usar o pacote ZIP do cuDNN, adicione ao `PATH` do Windows a pasta `bin`
instalada, por exemplo:

```text
C:\Program Files\NVIDIA\CUDNN\v9.x\bin
```

O CUDA Toolkit normalmente adiciona automaticamente sua pasta `bin` ao
`PATH`. Caso necessario, confira tambem:

```text
C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\bin
```

Feche e abra o PowerShell novamente e valide as instalacoes:

```powershell
nvcc --version
where.exe cublas64_12.dll
where.exe cudnn_ops64_9.dll
```

Com as DLLs encontradas, execute a transcricao usando a GPU:

```powershell
uv --system-certs run transcrever_audio.py `
  --device cuda `
  --compute-type float16
```

Se ainda houver erro de DLL, volte para a execucao em CPU ou verifique se as
pastas `bin` do CUDA e do cuDNN estao no `PATH`.

Na primeira transcricao, o `faster-whisper` baixa o modelo escolhido. Isso exige conexao com a internet.

## Instalar dependencias manualmente

Se preferir manter um ambiente virtual local:

```powershell
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install faster-whisper
```

## Executar com o audio padrao

O script ja aponta para o audio usado nesta transcricao:

```powershell
uv run transcrever_audio.py
```

Isso gera:

```text
transcricao-audio-instrucao-handson.md
```

## Executar informando outro audio

```powershell
uv run transcrever_audio.py "C:\caminho\para\audio.m4a" -o transcricao.md
```

## Opcoes uteis

Usar outro modelo:

```powershell
uv run transcrever_audio.py --model medium
```

Autodetectar idioma:

```powershell
uv run transcrever_audio.py --language ""
```

Usar GPU, se o ambiente tiver CUDA configurado:

```powershell
uv --system-certs run transcrever_audio.py --device cuda --compute-type float16
```

O modo CUDA exige uma GPU NVIDIA compatível e as bibliotecas CUDA/cuBLAS
disponíveis no `PATH` do Windows. Sem isso, use CPU.

Desativar o filtro de silencio:

```powershell
uv run transcrever_audio.py --no-vad
```

## Exemplo completo

```powershell
uv run transcrever_audio.py `
  "C:\Users\plinh\OneDrive\Documents\Camtasia\FDC\Export\Handson Modulo 01\audio-instrucao-handson.m4a" `
  -o transcricao-audio-instrucao-handson.md `
  --model small `
  --language pt
```
