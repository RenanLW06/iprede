"""Testes das regras que o banco precisa garantir sozinho (capacidade, tempo livre,
dia/bloco, código V, realocação de um dia, frequência). Rodam contra PostgreSQL."""
from datetime import date, time

from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from cadastros.models import Crianca, Distrito
from contas.models import Usuario
from frequencia.models import Frequencia, Sessao
from programacao.models import Atividade, Inscricao, Matricula, Oferta, Periodo, Realocacao, Sala, Tempo

SEGUNDA = date(2026, 2, 2)  # segunda-feira (dia_semana = 1)
TERCA = date(2026, 2, 3)


class BaseDeTestes(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_basico", verbosity=0)
        cls.periodo = Periodo.objects.get(ano=2026)
        cls.distrito = Distrito.objects.get(nome="D1")
        cls.atividade = Atividade.objects.create(nome="Artesania")
        cls.sala_a = Sala.objects.create(nome="Artesania Iara", atividade=cls.atividade)
        cls.sala_b = Sala.objects.create(nome="Artesania Ana", atividade=cls.atividade)
        cls.admin = Usuario.objects.create_user("admin", password="x")
        cls.n = 0

    def nova_crianca(self, dia=1, bloco="D1", inscrever=True):
        type(self).n += 1
        c = Crianca.objects.create(nome=f"Criança {self.n}", distrito=self.distrito)
        if inscrever:
            Inscricao.objects.create(crianca=c, periodo=self.periodo, dia_semana=dia, bloco=bloco)
        return c

    def oferta(self, sala, dia=1, ordem=1):
        return Oferta.objects.create(
            periodo=self.periodo, sala=sala, dia_semana=dia, tempo=Tempo.objects.get(ordem=ordem)
        )

    def matricular(self, crianca, oferta):
        with transaction.atomic():
            return Matricula.objects.create(crianca=crianca, oferta=oferta)


class CodigoVTests(BaseDeTestes):
    def test_codigos_sequenciais_e_imutaveis(self):
        a, b = self.nova_crianca(inscrever=False), self.nova_crianca(inscrever=False)
        self.assertEqual(b.codigo_v_num, a.codigo_v_num + 1)
        self.assertTrue(a.codigo_v.startswith("V"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Crianca.objects.filter(pk=a.pk).update(codigo_v_num=1)

    def test_crianca_nao_pode_ser_apagada(self):
        c = self.nova_crianca(inscrever=False)
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("DELETE FROM cadastros_crianca WHERE id = %s", [c.pk])


class MatriculaTests(BaseDeTestes):
    def test_capacidade_de_seis(self):
        oferta = self.oferta(self.sala_a)
        for _ in range(6):
            self.matricular(self.nova_crianca(), oferta)
        with self.assertRaises(IntegrityError):
            self.matricular(self.nova_crianca(), oferta)

    def test_mesmo_tempo_em_duas_salas_e_bloqueado(self):
        c = self.nova_crianca()
        self.matricular(c, self.oferta(self.sala_a, ordem=1))
        with self.assertRaises(IntegrityError):
            self.matricular(c, self.oferta(self.sala_b, ordem=1))

    def test_tempos_diferentes_no_mesmo_bloco_sao_permitidos(self):
        c = self.nova_crianca()
        self.matricular(c, self.oferta(self.sala_a, ordem=1))
        self.matricular(c, self.oferta(self.sala_b, ordem=2))

    def test_fora_do_bloco_ou_sem_inscricao(self):
        c = self.nova_crianca(bloco="D1")
        with self.assertRaises(IntegrityError):
            self.matricular(c, self.oferta(self.sala_a, ordem=3))  # tempo 3 é do D2
        sem_inscricao = self.nova_crianca(inscrever=False)
        with self.assertRaises(IntegrityError):
            self.matricular(sem_inscricao, self.oferta(self.sala_a, ordem=1))


class RealocacaoEFrequenciaTests(BaseDeTestes):
    def test_realocacao_pode_ultrapassar_capacidade(self):
        oferta = self.oferta(self.sala_a)
        for _ in range(6):
            self.matricular(self.nova_crianca(), oferta)
        visitante = self.nova_crianca(dia=2, bloco="D2")
        Realocacao.objects.create(
            crianca=visitante, oferta_destino=oferta, data=SEGUNDA, autorizador=self.admin, justificativa="Reposição"
        )
        self.assertEqual(oferta.ocupacao_na_data(SEGUNDA), 7)
        self.assertEqual(oferta.excesso_na_data(SEGUNDA), 1)

    def test_realocacao_exige_data_no_dia_da_oferta(self):
        oferta = self.oferta(self.sala_a)  # segunda
        with self.assertRaises(IntegrityError), transaction.atomic():
            Realocacao.objects.create(
                crianca=self.nova_crianca(), oferta_destino=oferta, data=TERCA,
                autorizador=self.admin, justificativa="x",
            )

    def test_frequencia_exige_exatamente_uma_origem(self):
        oferta = self.oferta(self.sala_a)
        c = self.nova_crianca()
        m = self.matricular(c, oferta)
        sessao = Sessao.objects.create(oferta=oferta, data=SEGUNDA)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Frequencia.objects.create(sessao=sessao, crianca=c, situacao="PRESENTE", registrado_por=self.admin)
        Frequencia.objects.create(
            sessao=sessao, crianca=c, matricula=m, situacao="PRESENTE", registrado_por=self.admin
        )
