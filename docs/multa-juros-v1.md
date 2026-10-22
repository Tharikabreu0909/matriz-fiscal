# Multa e juros v1

## Multa

`min(dias de atraso × 0,33%, 20%) × principal`

## Juros

- Selic mensal do mês seguinte ao vencimento até o mês anterior à atualização;
- mais 1% no mês da atualização;
- zero no próprio mês do vencimento.

## Fonte

Banco Central do Brasil, série SGS 4390 — Selic acumulada no mês.

## Vencimento

1. usar o vencimento extraído do PGDAS quando disponível;
2. caso contrário, estimar o dia 20 do mês seguinte;
3. sábado ou domingo avança para segunda-feira;
4. sinalizar que feriados bancários e prorrogações extraordinárias podem
   alterar o vencimento.
