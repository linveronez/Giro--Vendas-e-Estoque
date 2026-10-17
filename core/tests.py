import os
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
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
            total=Decimal("12.00"),
            forma_pagamento="pix",
            status="concluida",
            criado_em=hoje,
        )
        Venda.objects.create(
            atendente=self.user,
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

        cafe = Item.objects.get(nome="Café coado")
        cafe.estoque = 3
        cafe.save(update_fields=["estoque"])
        venda = Venda.objects.create(
            atendente=User.objects.get(username="dono"),
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
