# Security and Privacy Notes

## Secrets

- Store the Discord token only in `.env`.
- Store YouTube OAuth client and token files only in the excluded local `secrets/` directory used for video production. They are not required on the bot server.
- Never put tokens in YAML, screenshots, chat messages, logs, or source code.
- `.env`, databases, logs, backups, and generated certificates are excluded by `.gitignore`, but exclusion is not encryption.
- Reset the Discord token immediately if it is exposed.
- Revoke the FFCU Video Uploader connection in the Google Account and replace its local OAuth files if either file is exposed.

The software does not request or store passwords, seed phrases, private keys, 2FA codes, exchange credentials, or student trading API keys. Do not modify forms or assignments to collect them.

## Discord least privilege

The bot needs View Channels, Send Messages, Embed Links, Attach Files, and Read Message History. Add Manage Roles only if role awards are used. Keep the bot role below human administrators but above roles it assigns. Do not grant Administrator.

Staff authorization is checked on every command against configured role IDs or Discord Administrator permission. Student-facing buttons are bound to the invoking Discord user. Material admin actions are written to the audit log.

## Data

The database stores Discord user IDs, display/certificate names, progression, attempts, selected answers, assignments, certificate metadata, staff actions, and timestamps. Treat it as private educational data. Restrict operating-system access and backup access. Establish a retention/deletion policy with legal counsel appropriate to the business and student locations.

Display names are not identifiers; Discord user IDs are. Certificate names are administrator/student-approved display data and are sanitized/length-limited.

## URLs and inputs

Assignment attachment links must use HTTPS and are length-limited. Staff should still treat them as untrusted: use an updated browser, do not download executables, and do not sign wallet messages. Course URLs should be reviewed before publication. Referral links must be disclosed.

SQLAlchemy parameterizes database access. YAML is read with `safe_load`. No Python code is executed from course files. Discord errors are handled with a private generic message and detailed rotating logs.

Class-video URLs are restricted to HTTPS YouTube hosts. The WATCH CLASS button is Discord-role-gated, but YouTube Unlisted is not per-viewer authentication: anyone who receives a copied link can watch it. Keep links out of public messages and replace a video/link if it leaks.

## Backups and incident recovery

Use daily backups, encrypted offline retention, and periodic restore tests. Stop the bot before restoring. Keep certificates and their database records together. If compromise is suspected: stop the bot, revoke/reset the token, preserve logs, secure backups, rotate operating-system credentials, review the audit log, and consult an incident-response professional.

SQLite is appropriate for the initial single-process deployment. Before horizontal scaling or multiple bot processes, migrate to PostgreSQL and add a distributed interaction/session strategy.
