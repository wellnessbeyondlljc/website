# Crew Roster

Eleven advisors organized by job-title folder. Dana (delivery-manager) drives
phases and never leads one; Archie (architect) leads Design but does not
double as the driver.

See `templates/commands/wai-crew-convention.md` for the canonical folder spec,
inheritance rules, and version bump policy.

## Members

| Slug                  | Human name | Role                                                            | Version |
|-----------------------|------------|-----------------------------------------------------------------|---------|
| delivery-manager      | Dana       | Lead — drives phases, detects no-shows, surfaces stalls via lug | —       |
| product-strategist    | Pete       | Ideation, intent, risk tier                                     | —       |
| architect             | Archie     | Design, blast radius, rollback                                  | —       |
| ux-designer           | Uma        | User-facing flows, screens                                      | —       |
| persona-steward       | Stella     | Personas, copy, paths                                           | —       |
| release-engineer      | Will       | Build, CI, deploy                                               | —       |
| qa-engineer           | Jordy      | Verify, evidence, regression                                    | —       |
| security-reviewer     | Sage       | Authn/z, secrets, deps, PII                                     | —       |
| site-reliability      | Reggie     | Observability, drift                                            | —       |
| cruft-hygiene         | Hank       | Dead code, deprecations                                         | —       |
| growth-marketer       | Mark       | Content + growth (Clara merged in)                              | —       |

Version column populates as each member folder is scaffolded with frontmatter
(`version:` field in `crew/{slug}/SOP.md`). Member folders are scaffolded by
Phase B / Phase C of the OZI Directive crew rollout; until then the parent
`crew/SOP.md` and `crew/KNOWLEDGE.md` are the effective documents for every
advisor by inheritance.

## Phase division of labor

| Phase     | Lead                     | Consults           |
|-----------|--------------------------|--------------------|
| Ideate    | Pete                     | Stella             |
| Design    | Archie                   | Uma, Sage          |
| Implement | (Tender sub-agents)      | Hank               |
| Build     | Will                     | —                  |
| Verify    | Jordy                    | Stella, Sage       |
| Observe   | Reggie                   | Hank               |

Dana spans every phase as the driver, never the gate-owner.

## Phases

Per-phase SOPs live under `crew/phases/` (all currently `status: stub` —
content will be authored in later Phase rollouts).

| Phase     | File                            | Lead                   |
|-----------|---------------------------------|------------------------|
| Ideate    | [phases/ideate.md](phases/ideate.md)       | Pete                   |
| Design    | [phases/design.md](phases/design.md)       | Archie                 |
| Implement | [phases/implement.md](phases/implement.md) | (Tender sub-agents)    |
| Build     | [phases/build.md](phases/build.md)         | Will                   |
| Verify    | [phases/verify.md](phases/verify.md)       | Jordy                  |
| Observe   | [phases/observe.md](phases/observe.md)     | Reggie                 |
