# Roadmap

## Hecho

- [x] Patrón validado en AWS: interceptor → Cedar con hechos reales, tools ocultas por nivel, techo IAM por tags.
- [x] orphan-hunter con 5 tipos de recurso, 3 trampas e inyección de prompt; 3 actos ensayados.
- [x] GitHub Actions con OIDC, estado en S3 con `use_lockfile`, plan en PR y apply desde `main`.
- [x] Escalera como flujo de GitHub: promoción por PR, degradación inmediata.

## Siguiente

- [ ] Acotar `gha-deploy` a acciones por servicio en lugar de `PowerUserAccess`.
- [ ] Acotar `EvaluatePolicies` del rol del Gateway al ARN del engine.
- [ ] Drift detection programado (`plan -detailed-exitcode` → issue).
- [ ] Policies nuevas primero en `LOG_ONLY` y comparación con decisiones humanas (shadow mode).
- [ ] Respuestas de los dueños por issue o Slack en lugar de `owner_reply.py`.
- [ ] Módulos versionados (`source = "git::...?ref=vX.Y.Z"`).

## Más agentes sobre el mismo patrón

- [ ] `sg-guardian`: cierra security groups abiertos; puede restringir, nunca abrir.
- [ ] `tag-fixer`: corrige tags; muestra por qué los tags de gobierno necesitan su propio techo.
- [ ] Red team continuo: un agente atacante intenta engañar al gobernado en cada PR.
