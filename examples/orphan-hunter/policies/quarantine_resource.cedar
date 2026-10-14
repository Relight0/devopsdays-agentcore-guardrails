// Nivel 1+: cuarentena (reversible). Solo dev/staging, sin retencion (hold), sin uso real,
// y que no este ya en revision (quarantined, claimed, released: la respuesta del dueno no se pisa).
// Todos estos valores los pone el interceptor a partir del recurso real.
permit (
  principal is AgentCore::IamEntity,
  action == AgentCore::Action::"${target}___quarantine_resource",
  resource == AgentCore::Gateway::"${gateway_arn}"
)
when {
  principal.id like "arn:aws:*::${account_id}:*" &&
  context.input has environment &&
  context.input has hold &&
  context.input has in_use &&
  context.input has quarantine &&
  (context.input.environment == "dev" || context.input.environment == "staging") &&
  context.input.hold == "false" &&
  context.input.in_use == "false" &&
  context.input.quarantine == "none"
};
