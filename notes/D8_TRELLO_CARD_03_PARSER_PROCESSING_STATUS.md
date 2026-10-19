# Trello Card: Persisted Parser Processing Status

## Description

Make asynchronous document parsing observable in the database and API. Every receipt and bank statement now carries a processing state and a safe parser error message, allowing the UI, CloudBeaver, and support staff to see whether parsing is pending, active, complete, or failed.

This turns background parsing into a reliable application contract instead of an invisible thread.

## Acceptance Criteria

- [ ] Receipts and bank statements support `pending`, `processing`, `completed`, and `failed` states.
- [ ] Background receipt parsing records processing start and terminal success/failure.
- [ ] Background statement parsing records processing start and terminal success/failure.
- [ ] Parser failures store a safe user-facing `parser_error` message.
- [ ] Unexpected parser details remain in logs and are not returned to the browser.
- [ ] Temporary statement-parser files are removed in a `finally` path.
- [ ] The unified document API exposes `processing_status` and `parser_error`.
- [ ] CloudBeaver can display the same state transitions directly from PostgreSQL.

## Dependencies

- Django models and migrations applied to the active database.
- Existing receipt and bank statement upload workers.
- Central parser logging from the parser logging card.
- Authenticated document-list API access.

## Code References

- [core/models.py](../core/models.py#L46-L67) - Bank statement processing fields.
- [core/models.py](../core/models.py#L235-L255) - Receipt processing fields.
- [core/migrations/0017_bankstatement_parser_error_and_more.py](../core/migrations/0017_bankstatement_parser_error_and_more.py) - Schema migration.
- [core/views.py](../core/views.py#L543-L588) - Receipt worker state transitions.
- [core/views.py](../core/views.py#L1066-L1160) - Statement worker state transitions and cleanup.
- [core/views.py](../core/views.py#L1260-L1275) - Upload response status fields.
- [core/views.py](../core/views.py#L1318-L1335) - Receipt document-list status fields.
- [core/views.py](../core/views.py#L1350-L1368) - Statement document-list status fields.
