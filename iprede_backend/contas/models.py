from django.contrib.auth.models import AbstractUser
from django.db import models

from core.models import Carimbos


class Profissional(Carimbos):
    """Instrutor/profissional responsável por salas. Pode existir antes de ter
    usuário (equipe ainda em contratação)."""

    nome = models.CharField(max_length=150)
    contato = models.CharField(max_length=60, blank=True)
    ativo = models.BooleanField(default=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Usuario(AbstractUser):
    """Quem entra no sistema. Perfis = grupos do Django (Administrador, Instrutor).
    O vínculo com Profissional é opcional: sem vínculo, o instrutor não enxerga nada."""

    profissional = models.OneToOneField(
        Profissional,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="usuario",
    )
