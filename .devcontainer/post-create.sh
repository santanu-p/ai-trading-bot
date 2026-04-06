#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env ]; then
  cp .env.example .env
fi

python -m pip install --upgrade pip
python -m pip install -e "backend[dev]"

cd web
npm install
