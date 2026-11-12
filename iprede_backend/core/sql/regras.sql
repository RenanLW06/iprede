-- Regras de integridade aplicadas no PostgreSQL (idempotente: pode rodar a cada migrate).
-- Todas as violações usam o código 23514 (check_violation), que o Django converte em IntegrityError.
-- Nomes de tabelas seguem o padrão do Django: <app>_<modelo>.

-- 1. Código V -------------------------------------------------------------------------------
-- Sequência atômica. Antes de usar o sistema com crianças reais, e ao final da importação
-- da lista oficial, ajuste:  SELECT setval('codigo_v_seq', <maior número usado>);
CREATE SEQUENCE IF NOT EXISTS codigo_v_seq START 5000;

CREATE OR REPLACE FUNCTION iprede_crianca_protegida() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Crianças não são apagadas: marque como Inativa' USING ERRCODE = '23514';
  END IF;
  IF NEW.codigo_v_num IS DISTINCT FROM OLD.codigo_v_num THEN
    RAISE EXCEPTION 'O Código V é permanente e não pode ser alterado' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_crianca_protegida ON cadastros_crianca;
CREATE TRIGGER trg_crianca_protegida
  BEFORE UPDATE OR DELETE ON cadastros_crianca
  FOR EACH ROW EXECUTE FUNCTION iprede_crianca_protegida();

-- 2. Matrícula: inscrição, dia/bloco, tempo livre e capacidade -------------------------------
-- O bloqueio da oferta (FOR UPDATE) serializa matrículas simultâneas na mesma oferta, e o da
-- inscrição serializa as da mesma criança. Assim duas pessoas não ocupam a última vaga juntas.
CREATE OR REPLACE FUNCTION iprede_validar_matricula() RETURNS trigger AS $$
DECLARE
  oft RECORD;
  insc RECORD;
  ocupadas integer;
BEGIN
  IF NEW.situacao <> 'ATIVA' THEN
    RETURN NEW;
  END IF;

  SELECT ofe.periodo_id, ofe.dia_semana, ofe.tempo_id, ofe.capacidade_padrao, t.bloco
    INTO oft
    FROM programacao_oferta ofe
    JOIN programacao_tempo t ON t.id = ofe.tempo_id
   WHERE ofe.id = NEW.oferta_id
     FOR UPDATE OF ofe;

  SELECT i.dia_semana, i.bloco
    INTO insc
    FROM programacao_inscricao i
   WHERE i.crianca_id = NEW.crianca_id AND i.periodo_id = oft.periodo_id
     FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'A criança não tem inscrição neste período' USING ERRCODE = '23514';
  END IF;
  IF insc.dia_semana <> oft.dia_semana OR insc.bloco <> oft.bloco THEN
    RAISE EXCEPTION 'A oferta está fora do dia/bloco da inscrição da criança' USING ERRCODE = '23514';
  END IF;

  IF EXISTS (
    SELECT 1
      FROM programacao_matricula m
      JOIN programacao_oferta o2 ON o2.id = m.oferta_id
     WHERE m.crianca_id = NEW.crianca_id
       AND m.situacao = 'ATIVA'
       AND m.id IS DISTINCT FROM NEW.id
       AND o2.periodo_id = oft.periodo_id
       AND o2.dia_semana = oft.dia_semana
       AND o2.tempo_id = oft.tempo_id
  ) THEN
    RAISE EXCEPTION 'A criança já tem matrícula ativa neste tempo' USING ERRCODE = '23514';
  END IF;

  SELECT count(*) INTO ocupadas
    FROM programacao_matricula
   WHERE oferta_id = NEW.oferta_id AND situacao = 'ATIVA' AND id IS DISTINCT FROM NEW.id;
  IF ocupadas >= oft.capacidade_padrao THEN
    RAISE EXCEPTION 'Oferta lotada (capacidade %)', oft.capacidade_padrao USING ERRCODE = '23514';
  END IF;

  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_validar_matricula ON programacao_matricula;
CREATE TRIGGER trg_validar_matricula
  BEFORE INSERT OR UPDATE OF situacao, oferta_id, crianca_id ON programacao_matricula
  FOR EACH ROW EXECUTE FUNCTION iprede_validar_matricula();

-- 3. Realocação de um dia: a data precisa cair no dia da oferta; um tempo por data ------------
-- Não confere capacidade: a realocação pode ultrapassar o limite (o excesso é calculado).
CREATE OR REPLACE FUNCTION iprede_validar_realocacao() RETURNS trigger AS $$
DECLARE
  oft RECORD;
BEGIN
  SELECT ofe.dia_semana, ofe.tempo_id INTO oft
    FROM programacao_oferta ofe WHERE ofe.id = NEW.oferta_destino_id;

  IF EXTRACT(ISODOW FROM NEW.data)::int <> oft.dia_semana THEN
    RAISE EXCEPTION 'A data não cai no dia da semana da oferta de destino' USING ERRCODE = '23514';
  END IF;

  IF EXISTS (
    SELECT 1
      FROM programacao_realocacao r
      JOIN programacao_oferta o2 ON o2.id = r.oferta_destino_id
     WHERE r.crianca_id = NEW.crianca_id
       AND r.data = NEW.data
       AND o2.tempo_id = oft.tempo_id
       AND r.id IS DISTINCT FROM NEW.id
  ) THEN
    RAISE EXCEPTION 'A criança já está realocada neste tempo nesta data' USING ERRCODE = '23514';
  END IF;

  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_validar_realocacao ON programacao_realocacao;
CREATE TRIGGER trg_validar_realocacao
  BEFORE INSERT OR UPDATE ON programacao_realocacao
  FOR EACH ROW EXECUTE FUNCTION iprede_validar_realocacao();

-- 4. Sessão: a data precisa cair no dia da semana da oferta ---------------------------------
CREATE OR REPLACE FUNCTION iprede_validar_sessao() RETURNS trigger AS $$
DECLARE
  dia integer;
BEGIN
  SELECT dia_semana INTO dia FROM programacao_oferta WHERE id = NEW.oferta_id;
  IF EXTRACT(ISODOW FROM NEW.data)::int <> dia THEN
    RAISE EXCEPTION 'A data não cai no dia da semana da oferta' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_validar_sessao ON frequencia_sessao;
CREATE TRIGGER trg_validar_sessao
  BEFORE INSERT OR UPDATE ON frequencia_sessao
  FOR EACH ROW EXECUTE FUNCTION iprede_validar_sessao();

-- 5. Frequência: a origem (matrícula ou realocação) tem que ser da mesma criança e sessão ------
CREATE OR REPLACE FUNCTION iprede_validar_frequencia() RETURNS trigger AS $$
DECLARE
  s RECORD;
  m RECORD;
  r RECORD;
BEGIN
  SELECT oferta_id, data INTO s FROM frequencia_sessao WHERE id = NEW.sessao_id;

  IF NEW.matricula_id IS NOT NULL THEN
    SELECT crianca_id, oferta_id INTO m FROM programacao_matricula WHERE id = NEW.matricula_id;
    IF m.crianca_id <> NEW.crianca_id OR m.oferta_id <> s.oferta_id THEN
      RAISE EXCEPTION 'A matrícula não corresponde à criança e à oferta da sessão' USING ERRCODE = '23514';
    END IF;
  END IF;

  IF NEW.realocacao_id IS NOT NULL THEN
    SELECT crianca_id, oferta_destino_id, data INTO r FROM programacao_realocacao WHERE id = NEW.realocacao_id;
    IF r.crianca_id <> NEW.crianca_id OR r.oferta_destino_id <> s.oferta_id OR r.data <> s.data THEN
      RAISE EXCEPTION 'A realocação não corresponde à criança, oferta e data da sessão' USING ERRCODE = '23514';
    END IF;
  END IF;

  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_validar_frequencia ON frequencia_frequencia;
CREATE TRIGGER trg_validar_frequencia
  BEFORE INSERT OR UPDATE ON frequencia_frequencia
  FOR EACH ROW EXECUTE FUNCTION iprede_validar_frequencia();
