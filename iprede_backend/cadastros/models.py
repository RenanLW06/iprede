import re
from datetime import date

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import connection, models
from simple_history.models import HistoricalRecords

from core.models import Carimbos


def proximo_codigo_v() -> int:
    """Próximo número da sequência do PostgreSQL (criada em core/sql/regras.sql).
    A sequência é atômica: dois cadastros simultâneos nunca recebem o mesmo número."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('codigo_v_seq')")
        return cursor.fetchone()[0]


class Distrito(Carimbos):
    """Distrito educacional (D1 a D6). Pertence à criança, não à turma."""

    nome = models.CharField(max_length=20, unique=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Crianca(Carimbos):
    class Situacao(models.TextChoices):
        ATIVA = "ATIVA", "Ativa"
        SEM_GRUPO = "SEM_GRUPO", "Sem grupo (aguardando turma)"
        INATIVA = "INATIVA", "Inativa (desligada)"

    # Identificador institucional. Parte numérica do Código V (V4595 -> 4595).
    # Único, permanente (gatilho no banco) e nunca reaproveitado: a criança não é apagada.
    codigo_v_num = models.PositiveIntegerField(
        "Código V (número)",
        unique=True,
        editable=False,
        validators=[MinValueValidator(1)],
    )
    rm = models.CharField("RM", max_length=20, unique=True, null=True, blank=True)
    nome = models.CharField(max_length=200, db_index=True)
    data_nascimento = models.DateField(null=True, blank=True)
    nome_mae = models.CharField("Responsável", max_length=200, blank=True)
    # Visível só com a permissão `ver_telefone` (aplicada na API, não só na tela).
    whatsapp = models.CharField(max_length=30, blank=True)
    distrito = models.ForeignKey(Distrito, on_delete=models.PROTECT, related_name="criancas")
    situacao = models.CharField(max_length=10, choices=Situacao.choices, default=Situacao.SEM_GRUPO)
    data_inativacao = models.DateField(null=True, blank=True)
    observacoes = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["nome"]
        permissions = [("ver_telefone", "Pode ver o telefone/WhatsApp")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(situacao="INATIVA", data_inativacao__isnull=False)
                | ~models.Q(situacao="INATIVA"),
                name="crianca_inativa_tem_data",
            ),
        ]

    def __str__(self):
        return f"{self.codigo_v} - {self.nome}"

    @property
    def codigo_v(self) -> str:
        return f"V{self.codigo_v_num}" if self.codigo_v_num is not None else ""

    @property
    def idade(self):
        if not self.data_nascimento:
            return None
        hoje = date.today()
        n = self.data_nascimento
        return hoje.year - n.year - ((hoje.month, hoje.day) < (n.month, n.day))

    def save(self, *args, **kwargs):
        self.nome = re.sub(r"\s+", " ", self.nome or "").strip()
        self.rm = (self.rm or "").strip() or None
        if self.situacao == self.Situacao.INATIVA and not self.data_inativacao:
            self.data_inativacao = date.today()
        distrito_anterior = None
        if self.pk:
            distrito_anterior = (
                type(self).objects.filter(pk=self.pk).values_list("distrito_id", flat=True).first()
            )
        elif self.codigo_v_num is None:
            self.codigo_v_num = proximo_codigo_v()
        super().save(*args, **kwargs)
        if distrito_anterior is not None and distrito_anterior != self.distrito_id:
            HistoricoDistrito.objects.create(
                crianca=self,
                distrito_anterior_id=distrito_anterior,
                distrito_novo_id=self.distrito_id,
                alterado_por=getattr(self, "_usuario", None),
            )


class HistoricoDistrito(models.Model):
    crianca = models.ForeignKey(Crianca, on_delete=models.PROTECT, related_name="historico_distritos")
    distrito_anterior = models.ForeignKey(Distrito, on_delete=models.PROTECT, related_name="+")
    distrito_novo = models.ForeignKey(Distrito, on_delete=models.PROTECT, related_name="+")
    alterado_em = models.DateTimeField(auto_now_add=True)
    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-alterado_em"]
