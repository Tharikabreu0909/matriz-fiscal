# CheckFiscal 1.40.0

## Correção principal

- Reconciliação de `work_months` com `raw_rows` para preservar competências e códigos Tipo 17.
- Normalização de códigos `01`/`1` e `17` vindos de dados antigos ou numéricos.
- Validação explícita do plano de PGDAS, incluindo linhas Tipo 17 sem competência identificada.
- A interface não considera mais uma lista vazia como prova automática de que o PGDAS não é necessário.
- Se houver Tipo 17 sem plano completo, a interface exibe erro e bloqueia a análise.
- Se nenhum Tipo 17 for identificado, a interface informa “Não se aplica” e orienta conferir o PDF original caso ele contenha Tipo 17.
- Versão visível no painel e iniciador configurado para a porta local 8140.

## Validação

- Testes automatizados: 149 aprovados.
- Sintaxe JavaScript: validada com Node.js.
- Planejamento de referência da malha Aconchego: quatro solicitações no teste com data de referência 07/08/2026.
