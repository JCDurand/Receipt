# Trello Card: D8 Validation and Demonstration Evidence

## Description

Provide repeatable evidence that the D8 logging and remediation work is operational. The project includes regression coverage for parser failures and descriptive logs, documented Docker/DBeaver setup, and a practical demonstration path from malformed upload to database and log inspection.

This card closes the loop between implementation and a client-ready demonstration.

## Acceptance Criteria

- [ ] Django system checks pass.
- [ ] Core and parser test suites cover valid parsing, invalid rows, missing columns, unexpected parser failures, and upload behavior.
- [ ] A regression test verifies that a missing required column is logged descriptively.
- [ ] Frontend lint passes for the upload workflow.
- [ ] Frontend production build completes successfully.
- [ ] Demo instructions explain how to start the stack, open CloudBeaver, follow web logs, and inspect processing states.
- [ ] A malformed receipt demonstration proves that no invalid receipt is saved through the UI.
- [ ] Code references are available for client technical questions.

## Dependencies

- DBeaver/CloudBeaver container and startup integration.
- Central parser logging.
- Persisted parser processing status and API fields.
- Receipt upload failure handling.
- Docker, PostgreSQL, Python dependencies, and frontend dependencies available.

## Code References

- [core/tests.py](../core/tests.py#L250-L300) - Receipt parser and descriptive logging regression tests.
- [D8_DEMO_NOTES.md](../D8_DEMO_NOTES.md) - Client-facing walkthrough and evidence map.
- [README.md](../README.md#L135-L168) - CloudBeaver setup and database inspection instructions.
- [docker-compose.yml](../docker-compose.yml#L31-L48) - Reproducible D8 service setup.
