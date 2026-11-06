#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
docker compose up -d --build
printf '%s\n' '靶场地址：http://127.0.0.1:8080'
