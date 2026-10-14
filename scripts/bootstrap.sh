#!/usr/bin/env bash
# Crea OIDC provider, roles de GitHub Actions y bucket de estado; luego configura el repo con gh.
# Uso: AWS_PROFILE=<perfil> ./scripts/bootstrap.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOOT="$ROOT/bootstrap"
STACK="$ROOT/examples/orphan-hunter"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Falta '$1' en el PATH." >&2; exit 1; }; }
tfvar() { sed -nE "s/^$1[[:space:]]*=[[:space:]]*\"?([^\"#]*[^\"#[:space:]])\"?.*/\1/p" "$BOOT/terraform.tfvars"; }
out() { terraform -chdir="$BOOT" output -raw "$1"; }

need terraform
need aws

account="$(aws sts get-caller-identity --query Account --output text)"
owner="$(tfvar github_owner)"
repo="$(tfvar github_repo)"
environment="$(tfvar github_environment)"
slug="$owner/$repo"
echo "Cuenta AWS: $account · repo: $slug · environment: $environment"

terraform -chdir="$BOOT" init -input=false

if [[ "$(tfvar create_oidc_provider)" == "true" ]] \
  && aws iam list-open-id-connect-providers --query 'OpenIDConnectProviderList[].Arn' --output text \
     | grep -q 'token.actions.githubusercontent.com' \
  && ! terraform -chdir="$BOOT" state list 2>/dev/null | grep -q 'aws_iam_openid_connect_provider.github'; then
  echo "La cuenta ya tiene el OIDC provider de GitHub. Pon create_oidc_provider = false en bootstrap/terraform.tfvars." >&2
  exit 1
fi

terraform -chdir="$BOOT" apply -input=false

region="$(out region)"
bucket="$(out state_bucket)"
plan_role="$(out plan_role_arn)"
deploy_role="$(out deploy_role_arn)"

printf 'bucket = "%s"\nregion = "%s"\n' "$bucket" "$region" > "$STACK/backend.hcl"
echo "Escribi examples/orphan-hunter/backend.hcl (bucket $bucket)."

if ! command -v gh >/dev/null 2>&1 || ! gh auth status >/dev/null 2>&1; then
  cat <<EOF

gh no esta instalado o no tiene sesion. Configura en GitHub > Settings > Secrets and variables > Actions > Variables:
  AWS_REGION          = $region
  TF_STATE_BUCKET     = $bucket
  AWS_PLAN_ROLE_ARN   = $plan_role
  AWS_DEPLOY_ROLE_ARN = $deploy_role
y crea el environment '$environment' limitado a la rama main.
EOF
  exit 0
fi

if ! gh repo view "$slug" >/dev/null 2>&1; then
  echo "El repo $slug no existe todavia. Crealo (sin push) y vuelve a correr este script:"
  echo "  gh repo create $slug --public --source \"$ROOT\" --remote origin"
  exit 0
fi

gh variable set AWS_REGION -R "$slug" -b "$region"
gh variable set TF_STATE_BUCKET -R "$slug" -b "$bucket"
gh variable set AWS_PLAN_ROLE_ARN -R "$slug" -b "$plan_role"
gh variable set AWS_DEPLOY_ROLE_ARN -R "$slug" -b "$deploy_role"

gh api -X PUT "repos/$slug/environments/$environment" \
  -F 'deployment_branch_policy[protected_branches]=false' \
  -F 'deployment_branch_policy[custom_branch_policies]=true' >/dev/null
gh api -X POST "repos/$slug/environments/$environment/deployment-branch-policies" \
  -f name=main -f type=branch >/dev/null 2>&1 || true

# Permite que el workflow de la escalera abra Pull Requests con el GITHUB_TOKEN.
gh api -X PUT "repos/$slug/actions/permissions/workflow" \
  -f default_workflow_permissions=read -F can_approve_pull_request_reviews=true >/dev/null

echo "Listo: variables, environment '$environment' y permisos de Actions configurados en $slug."
