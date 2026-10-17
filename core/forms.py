from django import forms

from .models import Categoria, Item


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
