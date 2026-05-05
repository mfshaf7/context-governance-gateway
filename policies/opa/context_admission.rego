package context.admission

default allow := false

allow if {
  input.packet.policy_profile
  input.packet.admission_decision.raw_projection != "allowed-raw"
}
