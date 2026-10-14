# devopsdays-agentcore-guardrails

[![ci](https://github.com/Relight0/devopsdays-agentcore-guardrails/actions/workflows/ci.yml/badge.svg)](https://github.com/Relight0/devopsdays-agentcore-guardrails/actions/workflows/ci.yml)

Building blocks para que un AI Agent haga trabajo real en AWS **sin salirse de la raya**: Amazon Bedrock AgentCore
Gateway, policies Cedar y una Trust Ladder, todo como código.

Demo de la charla *"Infraestructura con criterio: agentes de IA que no se salen de la raya"* en
**DevOpsDays Bogotá 2026**.

![Arquitectura](docs/img/architecture.png)

## La demo: orphan-hunter

Un agente que limpia recursos huérfanos (EBS volumes, snapshots, Elastic IPs, security groups y network interfaces).
El inventario tiene 14 recursos por lote y tres trampas: recursos con nombre `tmp-…` que en realidad son `env=prod`
con `hold=true`. Una de las notas trae además una inyección de prompt.

| Acto | Carril | Qué pasa |
|---|---|---|
| 1 | sin gobierno | "Elimina los huérfanos." El agente se guía por el nombre y borra las trampas. |
| 2 | gobernado, nivel 2 | Misma orden. Cedar decide con los tags reales y bloquea todo lo que no pasó por el proceso. |
| 3 | Trust Ladder desde nivel 0 | Avisa a los dueños; con 3 confirmaciones propone subir; si se equivoca, baja solo. |

## Estructura

```
modules/                    lambda-function · governed-gateway · trust-ladder
lambdas/                    interceptor genérico y lectura compartida de EC2
guardrails/                 cliente MCP, ledger, Trust Ladder y agente (Python)
examples/orphan-hunter/     escenario: data/*.json, policies/*.cedar, tools y Terraform
bootstrap/                  OIDC provider, roles de GitHub Actions y bucket de estado
scripts/                    CLI del demo y bootstrap.sh
.github/workflows/          ci · terraform · demo
```

Todos los valores de Terraform viven en `terraform.tfvars` de cada stack; las variables no tienen defaults.

## Puesta en marcha

### Requisitos

- Python 3.13, Terraform ≥ 1.10, AWS CLI y [GitHub CLI](https://cli.github.com/) con sesión (`gh auth login`).
- Una cuenta AWS de pruebas con acceso al modelo `us.anthropic.claude-sonnet-4-6` en `us-east-1`.
- Cuota libre para 3 Elastic IPs y 1 VPC (`make preflight` lo revisa).

### 1. Validar sin AWS

```bash
make setup && source .venv/bin/activate
make check
```

### 2. Crear el repo y el bootstrap (una sola vez, desde tu máquina)

```bash
git init -b main && git add . && git commit -m "feat: agentcore-guardrails"
git remote add origin https://github.com/Relight0/devopsdays-agentcore-guardrails.git

export AWS_PROFILE=<tu-perfil>
make bootstrap

git push -u origin main
```

`make bootstrap` crea con Terraform el OIDC provider de GitHub, los roles `devopsdays-agentcore-guardrails-gha-plan` y
`devopsdays-agentcore-guardrails-gha-deploy` y el bucket de estado. Luego, con `gh`, configura las variables del repo
(`AWS_REGION`, `TF_STATE_BUCKET`, `AWS_PLAN_ROLE_ARN`, `AWS_DEPLOY_ROLE_ARN`), el environment `demo` limitado a
`main` y el permiso para que Actions abra Pull Requests. También escribe `examples/orphan-hunter/backend.hcl` para
trabajar en local con el mismo estado.

Si la cuenta ya tiene el OIDC provider de GitHub, pon `create_oidc_provider = false` en `bootstrap/terraform.tfvars`.

### 3. Desplegar

Desde GitHub: **Actions → terraform → Run workflow → apply** (o cualquier push a `main` que toque el stack).

Desde local:

```bash
make init       # si ya tenías estado local: make init-migrate
make apply
```

Después del primer apply confirma la suscripción de SNS en tu correo y espera 10-15 min a que CloudTrail indexe.

### 4. Correr la demo

Desde GitHub: **Actions → demo → Run workflow** y elige el paso (`smoke`, `act1`, `act2`, `act3`, `batch-a`,
`owner-reply`, `ladder-evaluate`, ...). En `ladder-evaluate`:

- **Promoción**: abre un PR con el nuevo `trust_level`. El merge es la aprobación humana y `terraform.yml` lo aplica.
- **Degradación**: se aplica en el mismo run y se publica directo en `main`, sin esperar a nadie.

Desde local, con pausas y tiempos:

```bash
make reseed && make level L=2
make rehearse
```

| Comando | Qué hace |
|---|---|
| `make smoke` | plumbing sin LLM: Gateway, interceptor, Cedar en las 3 trampas |
| `make act1` / `act2` / `act3` | los tres actos |
| `make truth` | tags reales del lote activo (lo que el agente no ve) |
| `make reply NAME=old-build-cache ANSWER=release` | respuesta del dueño |
| `make ladder` / `make ladder-approve` | evalúa la escalera / aplica el ascenso |
| `make destroy` | borra todo (unos US$14/mes si se deja desplegado) |

Si cambias de nivel en local (`make level`, `make ladder`), haz commit y push de `terraform.tfvars`: el siguiente
apply desde `main` usa el valor del repo.

## Calidad

- `ci.yml`: ruff, pytest con moto, lint de Cedar, `terraform fmt` y `validate` de los dos stacks.
- `terraform.yml`: plan comentado en cada PR con el rol de solo lectura; apply desde `main` en el environment `demo`.
- Acciones fijadas por SHA, Dependabot semanal y `pre-commit` (`pre-commit install`).
- Lock files de providers: `make lock` y commitea los `.terraform.lock.hcl`.

## Problemas comunes

| Síntoma | Qué hacer |
|---|---|
| `Not authorized to perform sts:AssumeRoleWithWebIdentity` | el job debe correr en `main` con `environment: demo`, o el repo/owner de `bootstrap/terraform.tfvars` no coincide |
| `CREATE_FAILED ... Overly Permissive` | falta el `when` en un `permit`; `make lint` lo detecta |
| `find_probable_owner` dice `unknown` | CloudTrail aún no indexa; espera 10-15 min |
| `AddressLimitExceeded` | libera Elastic IPs o pide más cuota |
| El PR de la escalera no se crea | habilita *Allow GitHub Actions to create and approve pull requests* (lo hace `make bootstrap`) |

## Más

[Arquitectura](docs/ARCHITECTURE.md) · [Decisiones](docs/DECISIONS.md) · [Roadmap](docs/ROADMAP.md) ·
[Cómo contribuir](CONTRIBUTING.md)

Creado por **José Miguel Vanegas Acosta** ([@Relight0](https://github.com/Relight0)) para DevOpsDays Bogotá 2026.
Licencia [MIT](LICENSE).
