# Atualização do importador do Skan Coach AI

Este conjunto classifica `x4` e `x5` como `Team Hunt (PT)`, `duo` e `x2` como
`Duo` (2 jogadores), e `x3` como `Trio` (3 jogadores). Também reconhece `TH`
e `Team Hunt`; quando a descrição lista os membros, usa essa lista para contar
a equipe. A regra usa
limites de token: `2x loot` e ocorrências dentro de palavras maiores não são
interpretadas como quantidade de jogadores. Se o título combinar um tamanho
de grupo com `solo`, a categoria do grupo prevalece e `needs_review` fica ativo.
Indicadores de categorias diferentes também são sinalizados para revisão; a
categoria de maior tamanho prevalece.

## Arquivos

- `import_youtube_playlist.py`: importa todas as páginas de uma playlist
  pública ou os vídeos enviados por um canal, gravando CSV e SQLite com a
  biblioteca padrão do Python.
- `title_classifier.py`: regra de classificação.
- `persist_classification.py`: migração incremental das colunas e atualização
  da linha já importada em `videos`.
- `test_title_classifier.py`: testes unitários, incluindo falsos positivos,
  prioridade de Team Hunt e persistência do conflito.

## Playlists e vocações

`playlist_manifest.json` reúne as listas de MS, EK, RP, ED e EM (Monk). Para
importar ou atualizar todas de uma vez, abra o PowerShell nesta pasta, defina
`YOUTUBE_API_KEY` nesta mesma janela e rode:

```powershell
$env:YOUTUBE_API_KEY = "SUA_CHAVE"
python .\import_youtube_playlist.py --sync-config
```

O mesmo classificador de modalidade, XP Raw e profit é aplicado a todas as
vocações. Para acrescentar uma playlist, adicione ao manifesto seu ID, a sigla
da vocação (`MS`, `EK`, `RP`, `ED` ou `EM`) e o nome que aparecerá na interface.
Para importar apenas uma lista, use `--playlist-id "ID_OU_URL" --vocation EK`.
O script cria/atualiza `playlist_videos.csv` e `skan_coach.db`.

### Importar hunts de um canal (sem playlist)

Passe o link público do canal, um ID `UC...` ou um identificador `@handle`.
O importador percorre a lista de envios do canal e mantém somente vídeos cujo
título contenha uma taxa de XP numérica ou um valor numérico associado a
`Profit` ou `Waste`. Waste é registrado como profit negativo. Os vídeos filtrados
são acrescentados ao catálogo e não removem as playlists já importadas. Exemplo:

```powershell
python .\import_youtube_playlist.py --channel "https://www.youtube.com/@nome-do-canal"
```

Para adicionar apenas um vídeo de hunt, use a URL ou o ID:

```powershell
python .\import_youtube_playlist.py --video "https://www.youtube.com/watch?v=VIDEO_ID" --vocation EK
```

A chave `YOUTUBE_API_KEY` precisa estar definida nessa janela do PowerShell,
como na importação das playlists. A API do YouTube só permite consultar canais
públicos e seus vídeos públicos.

O CSV pode ser aberto no Excel. O banco contém a tabela `videos` e as tabelas
`playlists` e `playlist_videos`, que ligam cada vídeo à sua lista e vocação.
Entradas indisponíveis sem `videoId` são ignoradas. A extração percorre páginas
de até 50 itens usando o `nextPageToken` oficial da API.

## XP Raw

O campo `xp_raw_display` traz a XP/h equivalente a 100%: rates explicitamente
marcadas como `Raw` são mantidas; se o título informar um percentual, o rate é
dividido por esse percentual; quando não houver percentual nem `Raw`, o padrão
de 150% informado pelo usuário é aplicado e identificado como presumido. A
interface também mostra o rate original e a base usada no cálculo. Rates de XP
com modificadores adicionais como Prey/Book Boosted são sinalizadas, pois o
bônus extra não pode ser separado apenas pelo título.

O campo `profit_display` é extraído somente do número ligado à palavra
`Profit`, sem confundi-lo com a XP Raw. Se o título disser apenas `Profit`, sem
`/h`, o valor é tratado como o resultado de uma hunt de 1 hora e essa suposição
fica registrada em `profit_assumption`.

Quando a regra de classificação mudar, reaplique-a aos arquivos existentes sem
fazer novas chamadas à API:

```powershell
python .\import_youtube_playlist.py --reclassify-existing
```

## Interface local

Para abrir o catálogo visual conectado ao banco, consulte
`interface/README.md`. O servidor local usa apenas a biblioteca padrão do
Python e serve a interface em `http://127.0.0.1:8000`.

## Integração em outro projeto

Depois de criar a tabela `videos`, chame `ensure_classification_columns(conn)`.
Ao inserir ou atualizar cada vídeo, chame
`store_title_classification(conn, video_id, title)` e confirme a transação.
O helper pressupõe que a tabela existente tenha `video_id` como identificador
do vídeo. Se o esquema atual usar outro nome de tabela ou chave, adapte somente
essa consulta ao esquema real.

Execute os testes com `python -m unittest -v` nesta pasta.

Este pacote é um importador autocontido; não requer um projeto Skan Coach AI
pré-existente. A API key é lida da variável `YOUTUBE_API_KEY` e não é gravada
nos arquivos de saída.

