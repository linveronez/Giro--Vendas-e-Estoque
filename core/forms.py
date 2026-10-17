from django import forms

from .models import Cliente, Item


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
    class Meta:
        model = Item
        fields = ["nome", "categoria", "emoji", "preco", "estoque", "estoque_minimo", "ativo"]
        labels = {"emoji": "Emoji (opcional)", "estoque_minimo": "Estoque mínimo"}
        widgets = {"emoji": forms.TextInput(attrs={"maxlength": 16, "placeholder": "ex.: ☕"})}


class ItemPrecoForm(forms.Form):
    preco = forms.DecimalField(label="Novo valor", min_value=0.01, decimal_places=2, max_digits=10)


class ItemEstoqueForm(forms.Form):
    estoque = forms.IntegerField(label="Novo estoque", min_value=0)


class CreditoForm(forms.Form):
    cliente_id = forms.IntegerField(widget=forms.HiddenInput)
    valor = forms.DecimalField(label="Valor", min_value=0.01, decimal_places=2, max_digits=10)
    tipo = forms.ChoiceField(label="Tipo", choices=[("credito", "Adicionar"), ("debito", "Retirar")])
    observacao = forms.CharField(label="Observacao", required=False, max_length=180)
