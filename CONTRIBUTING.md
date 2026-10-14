# Cómo contribuir

La idea es que este repo crezca con más agentes sobre el mismo patrón. Platform engineering, DevSecOps, cloud o IA:
cualquier aporte suma.

## Flujo

1. Haz fork, crea una rama `feat/...` o `fix/...` y abre un PR contra `main`.
2. Antes de abrirlo: `make check` y `terraform fmt -recursive`.
3. Un PR, un cambio. Mensajes de commit en formato *conventional commits* (`feat:`, `fix:`, `docs:`...).

## Agregar un agente

1. `cp -r examples/orphan-hunter examples/<tu-agente>`.
2. Cambia `data/scenario.json`, `data/tools.json`, `data/ladder.json`, `policies/*.cedar` y `lambdas/tools/`.
3. Si tu recurso no es EC2, agrega un resolver en `lambdas/attribute_resolver/handler.py`.
4. Adapta `tests/test_scenario.py`: atrapa policies sin `when`, campos de Cedar fuera del esquema y niveles que no
   son acumulativos.
5. Toda variable nueva va con su valor en `terraform.tfvars`, sin `default`.

## Reglas de las policies

- Todo `permit` necesita un `when` (el servicio rechaza las policies demasiado permisivas).
- Cedar solo puede leer campos que el interceptor llena con datos verificados; nunca confíes en lo que declara el
  modelo.
- Una policy nueva se prueba primero con `governed_mode = "LOG_ONLY"`.
