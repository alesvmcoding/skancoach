# Neon, Render e GitHub Pages

O projeto pode usar SQLite localmente e PostgreSQL no Neon quando a variável secreta `DATABASE_URL` está definida.

## Estrutura de publicação

- Render executa o servidor Python com `python -m backend.app` (configurado no `Procfile` e em `render.yaml`).
- O servidor usa Neon para catálogo, feedback, doações, fontes e solicitações quando `DATABASE_URL` está configurada.
- GitHub Pages publica a pasta `frontend/`; o workflow está em `.github/workflows/pages.yml`.

## Variáveis do servidor

Configure no Render, como segredos quando aplicável:

- `DATABASE_URL`: connection string do Neon.
- `YOUTUBE_API_KEY`: permite importar e atualizar fontes do YouTube.
- `SKAN_ADMIN_KEY`: chave de acesso ao Portal administrativo.
- `SKAN_ALLOWED_ORIGINS`: origem do frontend, se ele estiver hospedado em domínio separado.
- `SKAN_SMTP_USER`, `SKAN_SMTP_PASSWORD` e, se necessário, `SKAN_SMTP_HOST`/`SKAN_SMTP_PORT`: envio de notificações por e-mail.

Não coloque essas chaves nos arquivos públicos do frontend. `frontend/api-config.js` contém somente `SKAN_API_BASE`, a URL pública do servidor.

## Carga inicial do banco

Se a tabela do catálogo no Neon estiver vazia, o servidor inicializa o esquema e carrega o catálogo de `data/skan_coach.db`. Registros locais de feedback, doações e fontes também podem ser carregados quando existem no SQLite. Depois da primeira carga, o Neon passa a ser a fonte principal. Preserve o banco em `data/` para a carga inicial.

O importador usa a mesma `DATABASE_URL` do servidor; novas importações do Portal são gravadas no Neon.

## Cópia de segurança

Mantenha exportações periódicas dos dados do Neon. Os limites de armazenamento, computação e transferência dependem do plano configurado no serviço.
