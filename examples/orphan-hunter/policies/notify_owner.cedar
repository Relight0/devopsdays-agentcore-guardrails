// Nivel 0+: avisar al dueno. Es seguro porque el interceptor reemplaza `owner`
// por la etiqueta real: el agente propone, la plataforma enruta.
permit (
  principal is AgentCore::IamEntity,
  action == AgentCore::Action::"${target}___notify_owner",
  resource == AgentCore::Gateway::"${gateway_arn}"
)
when {
  principal.id like "arn:aws:*::${account_id}:*" &&
  context.input has owner
};
