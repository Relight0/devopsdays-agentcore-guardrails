// Nivel 0+: consultar el inventario de recursos sin uso.
// El `when` evita la regla "Overly Permissive" del servicio: solo principales de esta cuenta.
permit (
  principal is AgentCore::IamEntity,
  action == AgentCore::Action::"${target}___list_candidates",
  resource == AgentCore::Gateway::"${gateway_arn}"
)
when {
  principal.id like "arn:aws:*::${account_id}:*"
};
