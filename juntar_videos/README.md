# Juntar vídeos sem recodificar

O módulo `juntar_videos` reúne dois ou mais vídeos em um único arquivo,
exatamente na sequência de um YAML. Usa o demuxer `concat` do FFmpeg com
`-map 0 -c copy`: copia todos os streams, incluindo vídeo e áudio, sem encode.
Não modifica, move ou apaga os arquivos originais. Não precisa de GPU.

## YAML e comando

Crie um arquivo UTF-8 chamado `juncao.yaml`:

```yaml
origem: 'D:\Camtasia\FDC_OBS\visaoestrategica\organizados'
saida: 'D:\Camtasia\FDC_OBS\visaoestrategica\aula_completa.mp4'
arquivos:
  - '01.Introdução.mp4'
  - '03.Análise do ambiente.mp4'
  - '02.Conceitos de estratégia.mp4'
```

A posição na lista determina a sequência, independentemente dos números nos
nomes. A lista deve ter pelo menos dois arquivos. Você pode repetir um arquivo
para reproduzir o mesmo trecho novamente na sequência.

Os arquivos são caminhos relativos à `origem`, podendo incluir subpastas.
Caminhos absolutos ou que escapem da origem não são aceitos na lista.
`origem` e `saida` também podem ser relativos: nesse caso, são resolvidos pela
pasta do YAML, e não pelo diretório do terminal. Use aspas simples para caminhos
Windows no YAML; um apóstrofo dentro de aspas simples é escrito duas vezes.

Na raiz do repositório, com FFmpeg e ffprobe no `PATH`:

```powershell
# Conferir arquivos, sequência e compatibilidade, sem criar a saída.
uv run --locked -m juntar_videos --yaml "juncao.yaml" --simular

# Gerar o vídeo final.
uv run --locked -m juntar_videos --yaml "juncao.yaml"
```

O comando cria a pasta de saída, se necessário, e informa o arquivo gerado.
Um destino existente nunca é sobrescrito; escolha outro nome no YAML.
Não há opção de sobrescrita nem recodificação automática.

## Compatibilidade e limitações

Antes da junção, o módulo usa ffprobe para comparar todos os streams, na mesma
ordem: quantidade, tipo, codec, perfil, nível, base de tempo e configuração de
decodificação (`extradata_hash`). Nos vídeos, verifica resolução, formato de
pixels, proporção, taxa de quadros, entrelaçamento e características de cor;
nos áudios, formato de amostra, frequência, canais e layout. Duração, bitrate,
quantidade de frames e tags não precisam coincidir.

Diferenças interrompem o processo antes de criar o arquivo final, mostrando o
vídeo incompatível e os campos diferentes em relação ao primeiro vídeo.
Arquivos sem áudio podem ser unidos entre si; misturar vídeos com e sem áudio
não passa na comparação. Arquivos sem stream de vídeo são recusados.

A validação é conservadora e não garante que todo contêiner aceite todos os
streams. A extensão de `saida` define o contêiner, por exemplo `.mp4` ou `.mkv`.
Na execução, o FFmpeg verifica o suporte ao contêiner e os dados efetivos.
Se houver erro, o comando explica a falha e não publica a saída final.
`--simular` inspeciona os streams, mas não testa a muxagem nem lê todos os pacotes.

Não são adicionadas transições, pausas, capítulos, cortes ou alterações de
qualidade. Não há normalização de timestamps ou correção de entradas danificadas;
diferenças de duração entre áudio e vídeo podem produzir pequenas descontinuidades.
Metadados e capítulos de cada entrada não são combinados em um índice novo.
Veja os requisitos do [concat na documentação do FFmpeg](https://ffmpeg.org/ffmpeg-formats.html#concat).

## Temporários e falhas

Os arquivos temporários ficam em uma pasta exclusiva dentro da pasta de saída,
no mesmo disco. O nome final só é publicado depois que o FFmpeg termina com
sucesso, sem substituir um destino criado por outro processo durante a execução.
É necessário espaço para o vídeo final, aproximadamente a soma das entradas.

Em erros e interrupções tratadas (`Ctrl+C`), os temporários são removidos e os
originais permanecem intactos. A pasta de saída criada pode permanecer vazia.
Uma queda de energia ou encerramento forçado pode deixar uma pasta
`.juntar_videos-*`; confira se não há processo ativo antes de removê-la.

Códigos de saída: `0` para sucesso ou simulação válida, `1` para erro,
`2` para argumentos inválidos e `130` para interrupção.

```powershell
uv run --locked -m juntar_videos --help
uv run --locked pytest tests/juntar_videos
```

O teste de integração cria vídeos sintéticos curtos em diretório temporário e
confere codecs, duração, ordem e preservação das entradas. Ele requer FFmpeg com
`libx264` e AAC; é ignorado quando FFmpeg ou ffprobe não está no `PATH`.
