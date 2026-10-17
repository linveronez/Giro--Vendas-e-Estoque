import os

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from core.models import Item


class Command(BaseCommand):
    help = "Cria perfis e dados fictícios da demonstração."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-stock",
            action="store_true",
            help="Restaura os estoques iniciais do catálogo de demonstração após confirmação.",
        )

    def handle(self, *args, **options):
        postgres = connection.vendor == "postgresql"
        demo_password = os.environ.get("DEMO_PASSWORD", "")
        if postgres and not demo_password.strip():
            raise CommandError(
                "O seed no PostgreSQL exige DEMO_PASSWORD no ambiente para criar/atualizar o usuário demo."
            )

        reset_stock = options["reset_stock"]
        if reset_stock and not self._confirm_stock_reset():
            self.stdout.write(self.style.WARNING("Operação cancelada; nenhum dado foi alterado."))
            return

        products = [
            ("Café coado", "Bebidas quentes", "☕", "3.00", 40, 10),
            ("Cappuccino", "Bebidas quentes", "☕", "5.50", 25, 8),
            ("Chocolate quente", "Bebidas quentes", "🍫", "6.00", 20, 8),
            ("Chá", "Bebidas quentes", "🍵", "3.50", 4, 10),
            ("Coca-Cola lata", "Bebidas frias", "🥤", "6.00", 36, 12),
            ("Guaraná lata", "Bebidas frias", "🥤", "5.50", 24, 12),
            ("Suco de laranja", "Bebidas frias", "🍊", "5.00", 18, 6),
            ("Água mineral", "Bebidas frias", "💧", "3.00", 50, 15),
            ("Coxinha", "Salgados", "🍗", "7.00", 22, 10),
            ("Pão de queijo", "Salgados", "🧀", "4.00", 30, 10),
            ("Esfiha de carne", "Salgados", "🥙", "6.50", 3, 8),
            ("Empada", "Salgados", "🥧", "6.00", 14, 5),
            ("Brigadeiro", "Doces", "🍫", "3.00", 30, 10),
            ("Brownie", "Doces", "🍰", "6.50", 12, 5),
            ("Barra de cereal", "Doces", "🌾", "3.50", 20, 6),
            ("Bala", "Doces", "🍬", "0.50", 100, 30),
            ("Misto quente", "Lanches", "🥪", "9.00", 10, 4),
            ("Pão na chapa", "Lanches", "🍞", "5.00", 15, 5),
            ("Sanduíche natural", "Lanches", "🥗", "10.00", 0, 3),
        ]

        with transaction.atomic():
            for nome, categoria, emoji, preco, estoque_inicial, minimo in products:
                item, created = Item.objects.get_or_create(
                    nome=nome,
                    defaults={
                        "categoria": categoria,
                        "emoji": emoji,
                        "preco": preco,
                        "estoque": estoque_inicial,
                        "estoque_minimo": minimo,
                    },
                )
                if created:
                    continue

                item.categoria = categoria
                item.emoji = emoji
                item.preco = preco
                item.estoque_minimo = minimo
                item.ativo = True
                if reset_stock or not item.vendaitem_set.exists():
                    item.estoque = estoque_inicial
                item.save()

            self._remove_legacy_products(("Refrigerante lata", "Suco natural", "Cookie", "Bolo do dia"))
            if postgres:
                self._seed_postgres_demo_user(demo_password)
            else:
                self._seed_local_users()

        self.stdout.write(self.style.SUCCESS(f"{len(products)} produtos de demonstração verificados."))
        if reset_stock:
            self.stdout.write(self.style.SUCCESS("Estoque inicial restaurado para o catálogo de demonstração."))

    def _confirm_stock_reset(self) -> bool:
        self.stdout.write(
            self.style.WARNING(
                "Atenção: o reset substituirá o estoque atual dos produtos de demonstração, "
                "inclusive os que já possuem vendas."
            )
        )
        try:
            confirmation = input("Digite RESETAR para confirmar: ").strip()
        except EOFError:
            confirmation = ""
        return confirmation == "RESETAR"

    def _remove_legacy_products(self, names):
        for nome in names:
            antigo = Item.objects.filter(nome=nome).first()
            if not antigo:
                continue
            if antigo.vendaitem_set.exists():
                antigo.ativo = False
                antigo.save(update_fields=["ativo", "atualizado_em"])
            else:
                antigo.delete()

    def _seed_local_users(self):
        users = [
            ("Dono", "dono", True),
            ("Coordenador", "coordenador", False),
            ("Atendente", "atendente", False),
        ]
        for group_name, username, is_staff in users:
            group, _ = Group.objects.get_or_create(name=group_name)
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": group_name,
                    "is_staff": is_staff,
                    "is_superuser": group_name == "Dono",
                },
            )
            if created:
                user.set_password("123456")
            user.is_staff = is_staff
            user.groups.set([group])
            user.save()
            status = "criado" if created else "atualizado"
            self.stdout.write(self.style.SUCCESS(f"Usuário local {username} {status}."))

    def _seed_postgres_demo_user(self, password: str):
        group, _ = Group.objects.get_or_create(name="Dono")
        user, created = User.objects.get_or_create(
            username="demo",
            defaults={"first_name": "Demo"},
        )
        user.first_name = "Demo"
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.groups.set([group])
        user.save()
        status = "criado" if created else "atualizado"
        self.stdout.write(self.style.SUCCESS(f"Usuário de demonstração demo {status} no PostgreSQL."))
