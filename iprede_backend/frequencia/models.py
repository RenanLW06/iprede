from django.conf import settings
from django.db import models
from django.db.models import Q
from simple_history.models import HistoricalRecords

from cadastros.models import Crianca
from core.models import Carimbos
from programacao.models import Matricula, Oferta, Realocacao


class Sessao(Carimbos):
    """Uma oferta acontecendo numa data. Guarda o que é coletivo (feriado, turma liberada)."""

    class Status(models.TextChoices):
        REALIZADA = "REALIZADA", "Realizada"
        FERIADO = "FERIADO", "Feriado"
        TURMA_LIBERADA = "TURMA_LIBERADA", "Turma liberada"

    oferta = models.ForeignKey(Oferta, on_delete=models.PROTECT, related_name="sessoes")
    data = models.DateField()
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.REALIZADA)

    history = HistoricalRecords()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["oferta", "data"], name="sessao_unica_por_oferta_data")]
        ordering = ["-data"]
        verbose_name_plural = "sessões"


class Frequencia(Carimbos):
    """Presença individual numa sessão. Vem de uma matrícula OU de uma realocação."""

    class Situacao(models.TextChoices):
        PRESENTE = "PRESENTE", "Presente"
        FALTA = "FALTA", "Falta"
        FALTA_JUSTIFICADA = "FALTA_JUSTIFICADA", "Falta justificada"
        ATESTADO = "ATESTADO", "Atestado"
        VIAJANDO = "VIAJANDO", "Criança viajando"
        LIBERADO_ENFERMAGEM = "LIBERADO_ENFERMAGEM", "Liberado pela enfermagem"

    sessao = models.ForeignKey(Sessao, on_delete=models.PROTECT, related_name="frequencias")
    crianca = models.ForeignKey(Crianca, on_delete=models.PROTECT, related_name="frequencias")
    matricula = models.ForeignKey(
        Matricula, null=True, blank=True, on_delete=models.PROTECT, related_name="frequencias"
    )
    realocacao = models.ForeignKey(
        Realocacao, null=True, blank=True, on_delete=models.PROTECT, related_name="frequencias"
    )
    situacao = models.CharField(max_length=20, choices=Situacao.choices)
    atrasada = models.BooleanField(default=False)
    justificativa = models.CharField(max_length=300, blank=True)
    observacao = models.TextField(blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["sessao", "crianca"], name="frequencia_unica_por_sessao_crianca"),
            models.CheckConstraint(
                condition=(
                    Q(matricula__isnull=False, realocacao__isnull=True)
                    | Q(matricula__isnull=True, realocacao__isnull=False)
                ),
                name="frequencia_uma_origem",
            ),
        ]
        verbose_name_plural = "frequências"
