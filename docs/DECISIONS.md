# Decisiones

## Hallazgos verificados en AWS (us-east-1)

1. Cedar evalúa el input **después** del interceptor: la policy decide con el dato real.
2. `tools/list` oculta las herramientas que ninguna policy permite.
3. Los cambios de policy se reflejan en segundos; el `apply` tarda más (50-75 s).
4. Default deny: `-32002 Tool Execution Denied`.
5. El servicio rechaza policies "Overly Permissive": todo `permit` lleva un `when` (lo exige `lint_cedar.py`).
6. Contrato del interceptor: entra `event.mcp.gatewayRequest.body`; sale
   `{"interceptorOutputVersion":"1.0","mcp":{"transformedGatewayRequest":{"body":...}}}`.
7. Acciones Cedar: `<target>___<tool>`; resource `AgentCore::Gateway::"<arn>"`; principal `AgentCore::IamEntity`.
8. `ReleaseAddress`, `DeleteSecurityGroup` y `DeleteNetworkInterface` respetan `aws:ResourceTag/*`.
9. En el Acto 1 el modelo detecta la inyección de prompt y aun así borra las trampas: la defensa tiene que vivir
   fuera del modelo.

## Diseño

| Decisión | Por qué |
|---|---|
| Comportamiento como datos (`data/*.json`, `.cedar`) | un agente nuevo es un PR de datos, sin tocar módulos |
| Interceptor genérico con hechos derivados | "¿venció la cuarentena?" lo decide la plataforma, no el agente |
| `ec2_inventory.py` compartido por tools e interceptor | no pueden opinar distinto sobre el mismo recurso |
| `notify_owner` enrutado por el interceptor | CloudTrail dice quién **creó**, no quién **es dueño** |
| `aws:TagKeys` limitado a los tags de revisión | el agente no puede reescribir `env`/`hold` para escaparse |
| Ascenso por confirmación humana (`promote_on`) | autonomía por aciertos verificados, no por actividad |
| Un reclamo del dueño (`rejected`) degrada | un falso positivo también es evidencia |
| 3 lotes de inventario (a/b/c) | un lote limpio por acto, sin `apply` en escena |
| `-target` + `-refresh=false` al cambiar de nivel | no toca los demás recursos |
| Todos los valores en `terraform.tfvars` | una sola fuente de verdad, revisable en cada PR |
| OIDC con roles separados para plan y deploy | sin llaves de larga duración; el plan de un PR no puede cambiar nada |
| Promoción por PR, degradación inmediata | subir requiere un humano; bajar nunca espera |

## Limitaciones

- CloudTrail tarda 5-15 min en indexar: recién desplegado, `find_probable_owner` responde `unknown`.
- En el demo todos los avisos llegan a un solo correo; el asunto dice a quién iban.
- El rol del Gateway evalúa policies con `resources = ["*"]` (pendiente acotar al ARN del engine).
- Sin AWS Organization no hay SCP; `permissions_boundary_arn` queda en `null`.
- `gha-deploy` usa `PowerUserAccess` + IAM acotado al path del proyecto: suficiente para un demo, amplio para
  producción.
