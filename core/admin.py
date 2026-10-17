from django.contrib import admin

from .models import Categoria, Cliente, Item, MovimentoCredito, Venda, VendaItem


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
    list_display = ["id", "cliente", "atendente", "subtotal", "desconto", "total", "desconto_aplicado_por", "criado_em"]
    list_filter = ["criado_em", "atendente"]
    search_fields = ["cliente__nome", "atendente__username"]
    readonly_fields = ["subtotal", "desconto", "total", "desconto_aplicado_por", "desconto_motivo"]
    inlines = [VendaItemInline]


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ["nome", "documento", "telefone", "credito", "atualizado_em"]
    search_fields = ["nome", "documento", "telefone"]


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ["nome", "categoria", "preco", "custo", "estoque", "estoque_minimo", "ativo"]
    list_filter = ["ativo", "categoria"]
    search_fields = ["nome", "categoria"]


@admin.register(MovimentoCredito)
class MovimentoCreditoAdmin(admin.ModelAdmin):
    list_display = ["cliente", "usuario", "valor", "tipo", "criado_em"]
    list_filter = ["tipo", "criado_em"]
    search_fields = ["cliente__nome", "usuario__username"]
