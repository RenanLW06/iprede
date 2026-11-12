# Iprede: estrutura do banco de dados (Django + PostgreSQL)

Primeira versão do esquema. **Ainda não foi executada**: foi escrita sem acesso a Django nem a PostgreSQL,
só com checagem de sintaxe. O primeiro passo é rodar os comandos abaixo e corrigir o que aparecer.

## Como rodar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# crie o banco "iprede" e o usuário no PostgreSQL; ajuste POSTGRES_* se necessário
python manage.py makemigrations contas cadastros programacao frequencia
python manage.py migrate          # também aplica core/sql/regras.sql (sequência e gatilhos)
python manage.py seed_basico      # D1-D6, os 4 tempos, ano letivo 2026, perfis
python manage.py test             # testes das regras do banco
```

## Apps

| App | Conteúdo |
|---|---|
| `core` | Base abstrata, dias/blocos, **regras SQL** (`sql/regras.sql`), comando `seed_basico` |
| `contas` | `Usuario` (vínculo opcional com `Profissional`), `Profissional` |
| `cadastros` | `Distrito`, `Crianca` (Código V, RM, situação), `HistoricoDistrito` |
| `programacao` | `Periodo`, `Atividade`, `Sala`, `SalaProfissional`, `Tempo`, `Inscricao`, `Oferta`, `Matricula`, `Realocacao` |
| `frequencia` | `Sessao`, `Frequencia` |

## Onde cada regra é garantida

| Regra | Garantia |
|---|---|
| Código V único, permanente, sem reuso | Sequência `codigo_v_seq` + `UNIQUE` + gatilho que proíbe alterar e apagar a criança |
| RM opcional e único quando informado | `UNIQUE` em coluna que aceita nulo |
| Capacidade 6 por oferta (matrícula normal) | Gatilho com bloqueio da oferta (sem corrida na última vaga) |
| Criança sem duas matrículas no mesmo tempo | Gatilho com bloqueio da inscrição da criança |
| Matrícula dentro do dia e bloco da inscrição | Gatilho |
| Sala com uma oferta por dia e tempo | `UNIQUE (período, sala, dia, tempo)` |
| Realocação de um dia, pode exceder a capacidade | Modelo `Realocacao` com data; gatilho confere o dia da semana |
| Frequência vem de matrícula **ou** realocação | `CHECK` + gatilho (mesma criança, oferta e data) |
| Histórico e auditoria | `django-simple-history` nos modelos principais |
| Instrutor não vê telefone | Permissão `ver_telefone`, aplicada na API (próxima etapa) |

## Atenção

- **Sequência do Código V** começa em 5000 para não colidir com a lista (hoje vai até V4655).
  Ao final da importação, rode `SELECT setval('codigo_v_seq', <maior número>);`.
  Até lá, use só dados de teste.
- A importação da lista oficial ficou para o final do projeto e **não** está neste pacote.
- Os gatilhos SQL são recriados a cada `migrate` (idempotente). Se mudar nomes de tabelas, ajuste o SQL.
- Permissão por oferta para instrutores (só as suas salas) será aplicada na API, não no banco.
