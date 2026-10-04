# Extração de áudio

`extrair_audio.py` extrai a primeira faixa de áudio de um vídeo ou de todos os vídeos de uma pasta para arquivos M4A. Execute os comandos na raiz do repositório; FFmpeg e ffprobe devem estar no `PATH`.

## Um arquivo ou um lote

```powershell
uv run -m extracao_audio "C:\videos\aula.mp4" --saida "D:\audios"
uv run -m extracao_audio "C:\videos" --saida "D:\audios"
```

Alternativa pelo arquivo:

```powershell
uv run extracao_audio/extrair_audio.py "C:\videos" --saida "D:\audios"
```

A busca é recursiva e reconhece `.trec`, `.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`, `.mts` e `.m2ts`, desde que o FFmpeg consiga ler o conteúdo.

A estrutura das subpastas é preservada:

```text
Entrada: videos/modulo01/aula.mp4
Saída:   audios/modulo01/aula.m4a
```

## Cópia ou recodificação

Por padrão, o script copia a faixa de áudio sem recodificação. Se o codec de origem não for compatível com M4A, use `--reencode` para converter para AAC a 192 kbps:

```powershell
uv run -m extracao_audio "C:\videos" --saida "D:\audios" --reencode
```

Arquivos existentes não são substituídos por padrão. Para permitir a substituição:

```powershell
uv run -m extracao_audio "C:\videos" --saida "D:\audios" --overwrite
```

As opções podem ser combinadas. Arquivos de extensões diferentes com o mesmo nome base e na mesma pasta mapeiam para o mesmo M4A neste modo; execute-os com destinos distintos para preservar ambos.

## Comportamento

- Cria as pastas de destino conforme necessário.
- Ignora vídeos sem faixa de áudio.
- Extrai somente o primeiro stream de áudio, sem vídeo ou legendas.
- Falhas na leitura e na extração encerram a execução independente com código `1`.
- Caminhos com espaços devem ficar entre aspas.

No [pipeline da raiz](../README.md), esta etapa recebe somente os cortes gerados no lote. O destino é fixado em `<destino dos vídeos>/audios_extraidos`, mantendo a estrutura dos cortes. O áudio AAC dos cortes é copiado, sem nova recodificação.

## Ajuda e testes

```powershell
uv run -m extracao_audio --help
uv run pytest tests/extracao_audio
```
