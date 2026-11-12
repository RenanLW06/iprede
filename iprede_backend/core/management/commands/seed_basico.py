from datetime import time

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from cadastros.models import Distrito
from programacao.models import Periodo, Tempo

TEMPOS = [
    (1, "D1", time(13, 30), time(14, 30)),
    (2, "D1", time(14, 30), time(15, 30)),
    (3, "D2", time(15, 30), time(16, 30)),
    (4, "D2", time(16, 30), time(17, 30)),
]

PERMISSOES_INSTRUTOR = [
    "view_crianca",
    "view_sala",
    "view_oferta",
    "view_matricula",
    "view_inscricao",
    "view_realocacao",
    "view_sessao",
    "add_sessao",
    "view_frequencia",
    "add_frequencia",
    "change_frequencia",
]


class Command(BaseCommand):
    help = "Cria os dados fixos: distritos D1-D6, os 4 tempos, o ano letivo e os perfis."

    def add_arguments(self, parser):
        parser.add_argument("--ano", type=int, default=2026)

    def handle(self, *args, **opcoes):
        for n in range(1, 7):
            Distrito.objects.get_or_create(nome=f"D{n}")
        for ordem, bloco, inicio, fim in TEMPOS:
            Tempo.objects.update_or_create(
                ordem=ordem, defaults={"bloco": bloco, "hora_inicio": inicio, "hora_fim": fim}
            )
        Periodo.objects.get_or_create(ano=opcoes["ano"])

        admin, _ = Group.objects.get_or_create(name="Administrador")
        admin.permissions.set(
            Permission.objects.filter(content_type__app_label__in=["cadastros", "programacao", "frequencia", "contas"])
        )
        instrutor, _ = Group.objects.get_or_create(name="Instrutor")
        instrutor.permissions.set(Permission.objects.filter(codename__in=PERMISSOES_INSTRUTOR))
        self.stdout.write(self.style.SUCCESS("Dados básicos criados."))
