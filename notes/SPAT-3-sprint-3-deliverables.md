# SPAT-3 Sprint 3 - Deliverables

**Group:** SPAT-3 Smart Expense Tracker

**Sprint 3:** Monday 28 September 2026 - Friday 16 October 2026

---

## Sprint 3 Deliverables

### D1. Production Deployment & Architecture

The application must transition from a local Docker environment to a live, publicly accessible cloud server using the Oracle Cloud Free Tier. A dedicated domain name must be configured with appropriate DNS records. The deployment must include HTTPS, environment-based secrets, persistent media storage, and database migrations. Gunicorn must be implemented (with configured worker/thread counts and graceful shutdowns), while Nginx is retained as the public reverse proxy. CloudBeaver must be kept private and removed from public deployment. Basic deployment documentation and a health-check endpoint must be added.

**Stretch goals (not required for Sprint 3):**

Route the deployed cloud application through Cloudflare's Free Tier CDN to speed up load times for international users and manage SSL certificates.

**Demo:**

* Navigate to the live purchased domain URL via HTTPS.
* Securely log in to an account and demonstrate the application running smoothly on the public internet.
* Hit the health-check endpoint to verify server status.
* Show that CloudBeaver is not publicly accessible.

### D2. Financial Reporting Dashboard

A comprehensive analytics dashboard must be implemented to visualize user spending history. This includes customizable graphs (e.g., pie charts, line graphs, bar graphs) to show spending trends and category breakdowns. The dashboard must feature period-specific filtering (e.g., 24 hours, 1 week, 1 month) and an expense timeline visualization that branches out to show connected receipt line items. The dashboard must display running totals of account balances, statistical summaries, and support exporting data to CSV.

**Stretch goals (not required for Sprint 3):**

Implement backend algorithmic logic for anomaly detection to automatically alert the user to highly unusual spending patterns or outlier transactions.

**Demo:**

* Open the dashboard and view a visual timeline of expenses.
* Apply a 1-week time filter and interact with the graphs to show changes based on different categories.
* Export a financial report to CSV and open the document to verify the data formatting.

### D3. Advanced Tagging Hierarchies & Automation

The current tagging architecture must be expanded to support hierarchical levels and sub-groups. Tags must be able to exist independently or as nested subtags. Additionally, transaction templates must be expanded to automatically apply tags to incoming transactions based on user-defined specifications.

**Stretch goals (not required for Sprint 3):**

Enable bulk group-tagging functionality so users can categorize multiple untagged line items simultaneously directly from the centralized table view.

**Demo:**

* Create a parent tag with nested subtags.
* Select multiple unassigned line items and seamlessly group-tag them using the "select all" feature.
* Show a transaction template automatically applying a predefined tag to a new upload.

### D4. Quality of Life & Performance Enhancements

The system requires significant performance and UX upgrades. Backend data fetching must be accelerated (potentially by running parsers in parallel). Parsers must be updated to handle 3 to 4 different types of bank statements and fix previously broken receipt edge cases.

The UI must introduce a Dark Mode toggle, support multiple currency formats, and provide document previews alongside the upload interface. Table records must be better labeled, and line items belonging to a statement must be visually grouped underneath it rather than returning as loose items in searches. Detailed modal warnings must explicitly explain idempotency conflict resolutions. Finally, proactive spending limits must be introduced, alerting users when they cross 50% and 90% thresholds, and turning remaining funds red when low.

**Stretch goals (not required for Sprint 3):**

Optimize the deployed website's responsive layout so it can be easily viewed and navigated on mobile phone browsers. Integrate an external API for live currency conversions.

**Demo:**

* Upload an overlapping bank statement and show the detailed modal box explaining the idempotency conflict resolution.
* Trigger a spending limit warning showing the 90% threshold and red UI text.
* Toggle Dark Mode on for the application UI.
* Demonstrate faster data loading times and grouped line items in the table.

### D5. Subscription Tracking

The application must identify and track recurring monthly expenses. Utilizing an internal tagging system hidden from the user's primary view, the system will allow users to flag specific purchases as subscriptions. These recurring financial commitments must be aggregated into a dedicated sidebar or dashboard widget.

**Stretch goals (not required for Sprint 3):**

Automatically suggest which expenses might be subscriptions based on recurring identical amounts and merchants over previous months.

**Demo:**

* Flag specific deductions (e.g., Netflix) as subscriptions.
* Show the dedicated subscriptions sidebar automatically tracking these recurring financial commitments.

### D6. Dedicated Tags & Preferences Page

A centralized settings and preferences interface must be developed for the user. This includes a dedicated Tags management page allowing users to pre-plan, create, and configure their tagging hierarchies and templates before uploading any transactions. The page must also capture more realistic bank account information.

**Stretch goals (not required for Sprint 3):**

Implement customizable financial preferences, such as default currency overrides or custom tax year start dates. Automatically detect a new bank from a statement and auto-fill the account information.

**Demo:**

* Navigate to the new Settings page and display the configurations.
* Create a tagging template and set up financial preferences on a fresh account before importing any statements.

### D7. Database Backups

To ensure data integrity on the new live deployment, a robust automated backup strategy must be implemented for the data layer. PostgreSQL database snapshots must be securely stored to prevent permanent data loss in the event of a server failure.

**Stretch goals (not required for Sprint 3):**

Automate daily backups to be stored in a separate, secure cloud storage (e.g., AWS S3) rather than locally on the virtual server.

**Demo:**

* Verify the backup configuration or trigger a manual database backup script via the terminal.
* Explain the automated schedule and where the backups are securely stored.

---