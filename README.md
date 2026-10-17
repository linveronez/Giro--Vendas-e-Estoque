# Giro — Vendas e Estoque

Sistema web acadêmico para pequenos negócios registrarem vendas e acompanharem o estoque. A tela de caixa permite buscar produtos pelo nome ou filtrar por categoria, montar uma venda com poucos toques e conferir o total por forma de pagamento.

## Para a banca

O Giro é um protótipo acadêmico de sistema web para pequenos negócios. Ele demonstra como registrar vendas, atualizar o estoque, consultar resumo de vendas e exportar dados em CSV. A aplicação de novos descontos foi retirada temporariamente; registros históricos permanecem preservados e visíveis. Cancelar uma venda devolve as quantidades ao estoque, mas não faz reembolso financeiro. O catálogo e os registros de demonstração são fictícios.

O código Django é publicado no Render e os dados da versão online ficam no PostgreSQL do Neon. O projeto também pode ser executado localmente com SQLite. Como a hospedagem gratuita pode suspender a aplicação após um período sem acesso, o primeiro carregamento pode levar até um minuto. O manifest e o ícone permitem usar o Giro como atalho de aplicativo; as telas e os dados não ficam disponíveis sem conexão.

**Repositório:** [github.com/linveronez/Giro--Vendas-e-Estoque](https://github.com/linveronez/Giro--Vendas-e-Estoque)

## O que o sistema faz

- Cadastra produtos em categorias gerenciáveis pela tela de Produtos; categorias novas também aparecem nos filtros do Caixa.
- Registra vendas com um ou mais produtos e pagamento em dinheiro, Pix, cartão de débito ou cartão de crédito.
- Registra vendas pelo valor integral; descontos estão temporariamente desativados. O sistema preserva eventuais descontos de vendas antigas no histórico.
- Atualiza o estoque automaticamente e impede vender mais unidades do que estão disponíveis.
- Guarda o custo unitário do produto no item vendido, preservando o histórico quando o custo atual muda. O Resumo calcula lucro e margem brutos usando apenas itens com custo conhecido.
- Permite lançar um item avulso com descrição, preço e quantidade. O item aparece no histórico da venda, mas não movimenta o estoque.
- Permite cancelar uma venda, devolvendo os produtos cadastrados ao estoque.
- Exibe resumo por período, totais por forma de pagamento, produtos mais vendidos, reposição de estoque e histórico de cancelamentos; o ranking e a reposição podem ser filtrados por categoria.
- Permite ao Dono e ao Gerente exportar vendas do período, estoque atual e produtos cadastrados em CSV compatível com planilhas.
- Usa dados fictícios para a demonstração. O fluxo de venda não exige cadastro de clientes nem armazena fotos ou comprovantes.

## Tecnologias

- Python e Django
- SQLite para desenvolvimento local
- PostgreSQL para hospedagem
- HTML, CSS e JavaScript puro para a interface

## Executar localmente

Requer uma versão de Python compatível com as dependências em `requirements.txt`.

```powershell
git clone https://github.com/linveronez/Giro--Vendas-e-Estoque.git
cd Giro--Vendas-e-Estoque
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py seed
python manage.py runserver
```

Abra <http://127.0.0.1:8000>. Em SQLite, `seed` cria o catálogo de demonstração e os usuários locais `dono`, `gerente` e `atendente` (senha `123456`). Essas credenciais servem apenas para desenvolvimento local. A migração renomeia o grupo Coordenador para Gerente e conserva seus membros.

O seed é idempotente: pode ser repetido sem duplicar produtos ou usuários. O catálogo inclui produtos em estoque baixo e um esgotado para demonstrar os alertas e o bloqueio de venda. Sem `--reset-stock`, ele preserva o estoque atual dos produtos que já tenham vendas. Para restaurar os estoques iniciais, execute `python manage.py seed --reset-stock` e confirme digitando `RESETAR`; isso também afeta produtos que já tenham histórico de vendas.

Em PostgreSQL, o seed não cria os usuários locais nem usa senha fixa. Configure `DEMO_PASSWORD` no ambiente antes de executar `python manage.py seed`; sem essa variável, o comando falha antes de alterar dados. Ele cria ou atualiza apenas o usuário `demo` com a senha fornecida pelo ambiente.

## Publicar no Render com PostgreSQL do Neon

O arquivo `render.yaml` define o serviço web no Render, sem criar um banco temporário do próprio Render. A conexão com o PostgreSQL é fornecida pela variável secreta `DATABASE_URL`.

1. Crie um projeto PostgreSQL no Neon e copie a connection string.
2. No Render, crie um Blueprint a partir deste repositório.
3. Na configuração inicial do Blueprint, informe a connection string do Neon em `DATABASE_URL`. Se o serviço ou Blueprint já existir, preencha ou atualize `DATABASE_URL` manualmente na área **Environment** do serviço.
4. Mantenha `DEBUG=False` e deixe o Render gerar `SECRET_KEY`.
5. Faça o deploy. O comando de inicialização aplica as migrações antes de iniciar o Django.
6. Depois que o primeiro deploy concluir as migrações, crie seu usuário no Neon. Como o plano gratuito do Render não oferece Shell, faça isso pelo PowerShell, na pasta do projeto e com as dependências instaladas:

   ```bash
   $env:DATABASE_URL = Read-Host "Cole a connection string do Neon"
   python manage.py createsuperuser
   Remove-Item Env:DATABASE_URL
   ```

   O comando cria o usuário diretamente no Neon. Informe um nome e uma senha próprios; não use as credenciais locais de demonstração (`dono`, `coordenador` ou `atendente`).

Não publique a connection string, a `SECRET_KEY` ou credenciais de acesso no GitHub. O primeiro acesso ao serviço pode levar mais tempo se a aplicação estiver inativa. O banco e o serviço web podem suspender recursos em planos gratuitos; consulte os limites atuais dos provedores e mantenha um backup dos dados importantes.

> No Render, variáveis `sync: false` são solicitadas na criação inicial do Blueprint. Em atualizações de um Blueprint existente, o Render não solicita novamente esse valor; configure-o diretamente no painel do serviço. [Referência oficial de Blueprints do Render](https://render.com/docs/blueprint-spec).

## Roteiro de demonstração

1. Abra **Produtos** e mostre o catálogo, o estoque baixo e o produto esgotado.
2. No **Caixa**, filtre por uma categoria ou digite parte do nome. Adicione produtos e ajuste quantidades no carrinho.
3. Escolha a forma de pagamento e finalize a venda; confira a baixa no estoque.
4. Registre, se desejar, um item avulso para demonstrar uma venda sem movimentação de estoque.
5. Abra **Resumo**, selecione um período, confira totais e produtos mais vendidos e cancele uma venda para mostrar a devolução do estoque.

O Resumo preserva eventuais descontos históricos e exibe custo dos itens com custo informado, lucro bruto e margem bruta. A margem exclui itens sem custo conhecido, como itens avulsos; ela não representa lucro líquido, pois não desconta despesas, impostos ou taxas. O cancelamento é interno ao sistema e não estorna pagamentos. Voucher e estorno financeiro não fazem parte desta versão.

Este projeto é um protótipo acadêmico. Não use dados pessoais ou financeiros reais.
