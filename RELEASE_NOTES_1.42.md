# CheckFiscal 1.42.0

## Correção da instalação no Windows
- `uvicorn[standard]` foi substituído por `uvicorn` base porque o aplicativo não usa os extras opcionais. Isso evita a tentativa desnecessária de compilar PyYAML.
- O iniciador agora seleciona Python 3.13, 3.12 ou 3.11, em vez de escolher automaticamente Python 3.15.
- Se existir um ambiente virtual criado com Python incompatível, apenas `.venv` é recriada; o banco local permanece em `%LOCALAPPDATA%\CheckFiscal`.
- O instalador mostra instruções claras se não houver uma versão suportada.
- Porta atualizada para 8142 para evitar conflito com instâncias antigas.

## Regras de negócio preservadas
- Solicitar PGDAS para conferência em competências Tipo 01 e Tipo 17.
- Separar conferência documental de cálculo tributário.
- Não presumir omissão, imposto ou reflexo tributário apenas porque há Tipo 01.
