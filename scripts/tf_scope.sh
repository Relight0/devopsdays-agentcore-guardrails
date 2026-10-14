#!/usr/bin/env bash
# Si entre BASE y HEAD solo cambio trust_level en terraform.tfvars, imprime los argumentos para
# aplicar solo las policies de la escalera; si no, no imprime nada (apply completo).
# Uso: scripts/tf_scope.sh <base-ref>
set -euo pipefail

base="$1"
tfvars="examples/orphan-hunter/terraform.tfvars"

changed="$(git diff --name-only "$base" HEAD)"
[ "$changed" = "$tfvars" ] || exit 0

lines="$(git diff -U0 "$base" HEAD -- "$tfvars" | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' || true)"
if [ -n "$lines" ] && ! printf '%s\n' "$lines" | grep -qvE '^[+-]trust_level[[:space:]]*='; then
  echo "-refresh=false -target=module.ladder.aws_bedrockagentcore_policy.this"
fi