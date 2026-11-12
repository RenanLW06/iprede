from pathlib import Path

from django.apps import AppConfig
from django.db import connections
from django.db.models.signals import post_migrate


def aplicar_regras_sql(sender, using="default", **kwargs):
    """Aplica (de forma idempotente) a sequência do Código V e os gatilhos de
    integridade em PostgreSQL. Roda depois de todo `migrate`, quando as tabelas
    já existem. O arquivo é core/sql/regras.sql."""
    conexao = connections[using]
    if conexao.vendor != "postgresql":
        return
    sql = (Path(__file__).parent / "sql" / "regras.sql").read_text(encoding="utf-8")
    with conexao.cursor() as cursor:
        cursor.execute(sql)


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        post_migrate.connect(aplicar_regras_sql, sender=self)
