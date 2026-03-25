# Directive Conventions

## Confirm Receipt (always include)
Every directive should include a "FIRST ACTION — Confirm Receipt" step requiring `cowork_reports/directive_acknowledged.md` to be created with a timestamp and directive name. This lets the team verify pickup via Cowork.

## Hourly Directive Check (conditional)
- **Long-running tasks** (overnight, weekend, multi-hour): Include the hourly directive check instruction so new/updated `DIRECTIVE_*.md` files are noticed promptly.
- **Office-hours tasks** where the user is present: Hourly checks are not required unless explicitly specified.

## Naming
- Directive files: `DIRECTIVE_<DESCRIPTION>.md` in the project root
- Acknowledgment: `cowork_reports/directive_acknowledged.md`
- User will specify when hourly checks are needed in each directive
