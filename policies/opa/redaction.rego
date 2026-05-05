package context.redaction

default safe := false

safe if {
  input.redaction_report.report.finding_count == 0
}

safe if {
  input.packet.admission_decision.raw_projection == "denied"
}
