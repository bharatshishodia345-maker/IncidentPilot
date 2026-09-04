# IncidentPilot Engineering Instructions

## Product
IncidentPilot is a real-time AI co-commander for high-stakes technical incidents.

Core workflow:

OBSERVE → UNDERSTAND → COORDINATE → RECOMMEND → VERIFY → ACT → LEARN

The system must help incident responders maintain shared situational awareness.

## Core capabilities

1. Real-time incident room
2. Agora-based live voice participation
3. Incident conversation processing
4. Fact extraction
5. Hypothesis extraction
6. Decision tracking
7. Action-item extraction
8. Task ownership
9. Conflict detection
10. Missing-information detection
11. Incident timeline
12. Spoken status summaries
13. Human approval for consequential actions
14. Audit logging
15. Organization-specific policies/context

## Product principle

IncidentPilot is NOT an unrestricted autonomous agent.

AI recommends.
Humans authorize.
System enforces.

The AI must never invent a root cause.

Facts, hypotheses, decisions, unknowns and recommendations must remain clearly separated.

Historical incidents may inform future context only through verified outcomes.

## Security principles

Treat all external input as untrusted.

Consider:
- prompt injection
- SQL injection
- NoSQL injection where applicable
- SSTI
- ReDoS/resource abuse
- LDoS/rate abuse
- secret leakage
- replay attacks
- unauthorized actions
- data exposure

Use:
- validation
- parameterized queries / ORM
- RBAC
- least privilege
- organization isolation
- secret management
- rate limiting
- request/time/token limits
- audit logging
- allowlisted tools
- human approval for consequential actions

Never hardcode secrets.

Never expose API keys to the frontend.

Never allow arbitrary shell execution from LLM output.

Never allow the LLM to directly execute production actions.

## Engineering principles

- Keep the implementation lightweight.
- Every dependency must have a clear reason.
- Prefer simple modular architecture over unnecessary microservices.
- Avoid duplicate code.
- Avoid speculative abstractions.
- Write production-readable Python.
- Use type hints where practical.
- Keep business logic separate from API/UI code.
- Add tests for important behavior.
- Do not silently swallow exceptions.
- Do not use fake implementations while claiming features are production-ready.

## AI output

Prefer structured outputs such as:

{
  "facts": [],
  "hypotheses": [],
  "decisions": [],
  "actions": [],
  "conflicts": [],
  "unknowns": [],
  "timeline_events": []
}

LLM output must be validated before persistence or action.

## Demo scenario

Use a payment outage scenario.

Example:
- payment failures increase
- customer impact confirmed
- database latency proposed as a hypothesis
- conflicting evidence appears
- action assigned to responder
- AI gives spoken status summary
- consequential remediation requires human approval
- final incident summary is generated

Demo data must be clearly labeled as demonstration data.

## Agora

Agora is the real-time communication layer.

It must be treated as a meaningful product dependency, not merely shown in the presentation.

The MVP should demonstrate:
- live incident voice room
- participant presence/context
- AI participation
- real-time/shared updates where practical
- spoken AI status updates

Do not claim Agora features are implemented unless verified.

## Testing

After meaningful changes:
1. run relevant tests
2. run lint/type checks if configured
3. start the application when appropriate
4. verify the changed feature
5. report failures clearly

Before declaring a feature complete, verify it actually works.

## Git

Use small logical commits.

Suggested commit style:

feat:
fix:
refactor:
test:
docs:
chore:

Do not rewrite unrelated files.

Do not remove working functionality without a reason.

## Definition of done

A feature is done only when:
- implementation exists
- validation exists
- tests exist where appropriate
- it runs
- errors are handled
- security implications were considered
- documentation is updated when necessary