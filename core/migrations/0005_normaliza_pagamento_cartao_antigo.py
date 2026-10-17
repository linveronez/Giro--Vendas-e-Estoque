from django.db import migrations


def normaliza_cartao(apps, schema_editor):
    Venda = apps.get_model("core", "Venda")
    Venda.objects.filter(forma_pagamento="cartao").update(forma_pagamento="cartao_historico")


def reverte_cartao(apps, schema_editor):
    Venda = apps.get_model("core", "Venda")
    Venda.objects.filter(forma_pagamento="cartao_historico").update(forma_pagamento="cartao")


class Migration(migrations.Migration):
    dependencies = [("core", "0004_item_emoji_vendaitem_avulso_and_more")]

    operations = [migrations.RunPython(normaliza_cartao, reverte_cartao)]
