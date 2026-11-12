from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from simple_history.models import HistoricalRecords

from cadastros.models import Crianca
from contas.models import Profissional
from core.choices import Bloco, DiaSemana, letra_da_turma
from core.models import Carimbos


class Periodo(Carimbos):
    """Ano letivo. O projeto é anual (não existe 2026.2)."""

    ano = models.PositiveSmallIntegerField(unique=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-ano"]

    def __str__(self):
        return str(self.ano)


class Atividade(Carimbos):
    """Categoria: Artesania, Dança, Música, Judô..."""

    nome = models.CharField(max_length=100, unique=True)
    descricao = models.TextField(blank=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        verbose_name_plural = "atividades"

    def __str__(self):
        return self.nome


class Sala(Carimbos):
    """Corresponde a uma guia das planilhas (ex.: 'Artesania Iara'): a atividade
    mais o espaço/instrutor. Funciona nos 4 tempos do dia."""

    nome = models.CharField(max_length=120, unique=True)
    atividade = models.ForeignKey(Atividade, on_delete=models.PROTECT, related_name="salas")
    ativa = models.BooleanField(default=True)
    observacoes = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class SalaProfissional(models.Model):
    """Instrutor(es) de uma sala, com vigência, para a troca de instrutores
    (contratações em andamento) não apagar o histórico."""

    sala = models.ForeignKey(Sala, on_delete=models.PROTECT, related_name="instrutores")
    profissional = models.ForeignKey(Profissional, on_delete=models.PROTECT, related_name="salas")
    inicio = models.DateField(default=timezone.localdate)
    fim = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["sala", "profissional", "inicio"], name="sala_prof_unico"),
            models.CheckConstraint(
                condition=Q(fim__isnull=True) | Q(fim__gte=F("inicio")), name="sala_prof_vigencia_valida"
            ),
        ]


class Tempo(models.Model):
    """Os 4 tempos de 1h: T1 e T2 formam o bloco D1; T3 e T4, o bloco D2."""

    ordem = models.PositiveSmallIntegerField(unique=True)
    bloco = models.CharField(max_length=2, choices=Bloco.choices)
    hora_inicio = models.TimeField()
    hora_fim = models.TimeField()

    class Meta:
        ordering = ["ordem"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(ordem__in=[1, 2], bloco="D1") | Q(ordem__in=[3, 4], bloco="D2")),
                name="tempo_ordem_combina_com_bloco",
            ),
            models.CheckConstraint(condition=Q(hora_fim__gt=F("hora_inicio")), name="tempo_fim_apos_inicio"),
        ]

    def __str__(self):
        return f"T{self.ordem} ({self.hora_inicio:%H:%M}-{self.hora_fim:%H:%M})"


class Inscricao(Carimbos):
    """O dia (turma A a E) e o bloco (D1 ou D2) da criança no ano. Todas as
    matrículas dela precisam estar dentro deste dia e bloco."""

    crianca = models.ForeignKey(Crianca, on_delete=models.PROTECT, related_name="inscricoes")
    periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name="inscricoes")
    dia_semana = models.PositiveSmallIntegerField(choices=DiaSemana.choices)
    bloco = models.CharField(max_length=2, choices=Bloco.choices)

    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["crianca", "periodo"], name="inscricao_unica_por_periodo"),
            models.CheckConstraint(condition=Q(dia_semana__gte=1, dia_semana__lte=5), name="inscricao_dia_valido"),
        ]
        verbose_name_plural = "inscrições"

    @property
    def turma(self) -> str:
        return letra_da_turma(self.dia_semana)


class Oferta(Carimbos):
    """Sala + dia + tempo, com capacidade padrão 6. É a unidade de vagas."""

    periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name="ofertas")
    sala = models.ForeignKey(Sala, on_delete=models.PROTECT, related_name="ofertas")
    dia_semana = models.PositiveSmallIntegerField(choices=DiaSemana.choices)
    tempo = models.ForeignKey(Tempo, on_delete=models.PROTECT, related_name="ofertas")
    capacidade_padrao = models.PositiveSmallIntegerField(default=6)
    ativa = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        constraints = [
            # Também impede conflito de sala: a sala só tem uma oferta por dia e tempo.
            models.UniqueConstraint(
                fields=["periodo", "sala", "dia_semana", "tempo"], name="oferta_unica_sala_dia_tempo"
            ),
            models.CheckConstraint(condition=Q(dia_semana__gte=1, dia_semana__lte=5), name="oferta_dia_valido"),
            models.CheckConstraint(condition=Q(capacidade_padrao__gte=1), name="oferta_capacidade_positiva"),
        ]
        ordering = ["periodo", "dia_semana", "tempo", "sala"]
        verbose_name_plural = "ofertas"

    def __str__(self):
        return f"{self.sala} - {self.get_dia_semana_display()} - {self.tempo}"

    def ocupacao_na_data(self, data) -> int:
        """Matrículas ativas + crianças realocadas para esta oferta naquele dia."""
        return self.matriculas.filter(situacao=Matricula.Situacao.ATIVA).count() + self.realocacoes.filter(
            data=data
        ).count()

    def excesso_na_data(self, data) -> int:
        return max(0, self.ocupacao_na_data(data) - self.capacidade_padrao)


class Matricula(Carimbos):
    """Vínculo regular da criança com uma oferta. Capacidade, tempo livre e
    dia/bloco da inscrição são verificados por gatilho no banco (core/sql/regras.sql)."""

    class Situacao(models.TextChoices):
        ATIVA = "ATIVA", "Ativa"
        ENCERRADA = "ENCERRADA", "Encerrada"

    crianca = models.ForeignKey(Crianca, on_delete=models.PROTECT, related_name="matriculas")
    oferta = models.ForeignKey(Oferta, on_delete=models.PROTECT, related_name="matriculas")
    data_inicio = models.DateField(default=timezone.localdate)
    data_fim = models.DateField(null=True, blank=True)
    situacao = models.CharField(max_length=10, choices=Situacao.choices, default=Situacao.ATIVA)
    motivo_encerramento = models.CharField(max_length=200, blank=True)

    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["crianca", "oferta"],
                condition=Q(situacao="ATIVA"),
                name="matricula_ativa_unica_por_oferta",
            ),
            models.CheckConstraint(
                condition=(Q(situacao="ATIVA", data_fim__isnull=True) | Q(situacao="ENCERRADA", data_fim__isnull=False)),
                name="matricula_situacao_combina_com_data_fim",
            ),
            models.CheckConstraint(
                condition=Q(data_fim__isnull=True) | Q(data_fim__gte=F("data_inicio")),
                name="matricula_fim_apos_inicio",
            ),
        ]


class Realocacao(Carimbos):
    """Exceção de UM dia: a criança frequenta outra oferta naquela data.
    Não encerra nem cria matrícula, e pode ultrapassar a capacidade."""

    crianca = models.ForeignKey(Crianca, on_delete=models.PROTECT, related_name="realocacoes")
    oferta_destino = models.ForeignKey(Oferta, on_delete=models.PROTECT, related_name="realocacoes")
    data = models.DateField()
    matricula_origem = models.ForeignKey(
        Matricula, null=True, blank=True, on_delete=models.PROTECT, related_name="realocacoes"
    )
    autorizador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    justificativa = models.TextField()

    history = HistoricalRecords()

    class Meta:
        permissions = [("autorizar_realocacao", "Pode autorizar realocações")]
        constraints = [
            models.UniqueConstraint(fields=["crianca", "oferta_destino", "data"], name="realocacao_unica_por_dia"),
            models.CheckConstraint(condition=~Q(justificativa=""), name="realocacao_exige_justificativa"),
        ]
        verbose_name_plural = "realocações"
