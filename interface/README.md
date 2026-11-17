# Interface local do Skan Coach

Esta interface consulta diretamente o arquivo `skan_coach.db` da pasta pai.
Não precisa de chave da API nem de conexão com a internet para buscar os dados.
As miniaturas e a abertura dos vídeos usam links públicos do YouTube.

## Feedback das hunts

Os cards têm ações separadas: **Testei esta hunt** abre o formulário e **Ver feedback**
abre os relatos publicados; o botão mostra a quantidade de relatos daquele vídeo.
O formulário permite compartilhar vocação, level, XP Raw, profit, dificuldade,
resultado e se o vídeo parece desatualizado. Os relatos ficam associados ao vídeo
na tabela `hunt_feedback` do SQLite. Inicie o servidor
Python com `python app.py` para usar a API; abrir o HTML diretamente por `file://`
não permite enviar ou carregar feedback.

## Portal de comunidade e administração

`divulgar.html` aceita pedidos para analisar um canal ou vídeo e explica
os requisitos de título: o canal precisa usar números junto de XP ou Profit/Waste
para o importador localizar hunts. Canais podem conter várias vocações; o portal
não exige uma única vocação e o catálogo tenta identificar cada vídeo pelo título.
Vídeos sem vocação clara continuam visíveis em “Todas”. Vídeos individuais podem
ser importados pelo portal administrativo.

Abra `portal.html` pelo menu e use as variáveis de ambiente `SKAN_ADMIN_KEY` e
`YOUTUBE_API_KEY`. O portal importa/remover playlist, canal ou vídeo individual,
atualiza todas as fontes pelo botão **Atualizar todas as fontes**, revisa as
contribuições pendentes em Tibia Coins e marca fontes como patrocinadas. A atualização
consulta cada fonte cadastrada e pode levar vários minutos.
Uma marcação patrocinada é editorial: cobrança e validação do pagamento ainda são
manuais. O nome de quem contribui só aparece no ranking de TC quando a pessoa opta
por isso e o administrador confirma a transferência para **Lord Skanzin — Jadebra**.

Pedidos de divulgação e registros de doação também podem enviar avisos por e-mail
para `alesvmelo@gmail.com`. Para ativar, configure no servidor `SKAN_SMTP_USER`,
`SKAN_SMTP_PASSWORD`, `SKAN_SMTP_HOST` (padrão `smtp.gmail.com`),
`SKAN_SMTP_PORT` (padrão `587`) e `SKAN_NOTIFICATION_EMAIL` (padrão
`alesvmelo@gmail.com`). Use uma credencial SMTP de aplicativo e mantenha-a como
segredo do servidor. Se o SMTP não estiver configurado ou falhar, o pedido/doação
continua salvo no portal e o servidor registra que o aviso não foi enviado.

Para testar localmente, sem publicar o site, abra o PowerShell na pasta `interface`.
As telas e o banco local funcionam sem internet; importar conteúdo do YouTube exige
conexão e `YOUTUBE_API_KEY`. Antes de iniciar o servidor:

```powershell
$env:SKAN_ADMIN_KEY = "crie-uma-chave-secreta-forte"
$env:YOUTUBE_API_KEY = "sua-chave-da-YouTube-Data-API"
$env:SKAN_SMTP_USER = "sua-conta-de-envio@gmail.com"
$env:SKAN_SMTP_PASSWORD = "senha-de-aplicativo-do-email"
$env:SKAN_NOTIFICATION_EMAIL = "alesvmelo@gmail.com"
python .\app.py
```

O site abrirá em `http://127.0.0.1:8000`; use os links **Divulgar hunt** e **Portal**
no menu para trocar de página. Para hospedar publicamente, configure
`SKAN_HOST=0.0.0.0`, use um armazenamento persistente e mantenha as chaves como
segredos do provedor. O servidor atual usa SQLite local, por isso não deve ser
colocado num serviço gratuito que apague o disco entre reinícios sem migrar o banco.

## Preparação para GitHub Pages + API hospedada

O front-end pode ficar no GitHub Pages e chamar o servidor Python por uma URL
pública. Antes de publicar, substitua o valor vazio de `SKAN_API_BASE` em
`api-config.js` pela URL do serviço de API, sem barra final. No servidor, defina
`SKAN_ALLOWED_ORIGINS` com a origem do GitHub Pages, por exemplo
`https://seu-usuario.github.io` (sem o caminho do repositório).

O servidor já responde ao preflight CORS e aceita somente origens configuradas.
Essa configuração não publica chaves privadas no front-end: `SKAN_ADMIN_KEY`,
`YOUTUBE_API_KEY` e credenciais de e-mail permanecem no servidor.

**Ainda não publique a API gratuita com este banco.** O projeto atual usa SQLite
local; os serviços gratuitos do Render apagam o disco local quando reiniciam ou
adormecem. A API precisa ser migrada para um banco PostgreSQL externo antes do
uso comunitário. O importador de fontes também precisa gravar nesse banco para
que novas hunts e fontes sobrevivam a reinícios. O envio SMTP usa portas que o
Render Free bloqueia; para avisos por e-mail será necessário um provedor com API
HTTPS ou outro serviço compatível.

Quando essas adaptações forem concluídas, o fluxo será: publicar os arquivos de
`interface/` no GitHub Pages, publicar `interface/app.py` e o importador como
serviço Python, definir a URL pública em `api-config.js` e cadastrar a origem do
GitHub nas variáveis do servidor.

O servidor local escuta em `127.0.0.1`; para a comunidade usar as funções pela
internet, publique o app com banco persistente. GitHub Pages hospeda somente o
front-end estático. Render Free perde arquivos locais ao reiniciar e não deve
guardar feedback em SQLite local.

O ranking é em Tibia Coins, sem dinheiro real. O site registra os envios como
pendentes e só soma no ranking depois que você confirmar manualmente a transferência
no jogo. A exibição do apelido é opcional.

## Abrir direto no navegador

Você pode abrir `index.html` com duplo clique. O arquivo `catalog-data.js`
acompanha os dados do banco para que a página carregue também quando aberta
como arquivo local (`file://`). Os vídeos aparecem como cards com miniaturas;
clique em uma miniatura para abrir o vídeo no YouTube.

## Abrir pelo servidor local

1. Abra o PowerShell na pasta `interface`.
2. Execute `python .\app.py`.
3. Abra `http://127.0.0.1:8000` no navegador.
4. Para encerrar, volte ao PowerShell e pressione `Ctrl+C`.

O catálogo combina as playlists MS, EK, RP, ED e EM (Monk), com filtros por
vocação, modalidade, level e dificuldade estimada,
busca textual e ordenação por XP/h Raw, profit ou level. A dificuldade usa a
regra de referência de 10% em relação ao level do vídeo. XP Raw é mantida
quando já vem identificada no título; nos demais casos, é calculada com o
percentual informado ou com 150% presumido quando o percentual estiver ausente.
O valor original e a base do cálculo aparecem abaixo da XP Raw. Títulos com
Prey/Book Boosted recebem uma observação sobre o modificador adicional.
Profit ou Waste é extraído pelo valor associado a essas palavras; Waste aparece
como resultado negativo. Quando `/h` estiver ausente, considera-se uma hunt de
1 hora e isso aparece como observação.

O importador atualiza `catalog-data.js` quando grava o banco. O servidor local
também atualiza esse arquivo ao iniciar.

O layout se reorganiza para telas menores e o botão no topo alterna entre os
temas claro e escuro. A escolha do tema fica salva neste navegador.

Os cards mantêm o título original importado do YouTube. Quando o título não
informa o local, a interface tenta recuperar o nome da hunt e o Profit da
descrição. A XP Raw continua vindo do cálculo aplicado ao título. Vídeos sem
local, criatura ou outro indicador concreto de hunt ficam fora dos resultados,
mas continuam preservados no banco. Níveis escritos antes da vocação (por
exemplo, `940 ED`) também são reconhecidos.

