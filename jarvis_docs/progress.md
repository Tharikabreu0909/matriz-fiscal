# Progresso

Leitura de referência: código em 22/10/2026. Versão que o processo inicia: **1.41.0** na porta **8141**. Planejador: **2.4.0**.

## O que funciona no código

- Cadastro de empresa com CNPJ pelos dígitos verificadores. CFDF/IE é complementar.
- Carteira com situação por empresa e um processo principal, com merge de malhas novas.
- Leitura da malha (avisos Tipo 01 e Tipo 17) e do PGDAS (extrato e declaração).
- Bloqueio de malha de outra empresa até confirmação explícita, gravada no histórico.
- PGDAS de outra raiz de CNPJ ou de outra competência não é aceito.
- Plano antecipado de PGDAS para toda competência da malha, mais reflexos potenciais do Tipo 17, com validação `VALID`/`ERROR`. Lista vazia não significa “não se aplica” se a malha tiver competência.
- Análise automática por competência e revisão humana só quando as fontes conflitam ou há avisos duplicados com valores diferentes.
- Estudo contábil com motivo padronizado e dois cenários de cálculo guardados separados.
- Estimativa de anexo único (I a V), reflexos de RBT12 por 12 meses, bloqueio de 2027+, bloqueio se faltar PGDAS de análise/conferência ou receita de mês já vencido.
- Multa de 0,33% ao dia, teto 20%, e juros Selic + 1% no mês da atualização.
- Relatório do cliente sem memória técnica.
- PDF armazenado localmente, backup com documentos, restauração com checagem, pacote de suporte sem valor fiscal.
- Exclusão da empresa remove registros e a pasta de documentos.

## O que existe no código e não é o cálculo da API

- `services/tax_revenue_lines.py` (linhas, Fator R, PIS/Cofins monofásico, ICMS-ST).
- `services/tax_segregation.py` (segregação e Fator R >= 0,28 -> Anexo III, senão Anexo V).
- `services/annex_columns_profile.py`.

O cálculo exposto em `/api/calculate-tax` continua `STANDARD_FULL_REVENUE`.

## O que as notas 1.42–1.45 anunciam e o código não faz

- Troca de porta e de `APP_VERSION` para 1.42, 1.43, 1.44 ou 1.45.
- Seletor de Python 3.11–3.13 e remoção do extra `standard` do uvicorn no requisito pinado.
- Status persistente por PGDAS pedido: disponível, não declarado, não localizado (nota 1.44).
- Relatório parcial que segue sem cálculo quando todo pedido foi marcado (nota 1.44).
- Corte pelo último PGDAS transmitido, escolha de mês/ano 1990–2100, presunção de não transmissão nas competências posteriores e substituição de pedidos futuros pelo PGDAS do último PA (nota 1.45).
- Recusa explícita, no planejador, de receita hipotética R$ 0,00 como receita real.

Esses itens estão em release notes, HTML de abertura e testes que importam funções ausentes. Não estão em `app.py`, `database.py` nem `pgdas_planner.py`.

## Documentação

`docs/` cobre regra fiscal, beta comercial, política de dados e leitor. Parte está atrás do planejador 2.4.0 (`regra-planejador-pgdas.md`, `motor-tributario-v1.md`). O arquivo vigente para regra de negócio é `jarvis_docs/regrasDeNegocio.md`.

## Status

Beta local assistida, operacional na linha 1.41 do código, com motores tributários mais ricos já escritos ao lado do cálculo de anexo único. A linha 1.45 da pasta é meta e nota, não build verificável.
