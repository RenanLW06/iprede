from django.db import models


class DiaSemana(models.IntegerChoices):
    """A turma (A a E) é o dia da semana. Guardamos o número; a letra é exibição."""

    SEGUNDA = 1, "Segunda-feira (A)"
    TERCA = 2, "Terça-feira (B)"
    QUARTA = 3, "Quarta-feira (C)"
    QUINTA = 4, "Quinta-feira (D)"
    SEXTA = 5, "Sexta-feira (E)"


class Bloco(models.TextChoices):
    D1 = "D1", "D1 (13:30 às 15:30)"
    D2 = "D2", "D2 (15:30 às 17:30)"


def letra_da_turma(dia_semana: int) -> str:
    return "ABCDE"[dia_semana - 1]
