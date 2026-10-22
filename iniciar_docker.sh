#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "O Docker nao foi encontrado. Instale o Docker Desktop e tente de novo."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "O Docker Desktop nao esta em execucao. Abra-o, aguarde ficar pronto e tente novamente."
  exit 1
fi

mkdir -p checkfiscal_data

echo
echo "Subindo o Matriz Fiscal 1.45 em http://127.0.0.1:8145"
echo "Os dados ficam em: $(pwd)/checkfiscal_data"
echo "Alteracoes em arquivos .py recarregam o servidor sozinhas."
echo "Alteracoes em static/ aparecem ao atualizar o navegador."
echo "Se mudar requirements.txt, interrompa e suba de novo para reconstruir a imagem."
echo "Para encerrar: Ctrl+C e depois docker compose down"
echo

docker compose up --build
