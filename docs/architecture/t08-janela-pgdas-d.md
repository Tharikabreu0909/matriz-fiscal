# T08: validacao da janela PGDAS-D (registro; regra do planejador NAO alterada)

Medido em 16/11 sobre 7 documentos de UMA empresa (`coverage.history_start/end`): 6 de 7 seguem
"janeiro do ano anterior .. PA-1"; 1 (PA 06/2022) comeca depois do esperado (compativel com inicio de
atividade, nao comprovado). Essa janela sempre contem os 12 meses anteriores ao PA. Todos os documentos
reportam `has_previous_12_months_for_current_pa = true`.

Conclusao: regra OBSERVADA em uma unica empresa, nao universal. O motor de calculo usa a linha do tempo REAL
(`previous_revenues`) e nao depende da suposicao; ela afeta so o PLANEJAMENTO (o que pedir).
Riscos: empresa com menos de 12 meses (C8), PA com historico parcial, mudanca de layout.
Recomendacao (fora do escopo): coletar mais amostras e checar a cobertura real apos o upload.
`reflection_coverage.py` ainda usa HISTORY_MONTHS=24 (divergencia ja registrada, sem efeito medido):
propor correcao separada. Nunca presumir mes ausente = receita zero.
