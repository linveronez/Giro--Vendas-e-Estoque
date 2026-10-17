import os
from decimal import Decimal
from importlib import import_module
from unittest.mock import patch

from django.apps import apps as django_apps
from django.contrib.auth.models import Group, User
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Item, Venda, VendaItem


class GiroSalesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="test-owner",
            password="test-password-only",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)
        self.item = Item.objects.create(
            nome="Café de teste",
            categoria="Bebidas quentes",
            preco=Decimal("3.50"),
            custo=Decimal("1.25"),
            estoque=5,
            estoque_minimo=1,
        )

    def post_sale(self, **data):
        payload = {"forma_pagamento": "dinheiro", **data}
        return self.client.post(reverse("vendas"), payload)

    def test_venda_normal_baixa_estoque_e_recalcula_total_no_servidor(self):
        response = self.post_sale(
            itens=[str(self.item.pk)],
            **{f"quantidade_{self.item.pk}": "2", "total": "0.01"},
        )

        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.estoque, 3)
        venda = Venda.objects.get()
        self.assertEqual(venda.total, Decimal("7.00"))
        linha = VendaItem.objects.get(venda=venda)
        self.assertEqual(linha.valor_unitario, Decimal("3.50"))
        self.assertEqual(linha.custo_unitario, Decimal("1.25"))
        self.assertEqual(linha.subtotal, Decimal("7.00"))

    def test_venda_acima_do_estoque_e_recusada_sem_alteracoes(self):
        response = self.post_sale(
            itens=[str(self.item.pk)],
            **{f"quantidade_{self.item.pk}": "6"},
        )

        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.estoque, 5)
        self.assertFalse(Venda.objects.exists())
        self.assertFalse(VendaItem.objects.exists())

    def test_produto_inativo_nao_pode_ser_vendido(self):
        self.item.ativo = False
        self.item.save(update_fields=["ativo"])

        response = self.post_sale(
            itens=[str(self.item.pk)],
            **{f"quantidade_{self.item.pk}": "1"},
        )

        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.estoque, 5)
        self.assertFalse(Venda.objects.exists())

    def test_cancelamento_devolve_estoque_uma_unica_vez(self):
        self.item.estoque = 3
        self.item.save(update_fields=["estoque"])
        venda = Venda.objects.create(
            atendente=self.user,
            subtotal=Decimal("7.00"),
            total=Decimal("7.00"),
            forma_pagamento="dinheiro",
        )
        VendaItem.objects.create(
            venda=venda,
            item=self.item,
            quantidade=2,
            valor_unitario=Decimal("3.50"),
            subtotal=Decimal("7.00"),
        )

        url = reverse("cancelar_venda", args=[venda.pk])
        first = self.client.post(url)
        self.item.refresh_from_db()
        self.assertEqual(first.status_code, 302)
        self.assertEqual(self.item.estoque, 5)
        venda.refresh_from_db()
        self.assertEqual(venda.status, "cancelada")

        second = self.client.post(url)
        self.item.refresh_from_db()
        self.assertEqual(second.status_code, 302)
        self.assertEqual(self.item.estoque, 5)

    def test_item_avulso_exige_descricao_e_preco_positivo(self):
        invalid_payloads = (
            {"avulso_descricao": [""], "avulso_preco": ["2.50"], "avulso_quantidade": ["1"]},
            {"avulso_descricao": ["Água fora do catálogo"], "avulso_preco": ["0"], "avulso_quantidade": ["1"]},
            {"avulso_descricao": ["Água fora do catálogo"], "avulso_preco": ["-1"], "avulso_quantidade": ["1"]},
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                self.post_sale(**payload)
                self.assertFalse(Venda.objects.exists())
                self.item.refresh_from_db()
                self.assertEqual(self.item.estoque, 5)

    def test_venda_avulsa_valida_nao_altera_estoque(self):
        response = self.post_sale(
            avulso_descricao=["Água fora do catálogo"],
            avulso_preco=["2.75"],
            avulso_quantidade=["2"],
            total="9999.99",
        )

        self.assertEqual(response.status_code, 302)
        venda = Venda.objects.get()
        linha = VendaItem.objects.get(venda=venda)
        self.item.refresh_from_db()
        self.assertEqual(venda.total, Decimal("5.50"))
        self.assertEqual(linha.item_id, None)
        self.assertTrue(linha.avulso)
        self.assertEqual(self.item.estoque, 5)

    def test_relatorio_ignora_vendas_canceladas_nos_totais_por_pagamento(self):
        hoje = timezone.now()
        Venda.objects.create(
            atendente=self.user,
            subtotal=Decimal("12.00"),
            total=Decimal("12.00"),
            forma_pagamento="pix",
            status="concluida",
            criado_em=hoje,
        )
        Venda.objects.create(
            atendente=self.user,
            subtotal=Decimal("90.00"),
            total=Decimal("90.00"),
            forma_pagamento="pix",
            status="cancelada",
            criado_em=hoje,
        )

        response = self.client.get(reverse("relatorios"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_periodo"], Decimal("12.00"))
        self.assertEqual(response.context["quantidade_vendas"], 1)
        pix = next(item for item in response.context["pagamentos_periodo"] if item["nome"] == "Pix")
        self.assertEqual(pix["total"], Decimal("12.00"))

    def test_estoque_nao_aceita_valores_negativos_no_banco(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Item.objects.filter(pk=self.item.pk).update(estoque=-1)


class V02ControlsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner-v02",
            password="test-password-only",
            is_staff=True,
            is_superuser=True,
        )
        self.manager = User.objects.create_user(username="manager-v02", password="test-password-only")
        self.manager.groups.add(Group.objects.create(name="Gerente"))
        self.attendant = User.objects.create_user(username="attendant-v02", password="test-password-only")
        self.attendant.groups.add(Group.objects.create(name="Atendente"))
        self.item = Item.objects.create(
            nome="Produto de teste financeiro",
            categoria="Outros",
            preco=Decimal("3.50"),
            custo=Decimal("1.25"),
            estoque=10,
            estoque_minimo=1,
        )

    def test_dono_gerente_e_atendente_respeitam_permissoes_de_resumo_csv_e_cancelamento(self):
        sale = Venda.objects.create(
            atendente=self.owner,
            subtotal=Decimal("3.50"),
            total=Decimal("3.50"),
            forma_pagamento="dinheiro",
        )
        VendaItem.objects.create(
            venda=sale,
            item=self.item,
            quantidade=1,
            valor_unitario=Decimal("3.50"),
            custo_unitario=Decimal("1.25"),
            subtotal=Decimal("3.50"),
        )
        self.client.force_login(self.owner)
        sales_csv = self.client.get(reverse("exportar_vendas_csv")).content.decode("utf-8-sig")
        self.assertIn("Produto de teste financeiro", sales_csv)
        self.assertIn("Custo unitário histórico", sales_csv)
        urls = [
            reverse("exportar_vendas_csv"),
            reverse("exportar_estoque_csv"),
            reverse("exportar_produtos_csv"),
        ]
        for user, expected in ((self.owner, 200), (self.manager, 200), (self.attendant, 302)):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse("relatorios")).status_code, expected)
                for url in urls:
                    self.assertEqual(self.client.get(url).status_code, expected)

        for user in (self.owner, self.manager, self.attendant):
            with self.subTest(product_page_user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse("itens")).status_code, 200)

        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("vendas")).status_code, 200)

        self.item.estoque = 0
        self.item.save(update_fields=["estoque"])
        self.client.force_login(self.owner)
        self.client.post(reverse("cancelar_venda", args=[sale.pk]))
        self.item.refresh_from_db()
        self.assertEqual(self.item.estoque, 1)

        manager_sale = Venda.objects.create(atendente=self.manager, subtotal=Decimal("0.00"), total=Decimal("0.00"))
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(reverse("cancelar_venda", args=[manager_sale.pk])).status_code, 302)
        manager_sale.refresh_from_db()
        self.assertEqual(manager_sale.status, "cancelada")

        attendant_sale = Venda.objects.create(atendente=self.attendant, subtotal=Decimal("0.00"), total=Decimal("0.00"))
        self.client.force_login(self.attendant)
        self.client.post(reverse("cancelar_venda", args=[attendant_sale.pk]))
        attendant_sale.refresh_from_db()
        self.assertEqual(attendant_sale.status, "concluida")

    def test_desconto_e_custo_historico_calculam_lucro_e_margem(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("vendas"),
            {
                "forma_pagamento": "pix",
                "itens": [str(self.item.pk)],
                f"quantidade_{self.item.pk}": "2",
                "desconto": "1.00",
                "desconto_motivo": "Promoção de teste",
            },
        )
        self.assertEqual(response.status_code, 302)
        sale = Venda.objects.get()
        line = VendaItem.objects.get(venda=sale)
        self.assertEqual(sale.subtotal, Decimal("7.00"))
        self.assertEqual(sale.desconto, Decimal("1.00"))
        self.assertEqual(sale.total, Decimal("6.00"))
        self.assertEqual(sale.desconto_aplicado_por, self.owner)
        self.assertEqual(sale.desconto_motivo, "Promoção de teste")
        self.assertEqual(line.custo_unitario, Decimal("1.25"))
        self.assertEqual(line.desconto, Decimal("1.00"))
        report = self.client.get(reverse("relatorios"))
        self.assertEqual(report.context["desconto_periodo"], Decimal("1.00"))
        self.assertEqual(report.context["lucro_bruto"], Decimal("3.50"))
        self.assertAlmostEqual(float(report.context["margem_bruta"]), 58.33, places=2)

    def test_desconto_acima_do_subtotal_ou_sem_motivo_e_recusado(self):
        self.client.force_login(self.owner)
        base = {"forma_pagamento": "dinheiro", "itens": [str(self.item.pk)]}
        payloads = (
            {**base, "desconto": "3.51", "desconto_motivo": "Excesso"},
            {**base, "desconto": "1.00", "desconto_motivo": ""},
            {**base, "desconto": "-1.00", "desconto_motivo": "Invalido"},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                self.client.post(reverse("vendas"), payload)
                self.assertFalse(Venda.objects.exists())
                self.item.refresh_from_db()
                self.assertEqual(self.item.estoque, 10)

    def test_csv_produtos_protege_texto_de_formula_de_planilha(self):
        self.item.nome = "=HYPERLINK(\"https://example.invalid\")"
        self.item.save(update_fields=["nome"])
        self.client.force_login(self.manager)
        response = self.client.get(reverse("exportar_produtos_csv"))
        content = response.content.decode("utf-8-sig")
        self.assertIn(";Preço;Custo;Lucro bruto unitário;Margem bruta (%)", content)
        self.assertIn("'=HYPERLINK", content)


class GroupMigrationTests(TestCase):
    def test_migracao_renomeia_coordenador_sem_perder_membros(self):
        migration = import_module("core.migrations.0007_v02_financial_controls")
        old_group = Group.objects.create(name="Coordenador")
        manager_group = Group.objects.create(name="Gerente")
        old_user = User.objects.create_user(username="old-manager")
        new_user = User.objects.create_user(username="new-manager")
        old_user.groups.add(old_group)
        new_user.groups.add(manager_group)
        legacy_sale = Venda.objects.create(atendente=old_user, subtotal=Decimal("0.00"), total=Decimal("5.00"))
        legacy_sale.subtotal = Decimal("0.00")
        legacy_sale.save(update_fields=["subtotal"])

        migration.preencher_subtotais_e_renomear_perfil(django_apps, None)

        self.assertFalse(Group.objects.filter(name="Coordenador").exists())
        manager_group = Group.objects.get(name="Gerente")
        self.assertTrue(old_user.groups.filter(pk=manager_group.pk).exists())
        self.assertTrue(new_user.groups.filter(pk=manager_group.pk).exists())
        legacy_sale.refresh_from_db()
        self.assertEqual(legacy_sale.subtotal, Decimal("5.00"))


class SeedCommandTests(TestCase):
    def test_seed_postgres_exige_demo_password_antes_de_alterar_dados(self):
        with patch("core.management.commands.seed.connection.vendor", "postgresql"):
            with patch.dict(os.environ, {"DEMO_PASSWORD": ""}):
                with self.assertRaisesMessage(CommandError, "DEMO_PASSWORD"):
                    call_command("seed", verbosity=0)
        self.assertFalse(Item.objects.exists())
        self.assertFalse(User.objects.exists())

    def test_seed_postgres_cria_apenas_usuario_demo_com_senha_do_ambiente(self):
        with patch("core.management.commands.seed.connection.vendor", "postgresql"):
            with patch.dict(os.environ, {"DEMO_PASSWORD": "temporary-test-password"}):
                call_command("seed", verbosity=0)

        self.assertEqual(list(User.objects.values_list("username", flat=True)), ["demo"])
        self.assertTrue(User.objects.get(username="demo").check_password("temporary-test-password"))

    def test_seed_local_e_idempotente_e_reset_stock_pede_confirmacao(self):
        call_command("seed", verbosity=0)
        call_command("seed", verbosity=0)
        self.assertEqual(Item.objects.count(), 19)
        self.assertEqual(User.objects.count(), 3)
        self.assertTrue(Group.objects.filter(name="Gerente").exists())
        self.assertTrue(User.objects.get(username="gerente").groups.filter(name="Gerente").exists())

        cafe = Item.objects.get(nome="Café coado")
        cafe.estoque = 3
        cafe.save(update_fields=["estoque"])
        venda = Venda.objects.create(
            atendente=User.objects.get(username="dono"),
            subtotal=Decimal("3.00"),
            total=Decimal("3.00"),
        )
        VendaItem.objects.create(
            venda=venda,
            item=cafe,
            quantidade=1,
            valor_unitario=Decimal("3.00"),
            subtotal=Decimal("3.00"),
        )

        with patch("builtins.input", return_value="não"):
            call_command("seed", reset_stock=True, verbosity=0)
        cafe.refresh_from_db()
        self.assertEqual(cafe.estoque, 3)

        with patch("builtins.input", return_value="RESETAR"):
            call_command("seed", reset_stock=True, verbosity=0)
        cafe.refresh_from_db()
        self.assertEqual(cafe.estoque, 40)


class LoginPageTests(TestCase):
    def test_login_exibe_aviso_de_inatividade_sem_credenciais(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Primeiro acesso após inatividade pode levar até 1 minuto.")
        self.assertNotContains(response, "123456")
