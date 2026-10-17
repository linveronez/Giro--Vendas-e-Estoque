from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("itens/", views.itens, name="itens"),
    path("itens/<int:item_id>/preco/", views.atualizar_preco_item, name="atualizar_preco_item"),
    path("itens/<int:item_id>/estoque/", views.atualizar_estoque_item, name="atualizar_estoque_item"),
    path("itens/<int:item_id>/excluir/", views.excluir_item, name="excluir_item"),
    path("vendas/", views.vendas, name="vendas"),
    path("vendas/<int:venda_id>/cancelar/", views.cancelar_venda, name="cancelar_venda"),
    path("relatorios/", views.relatorios, name="relatorios"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("service-worker.js", views.service_worker, name="service_worker"),
    path("offline/", views.offline, name="offline"),
]
