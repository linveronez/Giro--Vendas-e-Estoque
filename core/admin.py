from django.contrib import admin

from .models import Categoria, Item, Venda, VendaItem


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ["nome", "emoji"]
    search_fields = ["nome"]


class VendaItemInline(admin.TabularInline):
    model = VendaItem
    extra = 0
    readonly_fields = ["item", "quantidade", "valor_unitario", "custo_unitario", "subtotal", "desconto"]


@admin.register(Venda)
class VendaAdmin(admin.ModelAdmin):
    list_display = ["id", "atendente", "subtotal", "desconto", "total", "desconto_aplicado_por", "criado_em"]
    list_filter = ["criado_em", "atendente"]
    search_fields = ["atendente__username"]
    readonly_fields = ["subtotal", "desconto", "total", "desconto_aplicado_por", "desconto_motivo"]
    inlines = [VendaItemInline]


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ["nome", "categoria", "preco", "custo", "estoque", "estoque_minimo", "ativo"]
    list_filter = ["ativo", "categoria"]
    search_fields = ["nome", "categoria"]
