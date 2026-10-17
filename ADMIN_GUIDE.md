# Administrator Guide

Administrators are identified by `ADMIN_ROLE_ID` or Discord's Administrator permission. Prefer the dedicated role and do not give the bot or human staff broader Discord permissions than needed.

## Daily commands

- `/university-admin` — private command reminder.
- `/university-stats` — enrollment, active students, graduates, average score, stalled students, certificates.
- `/course` — published levels and lesson counts.
- `/lesson code` — video, publication state, quiz size, and question count.
- `/quiz lesson_code` — active lesson bank count.
- `/exam level_number` — level exam count; use `-1` for final.
- `/student member` and `/student-progress member` — private progress/history views.

## Controlled actions

- `/student-lock member reason` prevents new lessons/quizzes and records the reason.
- `/student-unlock member reason` restores access.
- `/student-reset member reason` deletes attempts, progress, and assignment submissions only for a student without an issued certificate. It does not delete course content.
- `/student-pass member target_type target reason` creates an audited override. `target_type` is `lesson`, `level`, or `final`; `target` is a lesson code such as `2.3`, a level number, or `final`.
- `/student-fail member target_type target reason` removes a lesson or level completion after administrative review. It refuses certified graduates.
- `/student-certificate member certificate_name` issues or retrieves the one certificate permitted for a verified graduate.

Overrides are exceptional. Record a meaningful reason. Do not override a final exam until all published level completions are present. The database retains the acting Discord ID, affected student, action, timestamp, and details.

## Roles and hierarchy

Recommended Discord roles:

1. Bot role (highest of these; never Administrator)
2. FFCU Administrator
3. FFCU Professor
4. FFCU Mentor
5. FFCU Graduate
6. Optional FFCU Level roles
7. FFCU Student

Database locking controls individual lessons. Level roles should control major Discord categories only. Do not create a role per lesson.

## Privacy

Staff commands respond ephemerally. Do not repost individual scores in public channels. Limit direct database and backup access to authorized administrators. Discord user IDs are the identity key; display names may change.

## Operations

- Back up daily and before content changes.
- Review `logs/ffcu.log` for errors without publishing the file.
- Review pending assignments regularly with `/pending-assignments`.
- Follow up on the stalled-student count with appropriate private support, not public naming.
- If the token is exposed, stop the bot, reset the token in the Discord Developer Portal, update `.env`, and restart.
- Test backup restoration on a separate copy at least quarterly.
