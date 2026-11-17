# Preparar o Skan Coach para Neon + Render + GitHub Pages

## O que já está preparado

- O projeto continua usando SQLite quando `DATABASE_URL` não está definida, para
  manter o uso local como antes.
- Com `DATABASE_URL`, o servidor e o importador usam PostgreSQL via psycopg.
- Na primeira inicialização com Neon vazio, o servidor cria o esquema e semeia
  o catálogo do arquivo `skan_coach.db`. Também importa registros locais de
  feedbacks, doações, fontes e pedidos de divulgação quando essas tabelas existem.
- As chamadas da interface podem usar a URL externa da API em `interface/api-config.js`.
- `Procfile` informa ao provedor como iniciar o serviço Python.

## Configuração quando criar as contas

1. Crie um projeto PostgreSQL no Neon e copie a connection string com SSL.
2. Publique o código como Web Service Python no Render, usando a pasta raiz do
   projeto. O comando de inicialização está no `Procfile`.
3. No painel de variáveis do Render, configure `DATABASE_URL` com a string do
   Neon e marque-a como secreta. Nunca coloque essa string no GitHub ou no
   `api-config.js`.
4. Configure `SKAN_HOST=0.0.0.0`, `SKAN_ADMIN_KEY`, `YOUTUBE_API_KEY` e
   `SKAN_ALLOWED_ORIGINS=https://SEU-USUARIO.github.io`. O Render fornece `PORT`.
5. Em `interface/api-config.js`, defina `SKAN_API_BASE` para o endereço público
   do Web Service Render (ex.: `https://skan-hunt-api.onrender.com`, sem barra
   final). Esse endereço é público; não é uma senha.
6. Publique os arquivos da pasta `interface/` no GitHub Pages.

## Migração do catálogo atual

O primeiro início com um banco Neon vazio importa as tabelas de vídeos,
playlists e ligações a partir de `skan_coach.db`. Também copia os registros de
comunidade locais disponíveis. A cópia do catálogo só ocorre quando a tabela
`videos` no Neon está vazia; depois disso, Neon é a fonte principal de dados.

Não apague nem substitua o `skan_coach.db` empacotado antes da primeira carga.
Depois da implantação, novos vídeos importados pelo Portal serão gravados no
Neon porque o importador recebe a mesma variável `DATABASE_URL`.

## E-mail

O envio SMTP atual funciona em ambientes locais compatíveis. Alguns provedores
gratuitos de hospedagem bloqueiam SMTP; nesse caso, os pedidos e doações ainda
serão salvos, mas os avisos por e-mail exigirão migração para um serviço de e-mail
com API HTTPS.

## Observação sobre o plano gratuito

Neon mantém os dados no serviço de banco quando a API reinicia, mas o plano
gratuito tem limites de armazenamento, computação e transferência. Configure
exportações periódicas do banco para ter uma cópia independente.
