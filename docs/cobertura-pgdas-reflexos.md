# Cobertura de PGDAS para os reflexos

## Regra

O PGDAS da competência da malha serve para confirmar a receita original e
recalcular o próprio período.

Para os reflexos, também são necessárias as receitas reais dos períodos
posteriores.

## Exemplo

Correção em 11/2025:

- efeito na RBT12: 12/2025 a 11/2026;
- último PA normalmente vencido em 22/07/2026: 06/2026;
- complemento solicitado: PGDAS 06/2026;
- cálculo real disponível: até 06/2026;
- períodos futuros pendentes: 07/2026 a 11/2026.

## Segurança

O CheckFiscal não usa zero nem projeção automática como receita futura. O
resultado é parcial até que o período exista e o respectivo PGDAS seja
importado.
