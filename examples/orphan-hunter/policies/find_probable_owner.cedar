// Nivel 0+: buscar en CloudTrail quien creo el recurso (solo lectura).
permit (
  principal is AgentCore::IamEntity,
  action == AgentCore::Action::"${target}___find_probable_owner",
  resource == AgentCore::Gateway::"${gateway_arn}"
)
when {
  principal.id like "arn:aws:*::${account_id}:*"
};
