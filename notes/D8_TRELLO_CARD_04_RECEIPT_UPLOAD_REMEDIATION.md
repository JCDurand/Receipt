# Trello Card: Robust Receipt Upload Failure Handling

## Description

Protect the receipt workflow from corrupt or incomplete input. The parser preview reports issues before persistence, the UI presents those issues accessibly, and the Upload control becomes visibly greyed out and unavailable whenever parsing fails.

The guard exists both in the visual control and in the upload handler, so a stale or programmatic click cannot bypass the validation.

## Acceptance Criteria

- [ ] A receipt parser response containing issues is classified as failed in the upload page.
- [ ] A failed receipt parse disables the Upload button.
- [ ] The disabled button is visibly grey, has no hover movement, and uses a not-allowed cursor.
- [ ] Parser issues are announced with `role="alert"` and `aria-live`.
- [ ] The upload handler refuses unsupported, parsing, or failed states.
- [ ] A malformed receipt is not saved through the normal preview-and-upload flow.
- [ ] Valid receipts continue to show parsed rows for review before upload.
- [ ] Partial or reconciliation workflows still require the appropriate account or reconcile-later choice.
- [ ] Background parser failures produce a dismissible notification without a page refresh.

## Dependencies

- Receipt parse endpoint returning structured `issues`.
- Persisted document status and safe parser errors.
- Unified document-list API.
- Existing Uploads page, modal, and upload styling.

## Code References

- [capitec++/src/pages/Uploads.jsx](../capitec++/src/pages/Uploads.jsx#L246-L264) - Converts parser issues into failed state.
- [capitec++/src/pages/Uploads.jsx](../capitec++/src/pages/Uploads.jsx#L289-L320) - Handler-level upload guard and review payload.
- [capitec++/src/pages/Uploads.jsx](../capitec++/src/pages/Uploads.jsx#L143-L176) - Polling for background parser failures.
- [capitec++/src/pages/Uploads.jsx](../capitec++/src/pages/Uploads.jsx#L402-L420) - Dismissible parser alert.
- [capitec++/src/components/UploadModal.jsx](../capitec++/src/components/UploadModal.jsx#L110-L165) - Accessible issue display and disabled control.
- [capitec++/src/styles/FileListTable.css](../capitec++/src/styles/FileListTable.css#L661-L686) - Grey failed/disabled button styling.
- [core/receipt_parsing.py](../core/receipt_parsing.py#L60-L90) - Structured receipt parser issues.
