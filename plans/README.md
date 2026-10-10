# Work plans

This directory holds task-specific plans copied from the templates in
[`PLAN.md`](../PLAN.md).

The durable [source-finder implementation plan](source-finder-implementation.md)
is Hebog's authoritative roadmap for scientific equivalence, performance, and
Rapthor integration. Git history records completed work, rationale,
validation and evidence references. [`LOG.md`](../LOG.md) is a historical
archive; do not add new entries. Plans hold current state, remaining work
and acceptance gates; ADRs hold significant architecture decisions.

- Use `<issue-number>-<short-name>.md` when an issue exists, or
  `<YYYY-MM-DD>-<short-name>.md` otherwise.
- Keep the issue or pull request as the source of truth for status when one
  exists. Otherwise keep current status in the plan and completed outcomes
  and evidence references in commits.
- Update a plan when its scope, approach, decisions, gates, sequence, or risks
  change; do not use it as a routine activity log.
- Remove abandoned plans that have no lasting value. Completed plans may remain
  when they provide useful implementation history; architectural decisions
  belong in `docs/architecture/adr/`.
