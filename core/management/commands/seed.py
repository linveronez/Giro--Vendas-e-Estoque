from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from core.models import Item


class Command(BaseCommand):
    help = "Cria perfis e usuarios iniciais do sistema."

    def handle(self, *args, **options):
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
        for nome, categoria, emoji, preco, estoque, minimo in products:
            item, created = Item.objects.get_or_create(
                nome=nome,
                defaults={"categoria": categoria, "emoji": emoji, "preco": preco, "estoque": estoque, "estoque_minimo": minimo},
            )
            if not created:
                item.categoria = categoria
                item.emoji = emoji
                item.preco = preco
                item.estoque_minimo = minimo
                item.ativo = True
                if not item.vendaitem_set.exists():
                    item.estoque = estoque
                item.save()
        for nome_antigo in ("Refrigerante lata", "Suco natural", "Cookie", "Bolo do dia"):
            antigo = Item.objects.filter(nome=nome_antigo).first()
            if antigo:
                if antigo.vendaitem_set.exists():
                    antigo.ativo = False
                    antigo.save(update_fields=["ativo", "atualizado_em"])
                else:
                    antigo.delete()
        self.stdout.write(self.style.SUCCESS(f"{len(products)} produtos de demonstração verificados."))

        users = [
            ("Dono", "dono", "123456", True),
            ("Coordenador", "coordenador", "123456", False),
            ("Atendente", "atendente", "123456", False),
        ]
        for group_name, username, password, is_staff in users:
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
                user.set_password(password)
            user.is_staff = is_staff
            user.groups.set([group])
            user.save()
            status = "criado" if created else "atualizado"
            self.stdout.write(self.style.SUCCESS(f"Usuario {username} {status}."))
