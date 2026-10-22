# Motor Tributário v1

## Fórmula

Alíquota efetiva:

`(RBT12 × alíquota nominal − parcela a deduzir) ÷ RBT12`

## Janela

A receita corrigida de uma competência entra na RBT12 dos doze períodos
posteriores. O motor cria uma linha do tempo interna, soma correções
sobrepostas e não replica o imposto como se fosse nova receita.

## Fontes normativas usadas

- Lei Complementar nº 123/2006, art. 18.
- Anexos I a IV com redação vigente desde 01/01/2018.
- Períodos de 2027 em diante ficam bloqueados nesta versão devido às mudanças
  previstas para a transição tributária.

## Limite técnico

O motor v1 pressupõe uma única receita integralmente sujeita ao anexo
selecionado. A segregação por atividade será implementada antes de considerar
o cálculo definitivo.
