# Troubleshooting

## `python` or `py` is not recognized

Install Python 3.12 from <https://www.python.org/downloads/> and select **Add Python to PATH**. Restart Windows, then run `setup.bat` again.

## `Requested Python version (3.12) not installed`

Install Python 3.12 specifically. Newer versions are not required for this build.

## The bot window says a `.env` value is missing

Open `.env`, not `.env.example`. Fill `DISCORD_TOKEN` and `DISCORD_GUILD_ID`. Save as plain text. Windows must not silently rename it to `.env.txt`; enable **View → File name extensions** in File Explorer to check.

## Discord closes the connection with code 4014

In the Developer Portal, open the application → **Bot** → **Privileged Gateway Intents** and enable **Server Members Intent**. Restart the bot.

## Slash commands do not appear

- Confirm the bot was installed to the same server as `DISCORD_GUILD_ID`.
- Confirm the install has `applications.commands` and `bot` scopes.
- Confirm the ID contains digits only.
- Restart the bot and look for `Slash commands synced to guild` in `logs/ffcu.log`.

## The bot cannot assign roles

- Give the bot **Manage Roles**.
- Move the bot role above Student, Level, and Graduate roles.
- Confirm each role ID in `.env`.
- Discord does not let a bot manage a role equal to or above its highest role.

## A lesson says its video is pending

Add a valid `https://` URL under that lesson in `content/university.yaml`, run `seed_course.bat`, then restart. Empty URLs are deliberate placeholders, not failures.

## A quiz says there are no approved questions

The lesson is probably an unpublished draft that was published too early. Add at least `quiz_size` valid questions to `content/questions.yaml`, run `scripts\validate_content.py`, then reseed. Keep unreviewed lessons unpublished.

## YAML content fails validation

Read the exact lesson/question ID in the error. YAML indentation uses spaces, not tabs. Quote titles containing punctuation inside `{compact: entries}`. Every question needs four options and `correct: A`, `B`, `C`, or `D`.

## `database is locked`

Do not run restore or a second bot instance while the bot is active. Close duplicate `run_bot.bat` windows, wait a few seconds, then restart. SQLite WAL and a 30-second timeout handle normal brief concurrency.

## Certificate generation fails

Run `setup.bat` again to install ReportLab. Confirm the `certificates` folder is writable. An administrator can retry `/student-certificate`; duplicate-safe issuance retrieves the existing record rather than issuing another ID.

## The bot stops unexpectedly

Open `logs/ffcu.log` and inspect the last error. Do not post the full log publicly. Run:

```bat
.venv\Scripts\python.exe scripts\validate_content.py
.venv\Scripts\python.exe -m pytest
```

If tests pass but Discord still fails, verify the token, intents, IDs, bot role hierarchy, and internet connection.

## Restore did not work

Stop every bot process first. Confirm the backup ends in `.db`. Drag it onto `restore_database.bat` and type `RESTORE`. Immediately run `seed_course.bat` so current YAML updates are reapplied without deleting restored student progress.
