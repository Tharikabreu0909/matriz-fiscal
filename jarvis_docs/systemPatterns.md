# Padrões do sistema

## Forma do sistema

Monólito local. `app.py` (FastAPI) serve a interface: HTML em `static/index.html`, CSS em `static/app.css`. A API fica no mesmo processo. A leitura de PDF fica em `readers/`. A regra fiscal fica em `services/`. O estado fica em SQLite via `database.py`. Não há fila, autenticação nem serviço externo obrigatório, exceto a consulta Selic no Banco Central quando se calculam juros.

## Fluxo de dados

```
PDF da malha
  -> readers/malha_reader.py
  -> services/pgdas_planner.py (plano 2.4.0)
  -> database.processes (malha_json + pgdas_plan_json)

PDF do PGDAS
  -> readers/pgdas_reader.py
  -> services/cross_engine.validate_pgdas_identity
  -> database.pgdas_documents (só entra como aceito se raiz e competência conferem)

Análise
  -> services/analysis_engine.py
  -> confirmação humana só na exceção (analysis_confirmations)
  -> estudo contábil opcional (accounting_study_conclusions)

Cálculo
  -> services/reflection_coverage.py (bloqueia se faltar mês vencido)
  -> services/tax_engine.calculate_hidden_reflections
  -> services/legal_charges.py
  -> services/client_report.py
```

Nova malha da mesma empresa faz merge em `services/malha_merge.py` e regrava o plano. `ensure_current_pgdas_plan` recalcula o plano ao abrir o processo se a versão do planejador, os períodos, o PA vencido ou a validação mudaram.

## Módulos e responsabilidade

| Módulo | Papel |
| --- | --- |
| `readers/malha_reader.py` | Tabela de avisos: tipo, referência, informado, considerado, divergência, CFDF e razão social |
| `readers/pgdas_reader.py` | Extrato (`PGDAS_EXTRACT`) ou declaração (`PGDAS_DECLARATION`): PA, RPA, RBT12, histórico, DAS quando houver |
| `services/pgdas_planner.py` | Plano único e antecipado de PGDAS |
| `services/analysis_engine.py` | Cruzamento por competência e segregação 01/17 |
| `services/accounting_study.py` | Conclusão humana e dois cenários |
| `services/tax_engine.py` | Alíquota efetiva LC 123, anexos I–V, reflexos de anexo único |
| `services/tax_revenue_lines.py` | Linhas de receita, Fator R e tratamentos monofásico/ST |
| `services/tax_segregation.py` | Segregação por categoria e Fator R 0,28 |
| `services/annex_columns_profile.py` | Perfil de colunas por anexo, apoiado nas linhas de receita |
| `services/reflection_coverage.py` | Lacunas de receita posterior já vencida |
| `services/legal_charges.py` | Multa de mora e Selic |
| `services/security.py` | CNPJ e confronto da malha com a empresa |
| `services/file_storage.py` | PDF em disco, fora do JSON |
| `services/backup_service.py` | ZIP de banco e documentos |
| `services/support_bundle.py` | Diagnóstico sem PDF e sem valores fiscais |

O endpoint `POST /api/calculate-tax` chama apenas `calculate_hidden_reflections` e grava perfil `SINGLE_ANNEX_ESTIMATE_V1` / `STANDARD_FULL_REVENUE`. Os motores de segregação e de linhas de receita são usados por testes e por `build_tax_setup`, não por esse cálculo.

## Persistência

SQLite em modo WAL, `foreign_keys` ligado, timeout 30s. Migrações aditivas em `_run_migrations`, registradas em `schema_migrations`. `PRAGMA user_version = 2`.

Tabelas centrais: `companies`, `processes`, `pgdas_documents`, `analysis_confirmations`, `accounting_study_conclusions`, `tax_profiles`, `tax_calculations`, `legal_charge_calculations`, mais documentos armazenados, eventos e relatórios.

Uma empresa aponta para o processo mais recente (`ORDER BY id DESC LIMIT 1`). Excluir a empresa apaga os registros e a pasta de documentos. Backup antigo continua com os dados até alguém apagá-lo.

Valores monetários internos estão em **centavos inteiros**. Alíquotas usam `Decimal`.

## Decisões técnicas estáveis

- PDF entra por `UploadFile`, limite 20 MB, só extensão `.pdf`.
- Leitura com `pdfplumber.open` em gerenciador de contexto; malha exige a tabela de avisos; PGDAS classifica extrato ou declaração por texto.
- Identidade do PGDAS compara a raiz do CNPJ (8 dígitos), não o CNPJ completo.
- Identidade da malha: CFDF/IE igual tem prioridade; se divergir, bloqueia com HTTP 409 `MALHA_IDENTITY_MISMATCH` até `confirm_identity_mismatch`. Sem IE comparável, aceita razão social com similaridade >= 0,78 depois de normalizar acento e sufixos (LTDA, ME, EPP, SA).
- A receita do próprio PA prevalece sobre o histórico lido em outro extrato, tanto na análise quanto na linha do tempo tributária.
- Confirmação humana com decisão `CONFIRMED` substitui a análise automática daquela competência. O original permanece armazenado.
- Dois cenários de cálculo, gravados em separado: `CONSERVATIVE_FISCAL_EXPOSURE` e `VALIDATED_REGULARIZATION`. O estudo contábil não apaga a malha nem o PGDAS.
- Backup formato 1, teto de 2 GB descompactado e 20.000 membros. Restauração confere o manifesto e a estrutura do banco.
- Pacote de suporte leva versão, ambiente, integridade, contagens e logs. Não leva PDF nem valores extraídos.

## API principal

`GET /`, `GET /api/health`, empresas (`/api/companies`), `POST /api/analyze-malha`, `POST /api/upload-pgdas`, `POST /api/upload-pgdas-auto`, `POST /api/confirm-analysis`, `GET /api/accounting-study`, `GET /api/tax-setup`, `POST /api/calculate-tax`, `POST /api/calculate-legal-charges`, relatório do cliente, download de documento, backup, restauração e pacote de suporte.

## O que não fazer ao evoluir

- Não somar divergência Tipo 01 com Tipo 17.
- Não deixar Tipo 01 sozinho gerar imposto, multa ou reflexo.
- Não preencher mês futuro com zero.
- Não tratar o valor considerado do Tipo 01 como faturamento final do SPED.
- Não promover `tax_revenue_lines` ou `tax_segregation` ao cálculo principal sem uma decisão explícita de produto: hoje a API promete anexo único.
- Não subir a versão no HTML sem alterar `APP_VERSION`, o `.bat` e o planejador no mesmo passo.
