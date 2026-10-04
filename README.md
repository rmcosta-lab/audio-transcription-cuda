# Pipeline de vídeo e áudio

Ferramentas para detectar trechos com áudio, cortar vídeos, extrair os áudios dos cortes e transcrever áudio para Markdown. O projeto usa **UV** para gerenciar o ambiente e as dependências.

O pipeline da raiz executa **edição → extração de áudio**, em lote. A transcrição continua disponível como etapa independente.

## Preparar o ambiente

Requisitos:

- Python 3.10 ou superior; `.python-version` seleciona Python 3.13 para o ambiente do projeto.
- [UV](https://docs.astral.sh/uv/getting-started/installation/).
- FFmpeg e ffprobe no `PATH` para edição e extração.

No PowerShell, a partir deste repositório:

```powershell
Set-Location "D:\LabIA\audio-transcription-cuda"
uv sync --locked
ffmpeg -version
ffprobe -version
```

`uv sync` instala as ferramentas de desenvolvimento; use `uv sync --locked --no-dev` se precisar apenas executar o pipeline. FFmpeg é uma instalação externa, não uma dependência Python. Não é necessário ativar o ambiente ao usar `uv run`.

As dependências de transcrição são opcionais. Para instalá-las:

```powershell
uv sync --locked --extra transcricao
```

O [gerenciamento de dependências do UV](https://docs.astral.sh/uv/concepts/dependencies/) fica em `pyproject.toml`, com as versões resolvidas em `uv.lock`. Mantenha os dois arquivos versionados. Para redes que usam o armazenamento de certificados do Windows, acrescente `--system-certs` antes do comando: `uv --system-certs sync --locked --extra transcricao`.

## Executar o pipeline em lote

Informe a pasta de entrada e o destino dos vídeos. Os áudios são salvos automaticamente em **`<destino dos vídeos>\audios_extraidos`**:

```powershell
uv run --locked pipeline.py "C:\videos\originais" --saida "D:\videos\cortes"
```

`--destino-videos` é um alias de `--saida`. A busca inclui subpastas, e o processamento é sequencial, sem confirmação interativa. O pipeline usa CPU por padrão.

Para codificar com uma GPU NVIDIA que suporte NVENC:

```powershell
uv run --locked pipeline.py "C:\videos\originais" `
  --saida "D:\videos\cortes" `
  --encoder h264_nvenc `
  --quality 24
```

Os parâmetros de detecção anteriores foram preservados: silêncio mínimo de **5 segundos** e trecho mínimo de **60 segundos**. Para arquivos ou falas mais curtos, ajuste-os:

```powershell
uv run --locked pipeline.py "C:\videos\originais" `
  --saida "D:\videos\cortes" `
  --min-silence 1 `
  --min-segment 3 `
  --padding 0.25 `
  --merge-gap 0.7 `
  --noise=-35dB
```

O detector usa volume (`silencedetect` do FFmpeg), não reconhecimento de voz. Música e ruído acima do limiar também podem gerar trechos. Os cortes usam largura de 1920 pixels, altura proporcional e áudio AAC; a extração copia esse áudio para M4A.

### Organização da saída

Para a entrada `originais\modulo01\aula.mp4`, a saída será:

```text
cortes/
+-- modulo01/
|   +-- aula.mp4_tempos.txt
|   +-- aula.mp4_trechos/
|       +-- aula_trecho_001.mp4
|       +-- aula_trecho_002.mp4
+-- audios_extraidos/
|   +-- modulo01/
|       +-- aula.mp4_trechos/
|           +-- aula_trecho_001.m4a
|           +-- aula_trecho_002.m4a
+-- relatorio_pipeline.json
```

As subpastas de origem são preservadas. A extensão original faz parte do nome da pasta de cortes para distinguir, por exemplo, `aula.mp4` de `aula.mkv`.

### Reexecução e falhas

- Relatórios de tempos, cortes e áudios existentes são protegidos. Use `--overwrite` para permitir substituição, ou escolha um novo destino.
- `relatorio_pipeline.json` registra a execução mais recente, com parâmetros, arquivos gerados e status por vídeo: `concluido`, `sem_audio`, `sem_trechos`, `erro` ou `interrompido`.
- Uma falha em um vídeo é registrada e o lote continua nos demais. Saída do processo: `0` sem falhas, `1` com erro, `2` para argumentos inválidos e `130` para interrupção.
- Vídeos sem áudio ou sem trechos que atendam aos filtros são ignorados.
- Somente os cortes gerados nesta execução entram na extração. Arquivos antigos no destino não são extraídos.
- O destino pode ser uma subpasta da entrada; ele é excluído da busca. Não pode ser igual à entrada nem ser uma pasta que contenha a entrada. O nome `audios_extraidos` é reservado na primeira camada das subpastas de origem.
- Não há retomada automática. Uma falha pode deixar arquivos parciais; use outro destino ou `--overwrite`. Ao mudar os parâmetros, cortes antigos que excedam a nova quantidade permanecem no disco, mas não entram no lote atual. Um destino novo oferece uma saída limpa.

Consulte todas as opções:

```powershell
uv run pipeline.py --help
```

## Executar cada etapa separadamente

```powershell
# Edição: analisa, grava os tempos e pede confirmação; --yes automatiza a confirmação.
uv run -m edicao_video "C:\videos\aula.mp4" --saida "D:\videos\cortes" --encoder hevc_nvenc --quality 26

# Extração: aceita um arquivo ou uma pasta com subpastas.
uv run -m extracao_audio "D:\videos\cortes" --saida "D:\videos\cortes\audios_extraidos"

# Transcrição em CPU: informe um arquivo de áudio.
uv run --extra transcricao -m transcrever_audio "D:\audios\aula.m4a" -o "D:\transcricoes\aula.md" --model medium --device cuda --compute-type float16

# Transcrição em lote: informe a pasta de áudios e a pasta de destino.
uv run --extra transcricao -m transcrever_audio "D:\audios" -o "D:\transcricoes" `
  --model medium --device cuda --compute-type float16
```

Na transcrição em lote, cada áudio gera um Markdown e as subpastas são preservadas. O modelo é reutilizado entre os arquivos. Transcrições existentes são ignoradas; use `--overwrite` para substituí-las. O modo individual continua aceitando os mesmos argumentos.

Também é possível executar os arquivos diretamente: `uv run edicao_video/cortar_trechos_fala.py`, `uv run extracao_audio/extrair_audio.py` e `uv run --extra transcricao transcrever_audio/transcrever_audio.py`, com os mesmos argumentos.

Documentação de cada etapa:

- [Edição de vídeo](edicao_video/README.md): detecção, parâmetros de corte, TREC e NVENC.
- [Extração de áudio](extracao_audio/README.md): cópia do áudio e recodificação.
- [Transcrição](transcrever_audio/README.md): Whisper, CPU, CUDA e certificados.

## Estrutura do repositório

```text
.
+-- pipeline.py
+-- pyproject.toml
+-- uv.lock
+-- .python-version
+-- edicao_video/
|   +-- cortar_trechos_fala.py
|   +-- README.md
+-- extracao_audio/
|   +-- extrair_audio.py
|   +-- README.md
+-- transcrever_audio/
|   +-- transcrever_audio.py
|   +-- README.md
+-- tests/
|   +-- edicao_video/
|   +-- extracao_audio/
|   +-- transcrever_audio/
|   +-- test_pipeline.py
+-- cola.py                   # Preservado
```

A transcrição é executada pelo módulo `transcrever_audio` ou pelo arquivo `transcrever_audio/transcrever_audio.py`, tanto individualmente quanto em lote. Os caminhos de dados são informados pela linha de comando, sem depender de diretórios pessoais.

## Desenvolvimento e validação

```powershell
uv sync --locked
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
```

Os testes estão agrupados por etapa. Validam a orquestração do lote, preservação de caminhos, conflitos de saída, tratamento de erros, detecção de intervalos e transcrição individual e em lote. Usam substitutos das chamadas de mídia e do modelo: não geram vídeos sintéticos, não executam processamento de mídia e não baixam modelos Whisper.
