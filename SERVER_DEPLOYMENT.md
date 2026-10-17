# Fortune & Finance University Server Deployment

Use this guide after the YouTube upload audit passes. Never place `.env`, a Discord token, Google OAuth credentials, or a YouTube token in the handoff ZIP, source control, Discord, or ChatGPT.

## Files and persistent data

- Application source: the complete handoff ZIP
- Private configuration: `.env`, created only on the server
- Student database: `fortune_finance_university.db`, or the configured database from `DATABASE_URL`
- Certificates: `certificates/`
- Backups: `backups/`
- Logs: `logs/`
- Class videos: Unlisted YouTube; they do not live on the bot server

## New server installation

1. Install 64-bit Python 3.12 or newer.
2. Extract the handoff ZIP to a dedicated directory such as `C:\FortuneFinance\University` on Windows or `/opt/fortune-finance-university` on Linux.
3. Open a terminal in that directory.
4. Create and activate a virtual environment.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Linux:

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
```

5. Copy `.env.example` to `.env` on the server and enter the Discord IDs and Discord token. Restrict the file so only the bot service account can read it. YouTube OAuth files are production-workstation credentials and are not needed on the bot server.
6. Validate before touching production data:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\validate_content.py
```

Use `./.venv/bin/python` instead on Linux.

7. Initialize a new database with `seed_course.bat` on Windows or:

```bash
./.venv/bin/python scripts/initialize_database.py
```

8. Start the bot with `run_bot.bat` on Windows or `./.venv/bin/python main.py` on Linux.
9. Test with a non-staff Discord account that already has the paid Student role. Confirm Lesson 0.1 playback, quiz progression, a level exam, and certificate retrieval. Confirm a user without the Student role cannot start the University or receive a watch link.

## Moving an existing installation

1. Stop the old bot so the SQLite database is no longer changing.
2. Run `backup_database.bat` and retain the timestamped backup.
3. Transfer the existing `.env`, database, `certificates/`, and `backups/` through a secure private channel. Do not put them in the source handoff ZIP.
4. Extract the new source without overwriting the transferred `.env` or database.
5. Install dependencies, run tests, and run `scripts/validate_content.py`.
6. Run `seed_course.bat`. The loader updates curriculum records without deleting student progress.
7. Start the bot and verify `/progress`, `/scores`, `/my-certificate`, and an administrator `/course` check.

## Final operating rules

- The configured Student role is the paid-access gate; the bot never self-assigns it.
- The bot sends Unlisted YouTube links only after checking the paid Student role. Unlisted links can still be forwarded, so never post them in public channels.
- Back up the database daily and test restoration periodically.
- Keep the bot role above only the level and Graduate roles it must assign; do not grant Administrator.
- Rotate a Discord or Google OAuth token immediately if it is ever exposed.
- Run `scripts/validate_content.py` and the test suite after curriculum or video changes.
