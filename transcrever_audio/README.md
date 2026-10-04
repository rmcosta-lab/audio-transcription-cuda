# Transcrição de áudio

`transcrever_audio.py` transcreve um arquivo ou uma pasta de áudios para Markdown usando `faster-whisper`. A saída contém metadados, timestamps e texto corrido. A transcrição é independente do pipeline de edição e extração.

## Preparar e executar

Na raiz do repositório:

```powershell
uv sync --locked --extra transcricao
uv run --extra transcricao -m transcrever_audio "D:\audios\aula.m4a" -o "D:\transcricoes\aula.md"
```

Alternativa pelo arquivo:

```powershell
uv run --extra transcricao transcrever_audio/transcrever_audio.py "D:\audios\aula.m4a" -o "D:\transcricoes\aula.md"
```

A entrada é obrigatória. O padrão é modelo `small`, idioma `pt`, CPU e computação `int8`. No modo individual, sem `-o`, a saída é `transcricao-audio-instrucao-handson.md` no diretório atual. Uma saída individual existente é substituída, mantendo o comportamento anterior.

As dependências são declaradas no extra `transcricao` do `pyproject.toml`. Mantenha `--extra transcricao` nos comandos `uv run` desta etapa. Na primeira transcrição, o modelo escolhido é baixado do Hugging Face e exige internet; execuções seguintes reutilizam o cache.

## Transcrever em lote

Informe a pasta de entrada e a pasta de destino com `-o`, `--output` ou `--saida`. O modo em lote é selecionado automaticamente quando a entrada é um diretório:

```powershell
uv run --extra transcricao -m transcrever_audio `
  "D:\audios_extraidos" `
  -o "D:\transcricoes" `
  --model medium --device cuda --compute-type float16
```

Com o ambiente virtual ativado e as dependências instaladas, também pode usar `python -m transcrever_audio` com os mesmos argumentos. A execução pelo arquivo `transcrever_audio/transcrever_audio.py` também aceita lote.

- A busca inclui subpastas e reconhece `.aac`, `.aif`, `.aiff`, `.flac`, `.m4a`, `.mp3`, `.ogg`, `.opus`, `.wav` e `.wma`, sem diferenciar maiúsculas de minúsculas nas extensões.
- Cada áudio gera um Markdown de mesmo nome base; as subpastas são preservadas. Exemplo: `audios_extraidos/modulo01/aula.m4a` → `transcricoes/modulo01/aula.md`.
- O modelo é carregado uma única vez e os arquivos são processados sequencialmente, com os mesmos parâmetros de modelo, dispositivo, computação, idioma e VAD.
- Transcrições existentes são ignoradas no lote. Acrescente `--overwrite` para substituí-las. Se todas já existirem, nenhum modelo é carregado.
- Arquivos que mapeiam para o mesmo Markdown, como `aula.mp3` e `aula.wav` na mesma pasta, geram um erro antes da transcrição. Renomeie um deles ou coloque-os em subpastas distintas.
- Se o destino estiver dentro da entrada, essa subpasta é excluída da busca. Também é possível usar a própria pasta de entrada como destino; arquivos Markdown não entram na busca de áudios.
- Uma falha em um áudio é exibida e o lote continua. O resumo informa concluídos, ignorados e falhas. O processo retorna `1` se houver falhas e `130` em caso de interrupção. Falhas no carregamento do modelo encerram a execução.
- Uma entrada inexistente, uma pasta sem áudios suportados ou um lote sem `-o` geram erro antes de carregar o modelo.

## Opções

| Opção | Uso |
| --- | --- |
| `-o`, `--output`, `--saida` | Arquivo Markdown no modo individual; diretório obrigatório no lote |
| `--model` | `tiny`, `base`, `small`, `medium`, `large-v3` ou outro modelo compatível |
| `--language` | `pt` por padrão; string vazia para autodetecção |
| `--device` | `cpu` por padrão; `cuda` para GPU configurada |
| `--compute-type` | `int8` por padrão; por exemplo `float16` com CUDA |
| `--no-vad` | Desativa o filtro de trechos sem fala |
| `--overwrite` | No lote, substitui transcrições existentes; no individual, a substituição continua sendo o padrão |

Exemplo em CPU:

```powershell
uv run --extra transcricao -m transcrever_audio "D:\audios\aula.m4a" `
  -o "D:\transcricoes\aula.md" --model medium --language pt --device cpu --compute-type int8
```

## GPU NVIDIA no Windows

A [documentação do faster-whisper](https://github.com/SYSTRAN/faster-whisper#gpu) descreve as bibliotecas requeridas: cuBLAS para CUDA 12 e cuDNN 9 para CUDA 12. Use uma GPU NVIDIA e driver compatíveis, com as DLLs disponíveis no `PATH`. Essas bibliotecas de sistema não são instaladas por `uv sync`.

Downloads oficiais: [CUDA](https://developer.nvidia.com/cuda-downloads) e [cuDNN](https://developer.nvidia.com/cudnn).

```powershell
nvidia-smi
where.exe cublas64_12.dll
where.exe cudnn_ops64_9.dll
```

Após configurar as bibliotecas e reabrir o terminal:

```powershell
uv run --extra transcricao -m transcrever_audio "D:\audios\aula.m4a" `
  -o "D:\transcricoes\aula.md" --model medium --device cuda --compute-type float16
```

Se ocorrer `Library cublas64_12.dll is not found or cannot be loaded`, revise as bibliotecas e o `PATH` ou execute com `--device cpu --compute-type int8`.

## Certificados

O script usa `truststore` para os downloads do modelo. Caso a instalação das dependências falhe com `UnknownIssuer`, utilize o armazenamento de certificados do sistema também no UV:

```powershell
uv --system-certs sync --locked --extra transcricao
uv --system-certs run --extra transcricao -m transcrever_audio "D:\audios\aula.m4a" -o transcricao.md
```

Certificados de uma rede corporativa devem estar instalados no armazenamento de confiança do Windows. Mantenha a verificação SSL habilitada.

## Ajuda e testes

```powershell
uv run -m transcrever_audio --help
uv run pytest tests/transcrever_audio
```

A ajuda e os testes não carregam modelos nem exigem as dependências de inferência.
