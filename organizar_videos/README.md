# Organização de vídeos com YAML

O módulo `organizar_videos` funciona em duas etapas: cataloga os vídeos para você
definir nomes e ordem, depois renomeia e move os arquivos para uma única pasta.
Não utiliza FFmpeg, não recodifica os vídeos e não precisa de GPU.

## 1. Gerar o YAML

Execute na raiz do repositório:

```powershell
uv run --locked -m organizar_videos listar "D:\Camtasia\FDC_OBS\visaoestrategica\cortes" --yaml "organizacao.yaml" --destino "D:\Camtasia\FDC_OBS\visaoestrategica\organizados"
```

`--destino` é opcional: por padrão, será uma pasta irmã da origem chamada
`<nome da origem>_organizados`. Você também pode editar o destino no YAML.
Se o destino estiver dentro da origem, essa pasta é excluída da busca.

O caminho relativo de `--yaml` é resolvido dentro da pasta de origem informada
ao `listar`. No exemplo, o arquivo será criado em
`D:\Camtasia\FDC_OBS\visaoestrategica\cortes\organizacao.yaml`.
O terminal mostra o diretório completo onde o YAML foi salvo. Um caminho absoluto
em `--yaml` permite escolher outro local explicitamente. Ao aplicar, informe o
caminho do YAML criado, como nos comandos abaixo.

A busca inclui a raiz e todas as subpastas, em ordem de caminho, e considera
`.trec`, `.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`, `.mts` e `.m2ts`, independentemente
de maiúsculas/minúsculas. Áudios, relatórios e links simbólicos são ignorados.
Nenhum vídeo é movido nesta etapa. Um YAML existente nunca é sobrescrito;
use outro nome para uma nova listagem. Uma origem sem vídeos gera erro.

Exemplo de YAML gerado:

```yaml
origem: 'D:\Camtasia\FDC_OBS\visaoestrategica\cortes'
destino: 'D:\Camtasia\FDC_OBS\visaoestrategica\organizados'
arquivos:
  - diretorio: 'aula01_trechos'
    arquivo: 'aula01_trecho_001.mp4'
    ordem: null
    novo_nome: ''
  - diretorio: 'modulo02\aula02_trechos'
    arquivo: 'aula02_trecho_001.mp4'
    ordem: null
    novo_nome: ''
```

## 2. Preencher e aplicar

Preencha `ordem` com um inteiro positivo e único no YAML inteiro, e `novo_nome`
com o título, sem prefixo numérico e sem extensão:

```yaml
origem: 'D:\Camtasia\FDC_OBS\visaoestrategica\cortes'
destino: 'D:\Camtasia\FDC_OBS\visaoestrategica\organizados'
arquivos:
  - diretorio: 'aula01_trechos'
    arquivo: 'aula01_trecho_001.mp4'
    ordem: 2
    novo_nome: 'Conceitos de estratégia'
  - diretorio: 'modulo02\aula02_trechos'
    arquivo: 'aula02_trecho_001.mp4'
    ordem: 1
    novo_nome: 'Introdução à visão estratégica'
```

`diretorio` é relativo à origem; `.` indica um vídeo diretamente na raiz.
Mantenha `diretorio` e `arquivo` como gerados. Se informar `origem` ou `destino`
relativos, eles serão resolvidos em relação à pasta do YAML.
Para deixar um vídeo na origem, remova seu item do YAML; campos vazios não
significam ignorar. A lista precisa conter pelo menos um vídeo.

Confira o resultado sem mover arquivos:

```powershell
uv run --locked -m organizar_videos aplicar --yaml "D:\Camtasia\FDC_OBS\visaoestrategica\cortes\organizacao.yaml" --simular
```

Aplique a organização:

```powershell
uv run --locked -m organizar_videos aplicar --yaml "D:\Camtasia\FDC_OBS\visaoestrategica\cortes\organizacao.yaml"
```

Resultado, sem subpastas:

```text
organizados/
+-- 01.Introdução à visão estratégica.mp4
+-- 02.Conceitos de estratégia.mp4
```

O prefixo tem **no mínimo dois dígitos**: `01`, `02`, …, `10`, …, `100`.
Não é necessário usar números consecutivos. A extensão original é preservada.

## Validações e falhas

Todo o YAML é validado antes de criar o destino ou mover o primeiro vídeo.
Campos vazios, ordens repetidas, origens repetidas, vídeos ausentes, caminhos
fora da origem, links simbólicos e conflitos de destino impedem a execução.
O destino não pode ser igual à origem nem conter a origem.
Títulos não podem conter `< > : " / \ | ? *`, caracteres de controle, nem
terminar com ponto ou espaço. O nome final deve caber no limite de 255 caracteres
do Windows. Arquivos existentes nunca são sobrescritos.

A movimentação é sequencial por ordem: copia cada vídeo sem recodificar,
preserva seus metadados de arquivo e só então remove o original. Isso permite
mover entre discos, mas exige espaço para a cópia e pode demorar para vídeos
grandes. Uma falha durante a cópia remove o destino parcial e mantém a origem.
Arquivos não listados e as subpastas originais permanecem intactos.
Relatórios e áudios já existentes não são atualizados para os novos caminhos.

Não há transação nem retomada automática: uma falha de disco, permissão ou
interrupção pode deixar parte do lote concluída. Confira o progresso no terminal
e os arquivos dos dois lados; retire do YAML os itens já concluídos antes de
retomar. Se houver uma cópia no destino e o original ainda existir, confira ambos
antes de remover qualquer um. O YAML não é alterado ao aplicar; executar novamente
o mesmo YAML após uma aplicação bem-sucedida gera erro de origem ausente.

Códigos de saída: `0` para sucesso ou simulação válida, `1` para erro,
`2` para argumentos inválidos e `130` para interrupção.

```powershell
uv run --locked -m organizar_videos --help
uv run --locked -m organizar_videos listar --help
uv run --locked -m organizar_videos aplicar --help
uv run --locked pytest tests/organizar_videos
```
