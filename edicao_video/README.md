# Edição de vídeo

`cortar_trechos_fala.py` usa `silencedetect` do FFmpeg para encontrar intervalos acima do limiar de silêncio e salvar cada trecho em um MP4. Não é um classificador de fala: música e ruído também podem ser detectados.

## Execução independente

Execute na raiz do repositório, com FFmpeg e ffprobe no `PATH`:

```powershell
uv run -m edicao_video "C:\videos\aula.mp4" --saida "D:\videos\cortes"
```

Também aceita várias entradas e pastas recursivas:

```powershell
uv run -m edicao_video "C:\videos\modulo01" "C:\videos\modulo02" `
  --saida "D:\videos\cortes" --yes
```

Alternativa pelo arquivo: `uv run edicao_video/cortar_trechos_fala.py <entrada> --saida <destino>`.

Primeiro o script analisa os vídeos e grava os relatórios de tempos. Depois solicita `y` para gerar os cortes; `--yes` ou `-y` elimina essa confirmação. No pipeline da raiz, a execução já é automática.

São reconhecidos `.trec`, `.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`, `.mts` e `.m2ts`. A leitura depende do suporte do FFmpeg ao conteúdo de cada arquivo. Caso uma gravação TREC não seja reconhecida, exporte-a para MP4 pelo Camtasia.

## Parâmetros

| Opção | Padrão | Efeito |
| --- | --- | --- |
| `--encoder` | `libx264` | CPU; também aceita `h264_nvenc` e `hevc_nvenc` |
| `--quality` | 18 na CPU, 24 no NVENC | CRF ou CQ do encoder |
| `--noise` | `-35dB` | Limiar de silêncio; use `--noise=-35dB` |
| `--min-silence` | 5 s | Duração mínima da pausa |
| `--padding` | 0,25 s | Margem antes e depois de cada trecho |
| `--merge-gap` | 0,7 s | Intervalo máximo para unir trechos |
| `--min-segment` | 60 s | Duração mínima do trecho, aplicada antes da margem |
| `--overwrite` | desativado | Permite substituir cortes e relatórios de tempos |
| `--yes` | desativado | Dispensa a confirmação de geração |

Para falas curtas:

```powershell
uv run -m edicao_video "C:\videos\aula.mp4" --saida "D:\videos\cortes" `
  --min-silence 1 --min-segment 3 --yes
```

O corte recodifica o vídeo com largura de 1920 pixels e altura proporcional par, usando `yuv420p`. O áudio é convertido para AAC a 128 kbps. O terminal mostra o progresso do FFmpeg.

## Saídas

Na execução independente, `aula.mp4` gera:

```text
cortes/
+-- aula_tempos.txt
+-- aula_trechos/
    +-- aula_trecho_001.mp4
    +-- aula_trecho_002.mp4
```

O relatório contém início, fim, duração e caminho de cada corte planejado. Ele é criado antes da geração; sua presença não garante que os vídeos já foram produzidos. Se a confirmação for cancelada, uma nova análise no mesmo destino exige `--overwrite`.

O modo independente mantém os nomes base anteriores e usa um único destino; entradas com o mesmo nome base precisam de destinos separados. Para lotes com nomes repetidos, use o [pipeline da raiz](../README.md), que preserva as subpastas e inclui a extensão de origem na pasta de cada vídeo.

## GPU NVIDIA

```powershell
uv run -m edicao_video "C:\videos\aula.trec" --saida "D:\videos\cortes" `
  --encoder hevc_nvenc --quality 26 --yes
```

NVENC requer GPU e driver compatíveis com a versão instalada do FFmpeg. Verifique o ambiente:

```powershell
nvidia-smi
ffmpeg -encoders | Select-String nvenc
```

Se houver incompatibilidade com a API NVENC, atualize o driver conforme o erro do FFmpeg ou use `--encoder libx264`. NVENC acelera a codificação de saída; não implica que a decodificação do arquivo de entrada também ocorra na GPU.

## Converter TREC completo, sem cortes

Para arquivos que o FFmpeg consiga ler:

```powershell
ffmpeg -i "C:\videos\aula.trec" -map 0:v:0 -map "0:a:0?" `
  -vf "scale=1920:-2,format=yuv420p" -c:v libx264 -preset fast -crf 18 `
  -c:a aac -b:a 192k -movflags +faststart "D:\videos\aula.mp4"
```

## Ajuda e testes

```powershell
uv run -m edicao_video --help
uv run pytest tests/edicao_video
```
