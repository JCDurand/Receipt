# Deliverable 8 Demo Notes

## The headline

Deliverable 8 turns parser behavior from a black box into a visible, testable workflow. A client can now watch documents move through processing, inspect the live database in browser-based DBeaver, follow meaningful parser logs in the web container, and see the upload UI stop bad receipt data before it is saved.

The experience is deliberately simple for the user, while the implementation gives the technical team strong evidence when something goes wrong.

## 1. Live database visibility with DBeaver

DBeaver is delivered as part of the application stack through **CloudBeaver**, the browser edition of DBeaver. There is no local DBeaver installation or machine-specific setup required.

Run:

```bash
./start.sh
```

The script starts the full Docker environment and opens:

- Application: `http://localhost/`
- CloudBeaver: `http://localhost:8978/`

The Compose service is defined in [docker-compose.yml](docker-compose.yml#L31-L48). It uses the official `dbeaver/cloudbeaver` image, waits for PostgreSQL to become healthy, persists its workspace, and exposes the browser interface on port `8978`. The PostgreSQL service remains available to host tools on port `5433`, while CloudBeaver connects internally through the Docker hostname `db` on port `5432`.

The startup automation is in [start.sh](start.sh#L1-L18). The DBeaver web credentials can be configured through `DBEAVER_USER` and `DBEAVER_PASSWORD`; the documented defaults are `admin` and `dbeaver`. The setup and connection instructions are also available in [README.md](README.md#L135-L168).

### Suggested client demonstration

1. Open CloudBeaver at `http://localhost:8978/`.
2. Create a PostgreSQL connection with host `db`, port `5432`, and the PostgreSQL credentials from `.env`.
3. Keep the `core_bankstatement`, `core_receipt`, and `core_transaction` tables visible.
4. Upload a document in the application.
5. Refresh the relevant document row and show its processing state changing from `pending` or `processing` to `completed` or `failed`.

This makes the database architecture and parser workflow observable in real time, rather than something that must be inferred from the UI.

## 2. Parser logging: from silent failures to useful evidence

The project now uses one application-controlled logging configuration for parser and core application events. The Django configuration is in [config/settings.py](config/settings.py#L85-L111): logs include timestamps, severity, logger name, and the message, and the log level is controlled by `LOGLEVEL`.

Parser instances now use the shared Python logger instead of creating their own request-specific handlers. This avoids duplicate log lines and lets Docker capture all parser output consistently; see [parser/abstract_parser.py](parser/abstract_parser.py#L1-L13).

CSV receipt parsing now records:

- Parse start
- Rejected line items, including the line number and reason
- Parse completion with transaction and error counts

Those events are implemented in [parser/csv_receipt_parser.py](parser/csv_receipt_parser.py#L23-L108). The same logging pattern is used for bank CSV parsing in [parser/csv_bank_parser.py](parser/csv_bank_parser.py#L9-L105).

The receipt parsing boundary adds a user-safe warning for expected parser failures and a full exception trace for unexpected failures. For example, a missing required column is logged with the actual reason instead of appearing only as an unhelpful HTTP access-log entry. See [core/receipt_parsing.py](core/receipt_parsing.py#L55-L85).

Background receipt and statement processing now logs start, success, warnings, and unexpected failures. The statement worker also cleans up temporary parser files in its `finally` block. See the receipt worker in [core/views.py](core/views.py#L543-L588) and the statement worker in [core/views.py](core/views.py#L1066-L1160).

To show the live log stream during the demo:

```bash
docker compose logs -f web
```

A malformed receipt can now produce a meaningful event such as:

```text
WARNING core.receipt_parsing Receipt parser rejected file ...: Missing required column: quantity
```

The detailed internal exception remains in the server log, while the browser receives a safe, user-facing explanation.

## 3. Persisted parser status and UI feedback

Parser progress is now represented in the data model rather than existing only in terminal output. Both `BankStatement` and `Receipt` support:

```text
pending -> processing -> completed
                         or failed
```

The fields are defined in [core/models.py](core/models.py#L46-L67) and [core/models.py](core/models.py#L235-L255), with the schema change in [core/migrations/0017_bankstatement_parser_error_and_more.py](core/migrations/0017_bankstatement_parser_error_and_more.py). The API exposes `processing_status` and a safe `parser_error` through the unified document response in [core/views.py](core/views.py#L1260-L1275), [core/views.py](core/views.py#L1318-L1335), and [core/views.py](core/views.py#L1350-L1368).

This gives the application a reliable contract for asynchronous work: the UI does not have to guess whether parsing has finished, and the client can verify the same state directly in CloudBeaver.

## 4. Receipt upload remediation

The receipt upload flow now protects data quality before saving anything.

When the receipt or statement preview endpoint returns parser issues, [Uploads.jsx](capitec++/src/pages/Uploads.jsx#L246-L264) changes the parse state to `failed`. This handles both complete parser failures and files where any issue was reported.

The upload modal then:

- Announces parser issues accessibly with `role="alert"` and `aria-live`.
- Disables the Upload button when parsing fails.
- Applies a grey, no-hover, `not-allowed` visual state so the user can immediately see that uploading is unavailable.
- Keeps the handler-level guard, so a stale or programmatic click cannot bypass the disabled button.

The current master UI also supports reviewing parsed receipt or statement rows,
selecting the bank account, and choosing to reconcile a receipt later. Those
workflow controls are part of the same upload modal and do not weaken the
parser-failure guard.

These behaviors are visible in [UploadModal.jsx](capitec++/src/components/UploadModal.jsx#L110-L165), with the greyed-out styling in [FileListTable.css](capitec++/src/styles/FileListTable.css#L661-L686). The second guard is in [Uploads.jsx](capitec++/src/pages/Uploads.jsx#L289-L320).

For asynchronous uploads, the uploads page polls while documents are `pending` or `processing`. When a document transitions to `failed`, it refreshes the table and presents a dismissible alert containing the document name and safe parser error. See [Uploads.jsx](capitec++/src/pages/Uploads.jsx#L143-L176) and [Uploads.jsx](capitec++/src/pages/Uploads.jsx#L402-L420).

### Suggested corrupt-receipt demonstration

Use a CSV receipt with missing required columns, such as `missing_amount.csv`:

```csv
Date,Description
12/08/2026,Test
```

The client will see the parser issue in the modal, the Upload button will be greyed out and disabled, and no receipt is saved. At the same time, the backend log contains the descriptive parser reason. This is the visible proof that malformed input is handled deliberately rather than silently accepted.

## 5. Evidence and confidence

The remediation is covered by automated tests for receipt parsing, expected and unexpected parser failures, upload behavior, and descriptive logging. The regression test for missing required columns is in [core/tests.py](core/tests.py#L250-L300).

The implementation has been validated with:

```bash
docker compose exec web python manage.py check
docker compose exec web python manage.py test core parser
cd capitec++ && npm run lint && npm run build
```

The result is a stronger demonstration story: the same failure is visible in three coordinated places, each serving a different audience:

- **User:** a clear, disabled upload control and readable issue message.
- **Developer:** a timestamped parser log with the actual cause.
- **Client or reviewer:** a live database row showing the document processing state.
