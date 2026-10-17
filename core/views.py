import csv
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles.storage import staticfiles_storage
from django.db import transaction
from django.db.models import Case, CharField, F, Sum, When
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from .forms import CategoriaForm, ItemCustoForm, ItemEstoqueForm, ItemForm, ItemPrecoForm
from .models import Categoria, DEFAULT_CATEGORIAS, Item, Venda, VendaItem


ROLE_OWNER = "Dono"
ROLE_MANAGER = "Gerente"
ROLE_LEGACY_COORDINATOR = "Coordenador"
ROLE_ATTENDANT = "Atendente"


def user_role(user) -> str:
    if user.is_superuser:
        return ROLE_OWNER
    groups = set(user.groups.values_list("name", flat=True))
    if ROLE_OWNER in groups:
        return ROLE_OWNER
    if {ROLE_MANAGER, ROLE_LEGACY_COORDINATOR} & groups:
        return ROLE_MANAGER
    return ROLE_ATTENDANT


def can_manage_items(user) -> bool:
    return user_role(user) in {ROLE_OWNER, ROLE_MANAGER}


def can_view_reports(user) -> bool:
    return user_role(user) in {ROLE_OWNER, ROLE_MANAGER}


def role_context(request) -> dict:
    return {
        "role": user_role(request.user),
        "can_manage_items": can_manage_items(request.user),
        "can_view_reports": can_view_reports(request.user),
    }


def manager_or_owner_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not can_view_reports(request.user):
            messages.error(request, "Somente os perfis Dono e Gerente acessam esta área.")
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
def itens(request):
    if request.method == "POST":
        if not can_manage_items(request.user):
            messages.error(request, "Somente Dono ou Gerente cadastra itens.")
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

    categorias = available_categories()

    context = {
        **role_context(request),
        "form": form,
        "itens": itens_query,
        "busca": busca,
        "categoria_selecionada": categoria,
        "categorias": categorias,
        "categoria_form": CategoriaForm(),
    }
    return render(request, "core/itens.html", context)


def available_categories():
    saved = {category.nome: category for category in Categoria.objects.all()}
    for name, _label in DEFAULT_CATEGORIAS:
        saved.setdefault(name, Categoria(nome=name, emoji=default_category_emoji(name)))
    product_names = Item.objects.exclude(categoria="").values_list("categoria", flat=True).distinct()
    for name in product_names:
        saved.setdefault(name, Categoria(nome=name, emoji="🛍️"))
    return sorted(saved.values(), key=lambda category: category.nome.casefold())


def default_category_emoji(name):
    return {
        "Bebidas quentes": "☕",
        "Bebidas frias": "🥤",
        "Salgados": "🥐",
        "Doces": "🍰",
        "Lanches": "🥪",
        "Outros": "🧺",
    }.get(name, "🏷️")


@login_required
@require_POST
def criar_categoria(request):
    if not can_manage_items(request.user):
        messages.error(request, "Somente Dono ou Gerente cadastra categorias.")
        return redirect("itens")
    form = CategoriaForm(request.POST)
    if form.is_valid():
        categoria = form.save(commit=False)
        categoria.nome = categoria.nome.strip()
        categoria.emoji = categoria.emoji.strip() or "🏷️"
        categoria.save()
        messages.success(request, f"Categoria {categoria.nome} adicionada. Ela já está disponível no cadastro e no caixa.")
    else:
        messages.error(request, "Informe um nome válido para a categoria. " + " ".join(form.errors.get("nome", [])))
    return redirect("itens")


@login_required
@require_POST
def atualizar_preco_item(request, item_id):
    if not can_manage_items(request.user):
        messages.error(request, "Somente Dono ou Gerente altera itens.")
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
def atualizar_custo_item(request, item_id):
    if not can_manage_items(request.user):
        messages.error(request, "Somente Dono ou Gerente altera custos.")
        return redirect("itens")

    item = get_object_or_404(Item, pk=item_id)
    form = ItemCustoForm(request.POST)
    if form.is_valid():
        item.custo = form.cleaned_data["custo"]
        item.save(update_fields=["custo", "atualizado_em"])
        messages.success(request, f"Custo de {item.nome} atualizado.")
    else:
        messages.error(request, "Informe um custo válido ou deixe o campo vazio para não controlar custo.")
    return redirect("itens")


@login_required
@require_POST
def atualizar_estoque_item(request, item_id):
    if not can_manage_items(request.user):
        messages.error(request, "Somente Dono ou Gerente altera estoque.")
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
        messages.error(request, "Somente Dono ou Gerente exclui itens.")
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

    categorias = available_categories()
    emojis = {category.nome: category.emoji for category in categorias}
    produtos = Item.objects.filter(ativo=True).order_by("categoria", "nome")
    for item in produtos:
        item.categoria_emoji = emojis.get(item.categoria) or default_category_emoji(item.categoria)
    context = {
        **role_context(request),
        "itens": produtos,
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

    desconto_recebido = request.POST.get("desconto", "0").replace(",", ".") or "0"
    try:
        desconto_recebido = Decimal(desconto_recebido)
    except (InvalidOperation, TypeError, ValueError):
        messages.error(request, "Descontos estão temporariamente desativados. Registre a venda sem desconto.")
        return redirect("vendas")
    if not desconto_recebido.is_finite() or desconto_recebido != 0:
        messages.error(request, "Descontos estão temporariamente desativados. Registre a venda sem desconto.")
        return redirect("vendas")

    with transaction.atomic():
        itens = list(Item.objects.select_for_update().filter(pk__in=itens_selecionados, ativo=True).order_by("pk"))
        if len(itens) != len(itens_selecionados):
            messages.error(request, "Um produto ficou indisponível. Revise a venda e tente novamente.")
            return redirect("vendas")
        linhas = []
        subtotal = Decimal("0.00")
        for item in itens:
            try:
                quantidade = int(request.POST.get(f"quantidade_{item.pk}", "1") or 1)
            except (TypeError, ValueError):
                quantidade = 0
            if quantidade < 1 or quantidade > item.estoque:
                messages.error(request, f"Quantidade inválida para {item.nome}; estoque disponível: {item.estoque}.")
                return redirect("vendas")
            linha_subtotal = item.preco * quantidade
            subtotal += linha_subtotal
            linhas.append((item, "", quantidade, item.preco, item.custo, linha_subtotal))

        for descricao, preco, quantidade in avulsos:
            linhas.append((None, descricao, quantidade, preco, None, preco * quantidade))
            subtotal += preco * quantidade

        if subtotal > Decimal("99999999.99"):
            messages.error(request, "O subtotal excede o limite permitido para uma venda.")
            return redirect("vendas")
        total = subtotal
        if total > Decimal("99999999.99"):
            messages.error(request, "O total excede o limite permitido para uma venda.")
            return redirect("vendas")

        venda = Venda.objects.create(
            atendente=request.user,
            subtotal=subtotal,
            total=total,
            forma_pagamento=forma_pagamento,
        )

        for item, descricao, quantidade, preco, custo, linha_subtotal in linhas:
            VendaItem.objects.create(
                venda=venda,
                item=item,
                avulso=item is None,
                descricao_avulso=descricao,
                quantidade=quantidade,
                valor_unitario=preco,
                custo_unitario=custo,
                subtotal=linha_subtotal,
            )
            if item is not None:
                item.estoque -= quantidade
                item.save(update_fields=["estoque", "atualizado_em"])

    messages.success(request, "Venda registrada com sucesso.")
    return redirect("vendas")


@login_required
@manager_or_owner_required
def relatorios(request):
    data_inicio, data_fim = _periodo_relatorio(request)
    categorias = available_categories()
    categorias_validas = {categoria.nome for categoria in categorias}
    categoria_selecionada = request.GET.get("categoria", "").strip()
    if categoria_selecionada not in categorias_validas:
        categoria_selecionada = ""

    vendas_periodo = Venda.objects.filter(
        criado_em__date__gte=data_inicio,
        criado_em__date__lte=data_fim,
        status="concluida",
    )
    linhas_mais_vendidas = VendaItem.objects.filter(venda__in=vendas_periodo)
    itens_reposicao = Item.objects.filter(ativo=True, estoque__lte=F("estoque_minimo"))
    if categoria_selecionada:
        linhas_mais_vendidas = linhas_mais_vendidas.filter(item__categoria=categoria_selecionada)
        itens_reposicao = itens_reposicao.filter(categoria=categoria_selecionada)

    formas_pagamento = list(Venda.PAGAMENTOS) + [("cartao_historico", "Cartão (registro antigo)")]
    resultado_custo = VendaItem.objects.filter(venda__in=vendas_periodo, custo_unitario__isnull=False).annotate(
        receita_liquida_linha=F("subtotal") - F("desconto"),
        custo_linha=F("custo_unitario") * F("quantidade"),
    ).aggregate(receita=Sum("receita_liquida_linha"), custo=Sum("custo_linha"))
    receita_com_custo = resultado_custo["receita"] or Decimal("0.00")
    custo_vendido = resultado_custo["custo"] or Decimal("0.00")
    lucro_bruto = receita_com_custo - custo_vendido
    margem_bruta = (lucro_bruto * Decimal("100") / receita_com_custo) if receita_com_custo else None
    linhas_sem_custo = VendaItem.objects.filter(
        venda__in=vendas_periodo,
        custo_unitario__isnull=True,
    ).count()

    context = {
        **role_context(request),
        "vendas": vendas_periodo.select_related("atendente", "desconto_aplicado_por")[:100],
        "vendas_canceladas": Venda.objects.select_related("atendente", "desconto_aplicado_por").filter(
            criado_em__date__gte=data_inicio,
            criado_em__date__lte=data_fim,
            status="cancelada",
        )[:100],
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "categorias": categorias,
        "categoria_selecionada": categoria_selecionada,
        "total_periodo": vendas_periodo.aggregate(total=Sum("total"))["total"] or 0,
        "subtotal_periodo": vendas_periodo.aggregate(total=Sum("subtotal"))["total"] or Decimal("0.00"),
        "desconto_periodo": vendas_periodo.aggregate(total=Sum("desconto"))["total"] or Decimal("0.00"),
        "quantidade_vendas": vendas_periodo.count(),
        "receita_com_custo": receita_com_custo,
        "custo_vendido": custo_vendido,
        "lucro_bruto": lucro_bruto,
        "margem_bruta": margem_bruta,
        "linhas_sem_custo": linhas_sem_custo,
        "pagamentos_periodo": [
            {"nome": label, "total": vendas_periodo.filter(forma_pagamento=value).aggregate(total=Sum("total"))["total"] or 0}
            for value, label in formas_pagamento
        ],
        "itens_mais_vendidos": (
            linhas_mais_vendidas.annotate(
                nome=Case(
                    When(avulso=True, then=F("descricao_avulso")),
                    default=F("item__nome"),
                    output_field=CharField(),
                )
            ).annotate(receita_liquida_linha=F("subtotal") - F("desconto")).values("nome")
            .annotate(quantidade=Sum("quantidade"), receita=Sum("receita_liquida_linha"))
            .order_by("-quantidade")[:10]
        ),
        "lista_compras": itens_reposicao.order_by("estoque", "nome"),
    }
    return render(request, "core/relatorios.html", context)


def _periodo_relatorio(request):
    hoje = timezone.localdate()
    data_inicio = parse_date(request.GET.get("data_inicio", "")) or hoje.replace(day=1)
    data_fim = parse_date(request.GET.get("data_fim", "")) or hoje
    if data_inicio > data_fim:
        data_inicio, data_fim = data_fim, data_inicio
    return data_inicio, data_fim


def _csv_safe(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    if isinstance(value, Decimal):
        return format(value, ".2f").replace(".", ",")
    if value is None:
        return ""
    return value


def _csv_response(filename, headers, rows):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";", lineterminator="\r\n")
    writer.writerow([_csv_safe(value) for value in headers])
    for row in rows:
        writer.writerow([_csv_safe(value) for value in row])
    return response


def _filename_periodo(data_inicio, data_fim):
    return f"{data_inicio.isoformat()}_{data_fim.isoformat()}"


@login_required
@manager_or_owner_required
def exportar_vendas_csv(request):
    data_inicio, data_fim = _periodo_relatorio(request)
    vendas_periodo = Venda.objects.filter(
        criado_em__date__gte=data_inicio,
        criado_em__date__lte=data_fim,
    ).select_related("atendente", "desconto_aplicado_por").prefetch_related("itens__item")

    def linhas_csv():
        for venda in vendas_periodo.order_by("criado_em", "pk"):
            itens_venda = list(venda.itens.all())
            dados_venda = (
                venda.pk,
                timezone.localtime(venda.criado_em).strftime("%d/%m/%Y %H:%M"),
                venda.get_status_display(),
                venda.get_forma_pagamento_display(),
                venda.atendente.get_full_name() or venda.atendente.username,
                venda.subtotal,
                venda.desconto,
                venda.total,
                (venda.desconto_aplicado_por.get_full_name() or venda.desconto_aplicado_por.username)
                if venda.desconto_aplicado_por_id else "",
                venda.desconto_motivo,
            )
            if not itens_venda:
                yield (*dados_venda, "", "", "", "", "", "", "", "", "")
                continue
            for linha in itens_venda:
                nome = linha.descricao_avulso if linha.avulso else linha.item.nome
                categoria = "Avulso" if linha.avulso else linha.item.categoria
                custo_total = linha.custo_unitario * linha.quantidade if linha.custo_unitario is not None else None
                lucro_linha = linha.subtotal - linha.desconto - custo_total if custo_total is not None else None
                yield (
                    *dados_venda,
                    nome,
                    categoria,
                    linha.quantidade,
                    linha.valor_unitario,
                    linha.custo_unitario,
                    linha.subtotal,
                    linha.desconto,
                    linha.subtotal - linha.desconto,
                    lucro_linha,
                )

    return _csv_response(
        f"giro-vendas-{_filename_periodo(data_inicio, data_fim)}.csv",
        [
            "Venda", "Data", "Status", "Pagamento", "Atendente", "Subtotal da venda", "Desconto da venda",
            "Total líquido da venda", "Desconto aplicado por", "Motivo do desconto", "Produto/descrição",
            "Categoria", "Quantidade", "Preço unitário", "Custo unitário histórico", "Subtotal bruto do item",
            "Desconto alocado ao item", "Receita líquida do item", "Lucro bruto do item",
        ],
        linhas_csv(),
    )


@login_required
@manager_or_owner_required
def exportar_estoque_csv(request):
    itens = Item.objects.order_by("categoria", "nome")
    rows = (
        (
            item.pk,
            item.nome,
            item.categoria,
            item.estoque,
            item.estoque_minimo,
            item.custo,
            item.custo * item.estoque if item.custo is not None else None,
            "Baixo" if item.ativo and item.estoque <= item.estoque_minimo else "Ok",
            "Ativo" if item.ativo else "Inativo",
        )
        for item in itens
    )
    return _csv_response(
        f"giro-estoque-{timezone.localdate().isoformat()}.csv",
        ["ID", "Produto", "Categoria", "Estoque atual", "Estoque mínimo", "Custo unitário", "Valor do estoque a custo", "Alerta", "Status"],
        rows,
    )


@login_required
@manager_or_owner_required
def exportar_produtos_csv(request):
    itens = Item.objects.order_by("categoria", "nome")
    rows = (
        (
            item.pk,
            item.nome,
            item.categoria,
            item.preco,
            item.custo,
            item.lucro_unitario,
            item.margem_percentual,
            item.estoque,
            item.estoque_minimo,
            "Ativo" if item.ativo else "Inativo",
        )
        for item in itens
    )
    return _csv_response(
        f"giro-produtos-{timezone.localdate().isoformat()}.csv",
        ["ID", "Produto", "Categoria", "Preço", "Custo", "Lucro bruto unitário", "Margem bruta (%)", "Estoque", "Estoque mínimo", "Status"],
        rows,
    )


@login_required
@require_POST
@manager_or_owner_required
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
