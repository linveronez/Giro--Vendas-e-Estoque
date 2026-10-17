from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("itens/", views.itens, name="itens"),
    path("categorias/criar/", views.criar_categoria, name="criar_categoria"),
    path("itens/<int:item_id>/preco/", views.atualizar_preco_item, name="atualizar_preco_item"),
    path("itens/<int:item_id>/custo/", views.atualizar_custo_item, name="atualizar_custo_item"),
    path("itens/<int:item_id>/estoque/", views.atualizar_estoque_item, name="atualizar_estoque_item"),
    path("itens/<int:item_id>/excluir/", views.excluir_item, name="excluir_item"),
    path("vendas/", views.vendas, name="vendas"),
    path("vendas/<int:venda_id>/cancelar/", views.cancelar_venda, name="cancelar_venda"),
    path("relatorios/", views.relatorios, name="relatorios"),
    path("relatorios/exportar/vendas.csv", views.exportar_vendas_csv, name="exportar_vendas_csv"),
    path("relatorios/exportar/estoque.csv", views.exportar_estoque_csv, name="exportar_estoque_csv"),
    path("relatorios/exportar/produtos.csv", views.exportar_produtos_csv, name="exportar_produtos_csv"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("service-worker.js", views.service_worker, name="service_worker"),
    path("offline/", views.offline, name="offline"),
]
