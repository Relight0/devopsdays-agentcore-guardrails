// Nivel 2: eliminar solo lo que ya paso por el proceso: cuarentena vencida o liberada
// por su dueno. Prod y hold=true no se eliminan en ningun nivel.
permit (
  principal is AgentCore::IamEntity,
  action == AgentCore::Action::"${target}___delete_resource",
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
  (context.input.quarantine == "expired" || context.input.quarantine == "released")
};
