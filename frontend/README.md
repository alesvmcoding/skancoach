# Frontend do Skan Coach

A pasta `frontend/` contém os arquivos estáticos do site: catálogo, filtros, páginas de divulgação e portal, estilos, ícones e configuração da URL da API. O servidor em `backend/app.py` entrega esses arquivos e fornece os recursos de comunidade e administração.

## Rodar localmente

Na pasta raiz do projeto, execute:

```powershell
python -m backend.app
```

Acesse `http://127.0.0.1:8000`. O catálogo local usa `data/skan_coach.db`; a importação do YouTube exige `YOUTUBE_API_KEY`. Feedback, solicitações e funções do Portal são enviados ao servidor, então não funcionam ao abrir os HTMLs diretamente como arquivos.

## Páginas

- `index.html`: busca e filtros do catálogo, vídeos, XP Raw, profit e feedbacks.
- `divulgar.html`: informações para criadores e formulário de solicitação de divulgação.
- `portal.html`: ferramentas administrativas para fontes, atualizações e contribuições.

O tema claro/escuro e o layout responsivo são controlados por `app.js`, `portal.js`, `divulgar.js` e `styles.css`.

## Publicação separada do frontend

O GitHub Pages publica esta pasta pelo workflow em `.github/workflows/pages.yml`. Para conectar ao backend hospedado, informe a URL pública da API em `api-config.js` e configure `SKAN_ALLOWED_ORIGINS` no servidor com a origem do site. Chaves administrativas, do YouTube, de banco e de e-mail ficam apenas no servidor.

Consulte o [`README.md`](../README.md) na raiz para conhecer o propósito e as funções do Skan Coach. Consulte [`NEON_SETUP.md`](../NEON_SETUP.md) para configuração do banco e hospedagem.
