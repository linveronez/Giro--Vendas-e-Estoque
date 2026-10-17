import base64
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Case, CharField, F, Sum, When
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from .forms import ClienteForm, ClienteUpdateForm, CreditoForm, ItemEstoqueForm, ItemForm, ItemPrecoForm
from .models import Cliente, Item, MovimentoCredito, Venda, VendaItem


ROLE_OWNER = "Dono"
ROLE_COORDINATOR = "Coordenador"
ROLE_ATTENDANT = "Atendente"


def user_role(user) -> str:
    if user.is_superuser:
        return ROLE_OWNER
    group = user.groups.first()
    return group.name if group else ROLE_ATTENDANT


def can_manage_credit(user) -> bool:
    return user_role(user) in {ROLE_OWNER, ROLE_COORDINATOR}


def can_manage_clients(user) -> bool:
    return user_role(user) in {ROLE_OWNER, ROLE_COORDINATOR}


def can_debit_credit(user) -> bool:
    return user_role(user) == ROLE_OWNER


def can_manage_items(user) -> bool:
    return user_role(user) in {ROLE_OWNER, ROLE_COORDINATOR}


def can_view_reports(user) -> bool:
    return user_role(user) == ROLE_OWNER


def role_context(request) -> dict:
    return {
        "role": user_role(request.user),
        "can_manage_clients": can_manage_clients(request.user),
        "can_manage_credit": can_manage_credit(request.user),
        "can_debit_credit": can_debit_credit(request.user),
        "can_manage_items": can_manage_items(request.user),
        "can_view_reports": can_view_reports(request.user),
    }


def owner_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not can_view_reports(request.user):
            messages.error(request, "Somente o perfil Dono acessa relatorios.")
            return redirect("dashboard")
        return view_func(request, *args, **kwargs)

    return wrapper


@login_required
def dashboard(request):
    hoje = timezone.localdate()
    vendas_hoje = Venda.objects.filter(criado_em__date=hoje, status="concluida")
    hoje_total = vendas_hoje.aggregate(total=Sum("total"))["total"] or 0
    context = {
        **role_context(request),
        "itens_total": Item.objects.filter(ativo=True).count(),
        "estoque_baixo_total": Item.objects.filter(ativo=True, estoque__lte=F("estoque_minimo")).count(),
        "vendas_total": hoje_total,
        "ultimas_vendas": Venda.objects.select_related("atendente").filter(status="concluida")[:6],
    }
    return render(request, "core/dashboard.html", context)


@login_required
def clientes(request):
    if request.method == "POST":
        if not can_manage_credit(request.user):
            messages.error(request, "Atendentes nao cadastram credito inicial.")
            return redirect("clientes")
        form = ClienteForm(request.POST, request.FILES)
        if form.is_valid():
            cliente = form.save(commit=False)
            cliente.credito = form.cleaned_data.get("credito_inicial") or Decimal("0.00")
            cliente.save()
            foto = decode_camera_photo(request.POST.get("foto_base64", ""))
            if foto:
                cliente.foto.save(f"cliente-{cliente.pk}.png", foto, save=True)
            if cliente.credito:
                MovimentoCredito.objects.create(
                    cliente=cliente,
                    usuario=request.user,
                    valor=cliente.credito,
                    tipo=MovimentoCredito.CREDITO,
                    observacao="Credito inicial",
                )
            messages.success(request, "Cliente cadastrado com sucesso.")
            return redirect("clientes")
    else:
        form = ClienteForm()

    context = {
        **role_context(request),
        "form": form,
        "credito_form": CreditoForm(),
        "clientes": Cliente.objects.all(),
    }
    return render(request, "core/clientes.html", context)


@login_required
@require_POST
def atualizar_cliente(request, cliente_id):
    if not can_manage_clients(request.user):
        messages.error(request, "Somente Dono ou Coordenador atualiza cadastro de cliente.")
        return redirect("clientes")

    cliente = get_object_or_404(Cliente, pk=cliente_id)
    form = ClienteUpdateForm(request.POST, request.FILES, instance=cliente)
    if form.is_valid():
        cliente = form.save(commit=False)
        foto = decode_camera_photo(request.POST.get("foto_base64", ""))
        if form.cleaned_data["remover_foto"] and cliente.foto:
            cliente.foto.delete(save=False)
            cliente.foto = None
        if foto:
            if cliente.foto:
                cliente.foto.delete(save=False)
            cliente.foto.save(f"cliente-{cliente.pk}.png", foto, save=False)
        if form.cleaned_data["remover_comprovante_pix"] and cliente.comprovante_pix:
            cliente.comprovante_pix.delete(save=False)
            cliente.comprovante_pix = None
        cliente.save()
        messages.success(request, "Cadastro do cliente atualizado.")
    else:
        messages.error(request, "Revise os dados do cadastro.")
    return redirect("clientes")


@login_required
@require_POST
def ajustar_credito(request):
    if not can_manage_credit(request.user):
        messages.error(request, "Somente Dono ou Coordenador ajusta credito.")
        return redirect("clientes")

    form = CreditoForm(request.POST)
    if form.is_valid():
        cliente = get_object_or_404(Cliente, pk=form.cleaned_data["cliente_id"])
        valor = form.cleaned_data["valor"]
        tipo = form.cleaned_data["tipo"]
        if tipo == MovimentoCredito.DEBITO and not can_debit_credit(request.user):
            messages.error(request, "Somente o perfil Dono pode retirar credito por correcao.")
            return redirect("clientes")
        valor_final = valor if tipo == MovimentoCredito.CREDITO else -valor
        cliente.credito += valor_final
        cliente.save(update_fields=["credito", "atualizado_em"])
        MovimentoCredito.objects.create(
            cliente=cliente,
            usuario=request.user,
            valor=valor_final,
            tipo=tipo,
            observacao=form.cleaned_data["observacao"],
        )
        messages.success(request, "Credito atualizado.")
    else:
        messages.error(request, "Revise o valor informado.")
    return redirect("clientes")


@login_required
def itens(request):
    if request.method == "POST":
        if not can_manage_items(request.user):
            messages.error(request, "Somente Dono ou Coordenador cadastra itens.")
            return redirect("itens")
        form = ItemForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Item cadastrado com sucesso.")
            return redirect("itens")
    else:
        form = ItemForm(initial={"ativo": True, "estoque_minimo": 5})

    itens_query = Item.objects.all()
    busca = request.GET.get("busca", "").strip()
    categoria = request.GET.get("categoria", "").strip()
    if busca:
        itens_query = itens_query.filter(nome__icontains=busca)
    if categoria:
        itens_query = itens_query.filter(categoria=categoria)

    categorias = (
        Item.objects.exclude(categoria="")
        .values_list("categoria", flat=True)
        .distinct()
        .order_by("categoria")
    )

    context = {
        **role_context(request),
        "form": form,
        "itens": itens_query,
        "busca": busca,
        "categoria_selecionada": categoria,
        "categorias": categorias,
    }
    return render(request, "core/itens.html", context)


@login_required
@require_POST
def atualizar_preco_item(request, item_id):
    if not can_manage_items(request.user):
        messages.error(request, "Somente Dono ou Coordenador altera itens.")
        return redirect("itens")

    item = get_object_or_404(Item, pk=item_id)
    form = ItemPrecoForm(request.POST)
    if form.is_valid():
        item.preco = form.cleaned_data["preco"]
        item.save(update_fields=["preco", "atualizado_em"])
        messages.success(request, f"Preço de {item.nome} atualizado.")
    else:
        messages.error(request, "Informe um preço válido.")
    return redirect("itens")


@login_required
@require_POST
def atualizar_estoque_item(request, item_id):
    if not can_manage_items(request.user):
        messages.error(request, "Somente Dono ou Coordenador altera estoque.")
        return redirect("itens")

    item = get_object_or_404(Item, pk=item_id)
    form = ItemEstoqueForm(request.POST)
    if form.is_valid():
        item.estoque = form.cleaned_data["estoque"]
        item.save(update_fields=["estoque", "atualizado_em"])
        messages.success(request, f"Estoque de {item.nome} atualizado.")
    else:
        messages.error(request, "Informe uma quantidade válida.")
    return redirect("itens")


@login_required
@require_POST
def excluir_item(request, item_id):
    if not can_manage_items(request.user):
        messages.error(request, "Somente Dono ou Coordenador exclui itens.")
        return redirect("itens")

    item = get_object_or_404(Item, pk=item_id)
    if item.vendaitem_set.exists():
        item.ativo = False
        item.save(update_fields=["ativo", "atualizado_em"])
        messages.success(request, f"{item.nome} foi desativado para preservar o histórico de vendas.")
    else:
        nome = item.nome
        item.delete()
        messages.success(request, f"{nome} foi excluído.")
    return redirect("itens")


@login_required
def vendas(request):
    if request.method == "POST":
        return criar_venda(request)

    categorias = [value for value, _label in Item.CATEGORIAS]
    context = {
        **role_context(request),
        "itens": Item.objects.filter(ativo=True).order_by("categoria", "nome"),
        "categorias": categorias,
    }
    return render(request, "core/vendas.html", context)


def criar_venda(request):
    itens_selecionados = list(dict.fromkeys(request.POST.getlist("itens")))
    forma_pagamento = request.POST.get("forma_pagamento", "")
    formas_validas = {value for value, _label in Venda.PAGAMENTOS}
    if forma_pagamento not in formas_validas:
        messages.error(request, "Selecione uma forma de pagamento válida.")
        return redirect("vendas")
    descricoes_avulsas = request.POST.getlist("avulso_descricao")
    precos_avulsos = request.POST.getlist("avulso_preco")
    quantidades_avulsas = request.POST.getlist("avulso_quantidade")
    if not (len(descricoes_avulsas) == len(precos_avulsos) == len(quantidades_avulsas)):
        messages.error(request, "Revise os itens avulsos e tente novamente.")
        return redirect("vendas")
    avulsos = []
    for descricao, preco_texto, quantidade_texto in zip(descricoes_avulsas, precos_avulsos, quantidades_avulsas):
        try:
            preco = Decimal(preco_texto.replace(",", "."))
            quantidade = int(quantidade_texto)
        except (InvalidOperation, TypeError, ValueError):
            messages.error(request, "Preço ou quantidade inválida no item avulso.")
            return redirect("vendas")
        descricao = descricao.strip()
        if (
            not descricao
            or len(descricao) > 140
            or not preco.is_finite()
            or preco <= 0
            or preco > Decimal("99999999.99")
            or preco.as_tuple().exponent < -2
            or quantidade < 1
        ):
            messages.error(request, "Informe descrição, preço maior que zero e quantidade válida para o item avulso.")
            return redirect("vendas")
        avulsos.append((descricao, preco, quantidade))

    if not itens_selecionados and not avulsos:
        messages.error(request, "Selecione pelo menos um item para vender.")
        return redirect("vendas")

    with transaction.atomic():
        itens = list(Item.objects.select_for_update().filter(pk__in=itens_selecionados, ativo=True).order_by("pk"))
        if len(itens) != len(itens_selecionados):
            messages.error(request, "Um produto ficou indisponível. Revise a venda e tente novamente.")
            return redirect("vendas")
        linhas = []
        total = Decimal("0.00")
        for item in itens:
            try:
                quantidade = int(request.POST.get(f"quantidade_{item.pk}", "1") or 1)
            except (TypeError, ValueError):
                quantidade = 0
            if quantidade < 1 or quantidade > item.estoque:
                messages.error(request, f"Quantidade inválida para {item.nome}; estoque disponível: {item.estoque}.")
                return redirect("vendas")
            subtotal = item.preco * quantidade
            total += subtotal
            linhas.append((item, quantidade, subtotal))

        total_avulsos = sum((preco * quantidade for _descricao, preco, quantidade in avulsos), Decimal("0.00"))
        total += total_avulsos
        if total > Decimal("99999999.99"):
            messages.error(request, "O total excede o limite permitido para uma venda.")
            return redirect("vendas")

        venda = Venda.objects.create(
            atendente=request.user,
            total=total,
            forma_pagamento=forma_pagamento,
        )

        for item, quantidade, subtotal in linhas:
            VendaItem.objects.create(
                venda=venda,
                item=item,
                quantidade=quantidade,
                valor_unitario=item.preco,
                subtotal=subtotal,
            )
            item.estoque -= quantidade
            item.save(update_fields=["estoque", "atualizado_em"])

        for descricao, preco, quantidade in avulsos:
            VendaItem.objects.create(
                venda=venda,
                item=None,
                avulso=True,
                descricao_avulso=descricao,
                quantidade=quantidade,
                valor_unitario=preco,
                subtotal=preco * quantidade,
            )

    messages.success(request, "Venda registrada com sucesso.")
    return redirect("vendas")


def decode_camera_photo(data_url: str) -> ContentFile | None:
    prefix = "data:image/png;base64,"
    if not data_url.startswith(prefix):
        return None
    return ContentFile(base64.b64decode(data_url[len(prefix):]))


@login_required
def relatorios(request):
    hoje = timezone.localdate()
    data_inicio = parse_date(request.GET.get("data_inicio", "")) or hoje.replace(day=1)
    data_fim = parse_date(request.GET.get("data_fim", "")) or hoje
    if data_inicio > data_fim:
        data_inicio, data_fim = data_fim, data_inicio
    vendas_periodo = Venda.objects.filter(
        criado_em__date__gte=data_inicio,
        criado_em__date__lte=data_fim,
        status="concluida",
    )
    formas_pagamento = list(Venda.PAGAMENTOS) + [("cartao_historico", "Cartão (registro antigo)")]
    context = {
        **role_context(request),
        "vendas": vendas_periodo.select_related("atendente")[:100],
        "vendas_canceladas": Venda.objects.select_related("atendente").filter(
            criado_em__date__gte=data_inicio,
            criado_em__date__lte=data_fim,
            status="cancelada",
        )[:100],
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "total_periodo": vendas_periodo.aggregate(total=Sum("total"))["total"] or 0,
        "quantidade_vendas": vendas_periodo.count(),
        "pagamentos_periodo": [
            {"nome": label, "total": vendas_periodo.filter(forma_pagamento=value).aggregate(total=Sum("total"))["total"] or 0}
            for value, label in formas_pagamento
        ],
        "itens_mais_vendidos": (
            VendaItem.objects.filter(venda__in=vendas_periodo).annotate(
                nome=Case(
                    When(avulso=True, then=F("descricao_avulso")),
                    default=F("item__nome"),
                    output_field=CharField(),
                )
            ).values("nome")
            .annotate(quantidade=Sum("quantidade"), receita=Sum("subtotal"))
            .order_by("-quantidade")[:10]
        ),
        "lista_compras": Item.objects.filter(ativo=True, estoque__lte=F("estoque_minimo")).order_by("estoque"),
    }
    return render(request, "core/relatorios.html", context)


@login_required
@require_POST
def cancelar_venda(request, venda_id):
    with transaction.atomic():
        venda = get_object_or_404(Venda.objects.select_for_update(), pk=venda_id)
        if venda.status == "cancelada":
            messages.error(request, "Esta venda já foi cancelada.")
            return redirect("relatorios")
        linhas = list(venda.itens.select_related("item").order_by("item_id"))
        itens = {
            item.pk: item
            for item in Item.objects.select_for_update().filter(
                pk__in=[linha.item_id for linha in linhas if linha.item_id]
            ).order_by("pk")
        }
        for linha in linhas:
            if linha.item_id is None:
                continue
            item = itens[linha.item_id]
            item.estoque += linha.quantidade
            item.save(update_fields=["estoque", "atualizado_em"])
        venda.status = "cancelada"
        venda.save(update_fields=["status"])
    messages.success(request, f"Venda #{venda.pk} cancelada; estoque devolvido.")
    return redirect("relatorios")


def manifest(request):
    return JsonResponse(
        {
            "name": "Giro - Vendas e Estoque",
            "short_name": "Giro",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#f5f7f4",
            "theme_color": "#14532d",
            "icons": [
                {"src": staticfiles_storage.url("core/icon.svg"), "sizes": "any", "type": "image/svg+xml"},
            ],
        }
    )


def service_worker(request):
    content = """
self.addEventListener('install', event => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  event.respondWith(fetch(event.request));
});
"""
    return HttpResponse(content, content_type="application/javascript")


def offline(request):
    return render(request, "core/offline.html")
