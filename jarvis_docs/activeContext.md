# Contexto ativo

Fonte da verdade desta sessão: estudo do repositório em 22/10/2026, confrontando `docs/`, notas de versão e o código em execução. Nenhum código de produto foi alterado.

## No que se está trabalhando

Ajuste de usabilidade nas telas Empresas, Malhas, Relatórios, Histórico e Configurações. O menu lateral abre e fecha pelo botão ☰ da barra superior; a escolha fica em `localStorage` (`checkfiscal-sidebar-closed`). O Histórico da carteira e o Histórico do processo leem a mesma tabela `process_events` e agora usam o mesmo componente `renderHistoryEvents`: a carteira mostra a empresa e abre o processo; o da malha mostra só os eventos daquele processo.

## Estado verificado do aplicativo

- `APP_VERSION` em `app.py`: **1.41.0**.
- Inicializador Windows e `desktop_launcher.py`: porta **8141**, título Matriz Fiscal 1.41.
- Planejador em `services/pgdas_planner.py`: versão **2.4.0**, estratégia `UPFRONT_COMPLETE_PLAN`.
- `README.md` e `docs/CHECKLIST_BETA_COMERCIAL.md` descrevem essa mesma 1.41 / 8141.
- `compose.yaml` publica `127.0.0.1:8145:8145` e sobe o uvicorn na 8145. Isso não bate com o `.bat`.

## Descompasso que não pode ser esquecido

A pasta, `RELEASE_NOTES_1.42.md` a `RELEASE_NOTES_1.45.md` e os HTML `COMO_ABRIR_VERSAO_1.4x.html` anunciam portas 8142–8145 e regras novas. Essas regras **não estão no código**:

- `adapt_plan_to_last_transmitted` é importada em `tests/test_v145_last_declared_cutoff.py` e **não existe** em `services/pgdas_planner.py`.
- `database.set_last_transmitted_pgdas`, `get_last_transmitted_pgdas` e `list_pgdas_missing_status` são usadas nos testes 1.44/1.45 e **não existem** em `database.py`.
- O teste 1.45 lê um PDF em `/mnt/data/MALHA FISCAL RF(1).pdf`, caminho que não faz parte deste workspace Windows.

Tratar nota de versão 1.43–1.45 como comportamento atual produz decisão errada.

## Documentos de regra desatualizados em relação ao código 1.41

- `docs/regra-planejador-pgdas.md` — diz que competência só Tipo 01 não gera pedido de PGDAS. O planejador 2.4.0 pede PGDAS para toda competência da malha.
- `docs/motor-tributario-v1.md` — limita anexos I a IV e diz que a segregação ainda será feita. O código tem tabelas I a V; segregação e linhas de receita existem, mas `/api/calculate-tax` ainda calcula anexo único.
- `docs/planejador-pgdas-v2.md` — cobre só o complemento posterior do Tipo 17. O plano antecipado completo está no código 2.4.0.

## Alteração recente deste ciclo

Criação de `jarvis_docs/` com contexto de produto, arquitetura, stack, progresso e regras de negócio. Sem commit.

## Próximos passos

1. Confirmar com o responsável se a meta é permanecer na 1.41 ou implementar de fato o corte do último PGDAS transmitido (notas 1.44 e 1.45).
2. Se a meta for 1.45, implementar no planejador e no banco antes de subir `APP_VERSION`, porta e inicializador. Não marcar a versão só nos HTML.
3. Ao implementar, não usar receita hipotética zero como receita real nem como base de DAS.
4. Não editar código fiscal sem reler `jarvis_docs/regrasDeNegocio.md` e `jarvis_docs/techContext.md`.
