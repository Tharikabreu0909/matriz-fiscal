# Regra do planejador de PGDAS

## Entrada

JSON confirmado pelo leitor da malha.

## Saída

- competências únicas;
- ações preliminares por competência;
- lista inicial de PGDAS necessários;
- competências tipo 17 cobertas por cada arquivo.

## Algoritmo inicial

1. Selecionar apenas competências que contenham tipo 17.
2. Ordenar as competências.
3. Escolher a competência mais recente ainda não coberta.
4. Solicitar o PGDAS dessa própria competência.
5. Marcar como cobertas as competências tipo 17 anteriores dentro da janela de
   24 meses.
6. Repetir até cobrir todas as competências tipo 17.

Competências somente tipo 01 permanecem no processo, mas não geram pedido
inicial de PGDAS.

## Validação posterior

O planejador não presume que já possui todos os meses futuros necessários para
os reflexos. Depois da leitura real dos PGDAS, o sistema valida a linha do tempo
armazenada e solicita complemento somente quando existir lacuna.
