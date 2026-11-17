# Skan Coach — AI Hunt Planner

O **Skan Coach** é um catálogo comunitário de hunts de Tibia. Ele reúne vídeos de diferentes criadores em um formato comum para ajudar jogadores a encontrar respawns, comparar XP e profit e escolher hunts adequadas à sua vocação e level.

## O que a aplicação faz

- Importa vídeos públicos de playlists, canais ou links individuais do YouTube.
- Organiza o catálogo por vocação, nome da hunt, modalidade e level.
- Lê os números de XP e profit/waste dos títulos. A XP é normalizada para XP Raw quando o título informa percentual; sem percentual ou indicação de Raw, aplica a regra de 150% presumidos. Waste é exibido como profit negativo.
- Permite buscar, filtrar por level e vocação, comparar resultados e abrir o vídeo original.
- Recebe relatos da comunidade sobre testes de respawn, resultados de XP/profit e vídeos desatualizados.
- Registra doações em Tibia Coins como pendentes. O administrador valida a transferência antes de atualizar o ranking.
- Oferece um portal administrativo para adicionar, atualizar e remover fontes do YouTube e destacar conteúdos patrocinados.

O objetivo é transformar títulos e descrições publicados por criadores diferentes em um catálogo prático, sem substituir o vídeo ou a experiência de quem testa a hunt. A comunidade pode complementar os dados com resultados atuais.

## Organização dos arquivos

- `backend/`: servidor web, importador do YouTube, integração com SQLite/Neon e regras de XP, profit e modalidade.
- `frontend/`: site, portal administrativo, formulário de divulgação, estilos e configuração da API.
- `data/`: manifesto das playlists, exportação CSV e banco SQLite usado localmente e como carga inicial do Neon.
- `tests/`: testes automatizados das regras de classificação e XP.
- `render.yaml`, `Procfile` e `requirements.txt`: configuração de execução e hospedagem.
- `setup_neon.ps1`: utilitário opcional para preparar a conexão local com o Neon. O arquivo `.env.local` criado por ele contém segredos e não deve ser enviado ao GitHub.

## Rodar localmente

Use Python instalado e, na pasta raiz do projeto, instale as dependências:

```powershell
python -m pip install -r requirements.txt
```

Defina as chaves necessárias na janela do PowerShell. `YOUTUBE_API_KEY` é necessária para importar do YouTube; o site pode abrir sem ela. `DATABASE_URL` só é necessária quando você quer usar Neon em vez do banco SQLite local.

```powershell
$env:YOUTUBE_API_KEY = "SUA_CHAVE_DO_YOUTUBE"
$env:SKAN_ADMIN_KEY = "UMA_CHAVE_ADMINISTRATIVA_FORTE"
python -m backend.app
```

Abra `http://127.0.0.1:8000`. Para desligar, volte ao terminal e pressione `Ctrl+C`.

## Importar ou atualizar playlists

O manifesto `data/playlist_manifest.json` contém as playlists cadastradas. Para importar ou sincronizar todas:

```powershell
python -m backend.import_youtube_playlist --sync-config
```

Também é possível importar um canal ou vídeo individual:

```powershell
python -m backend.import_youtube_playlist --channel "https://www.youtube.com/@nome-do-canal"
python -m backend.import_youtube_playlist --video "https://www.youtube.com/watch?v=VIDEO_ID" --vocation EK
```

Canais podem conter várias vocações; os vídeos são classificados individualmente. O importador só considera vídeos de canal quando o título tem um número ligado a XP, Profit ou Waste. Para atualizar as fontes cadastradas pelo Portal, use **Atualizar todas as fontes**.

## Classificação das hunts

A modalidade pode vir do título ou de uma lista estruturada de jogadores na descrição. `x2`/`duo` vira Duo, `x3` vira Trio e `x4`/`x5` vira Team Hunt. O título fornece a vocação e o jogador em destaque, sem contar novamente essa pessoa quando ela também aparece na descrição. Se Solo e uma equipe entrarem em conflito, a equipe prevalece e o vídeo fica sinalizado para revisão. Sem evidência de grupo, a modalidade padrão é Solo.

## Banco de dados

Sem `DATABASE_URL`, a aplicação usa `data/skan_coach.db` para desenvolvimento local. Com `DATABASE_URL`, usa PostgreSQL no Neon; mantenha essa URL como variável secreta no serviço de hospedagem. Na primeira inicialização de um banco Neon vazio, o catálogo e os registros locais existentes são carregados a partir do SQLite empacotado.

O arquivo `data/playlist_videos.csv` é uma exportação conveniente para análise. O banco configurado pela aplicação é a fonte usada pelo catálogo e pelo Portal.

## Hospedagem

O Render inicia o servidor pelo comando `python -m backend.app`, definido nos arquivos de deploy. Configure nele `DATABASE_URL`, `YOUTUBE_API_KEY`, `SKAN_ADMIN_KEY` e, se usar notificações, as variáveis SMTP. Não coloque chaves no frontend.

O GitHub Pages publica a pasta `frontend/` pelo workflow em `.github/workflows/pages.yml`. Para separar frontend e API, configure `SKAN_API_BASE` em `frontend/api-config.js` com a URL pública do servidor e `SKAN_ALLOWED_ORIGINS` no Render com a origem do GitHub Pages.

Mais detalhes de configuração estão em [`NEON_SETUP.md`](NEON_SETUP.md) e [`frontend/README.md`](frontend/README.md).

## Executar os testes

Na pasta raiz do projeto:

```powershell
python -m unittest discover -s tests -v
```
