# Trello Card: Centralized Parser Logging

## Description

Replace silent or inconsistent parser output with application-controlled logging. Parser activity is now visible in Docker logs with timestamps, severity, logger names, parse lifecycle events, rejected-row details, and unexpected exception traces.

The result is faster diagnosis during testing and a clear technical explanation when a document cannot be parsed.

## Acceptance Criteria

- [ ] Django configures shared console logging for `parser` and `core` loggers.
- [ ] Log level is controlled through `LOGLEVEL`.
- [ ] Parser instances do not create duplicate per-request handlers.
- [ ] CSV receipt parsing logs start, rejected rows, and completion counts.
- [ ] CSV bank parsing logs start, rejected rows, and completion counts.
- [ ] Expected parser failures include descriptive reasons, such as missing columns.
- [ ] Unexpected failures include server-side exception traces without exposing internals to users.
- [ ] Operators can follow logs with `docker compose logs -f web`.

## Dependencies

- Django application settings loaded by the web service.
- Parser modules using the shared Python logging API.
- Docker Compose web container for live log output.
- `LOGLEVEL` available through `.env` or the container environment.

## Code References

- [config/settings.py](../config/settings.py#L85-L111) - Central logging formatters, handlers, and logger levels.
- [parser/abstract_parser.py](../parser/abstract_parser.py#L1-L13) - Shared parser logger ownership.
- [parser/csv_receipt_parser.py](../parser/csv_receipt_parser.py#L23-L108) - Receipt CSV lifecycle and row-warning logs.
- [parser/csv_bank_parser.py](../parser/csv_bank_parser.py#L9-L105) - Bank CSV lifecycle and row-warning logs.
- [core/receipt_parsing.py](../core/receipt_parsing.py#L60-L90) - Descriptive expected-failure and unexpected-failure logging.
- [core/views.py](../core/views.py#L543-L588) - Background receipt parser logging.
- [core/views.py](../core/views.py#L1066-L1160) - Background statement parser logging.
