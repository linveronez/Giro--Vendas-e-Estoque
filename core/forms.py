from django import forms

from .models import Categoria, Cliente, Item


class ClienteForm(forms.ModelForm):
    credito_inicial = forms.DecimalField(
        label="Credito inicial",
        required=False,
        min_value=0,
        decimal_places=2,
        max_digits=10,
        initial=0,
    )

    class Meta:
        model = Cliente
        fields = ["nome", "documento", "telefone", "credito_inicial", "comprovante_pix", "observacoes"]
        labels = {
            "documento": "Documento ou prontuario (opcional)",
            "telefone": "Telefone (opcional)",
        }
        widgets = {
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }


class ClienteUpdateForm(forms.ModelForm):
    remover_foto = forms.BooleanField(label="Remover foto atual", required=False)
    remover_comprovante_pix = forms.BooleanField(label="Remover comprovante Pix atual", required=False)

    class Meta:
        model = Cliente
        fields = ["nome", "documento", "telefone", "comprovante_pix", "observacoes"]
        labels = {
            "documento": "Documento ou prontuario (opcional)",
            "telefone": "Telefone (opcional)",
            "comprovante_pix": "Novo comprovante Pix",
        }
        widgets = {
            "observacoes": forms.Textarea(attrs={"rows": 2}),
        }


class ItemForm(forms.ModelForm):
    categoria = forms.ChoiceField(label="Categoria")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        names = set(Categoria.objects.values_list("nome", flat=True))
        names.update(Item.objects.exclude(categoria="").values_list("categoria", flat=True).distinct())
        names.update({"Outros"})
        self.fields["categoria"].choices = [(name, name) for name in sorted(names, key=str.casefold)]

    class Meta:
        model = Item
        fields = ["nome", "categoria", "emoji", "preco", "custo", "estoque", "estoque_minimo", "ativo"]
        labels = {"emoji": "Emoji (opcional)", "custo": "Custo unitário (opcional)", "estoque_minimo": "Estoque mínimo"}
        widgets = {"emoji": forms.TextInput(attrs={"maxlength": 16, "placeholder": "ex.: ☕"})}


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nome", "emoji"]
        labels = {"nome": "Nome da categoria", "emoji": "Emoji (opcional)"}
        widgets = {
            "nome": forms.TextInput(attrs={"maxlength": 40, "placeholder": "Ex.: Chocolates"}),
            "emoji": forms.TextInput(attrs={"maxlength": 16, "placeholder": "Ex.: 🍫"}),
        }

    def clean_nome(self):
        nome = self.cleaned_data["nome"].strip()
        if Categoria.objects.filter(nome__iexact=nome).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Essa categoria já existe.")
        return nome


class ItemPrecoForm(forms.Form):
    preco = forms.DecimalField(label="Novo valor", min_value=0.01, decimal_places=2, max_digits=10)


class ItemCustoForm(forms.Form):
    custo = forms.DecimalField(label="Novo custo", min_value=0, required=False, decimal_places=2, max_digits=10)


class ItemEstoqueForm(forms.Form):
    estoque = forms.IntegerField(label="Novo estoque", min_value=0)


class CreditoForm(forms.Form):
    cliente_id = forms.IntegerField(widget=forms.HiddenInput)
    valor = forms.DecimalField(label="Valor", min_value=0.01, decimal_places=2, max_digits=10)
    tipo = forms.ChoiceField(label="Tipo", choices=[("credito", "Adicionar"), ("debito", "Retirar")])
    observacao = forms.CharField(label="Observacao", required=False, max_length=180)
