# Work plans

This directory holds task-specific plans copied from the templates in
[`PLAN.md`](../PLAN.md).

The durable [source-finder implementation plan](source-finder-implementation.md)
was ported from the predecessor scaffold and is the authoritative roadmap for
scientific equivalence, performance, and Rapthor integration. The repository's
[`LOG.md`](../LOG.md) records material progress, evidence, deviations, and next
steps while the plan remains focused on intended work and acceptance gates.

- Use `<issue-number>-<short-name>.md` when an issue exists, or
  `<YYYY-MM-DD>-<short-name>.md` otherwise.
- Keep the issue or pull request as the source of truth for status when one
  exists. Otherwise use `LOG.md` for execution status and evidence.
- Update a plan when its scope, approach, decisions, gates, sequence, or risks
  change; do not use it as a routine activity log.
- Remove abandoned plans that have no lasting value. Completed plans may remain
  when they provide useful implementation history; architectural decisions
  belong in `docs/architecture/adr/`.
