# Course Content Authoring

Course data lives in `content/university.yaml`; question banks live in `content/questions.yaml`. You never edit Python to add a lesson.

## Safe publishing workflow

1. Stop the bot and run `backup_database.bat`.
2. Add or edit one lesson in `university.yaml`.
3. Add its approved question bank in `questions.yaml`.
4. Run `.venv\Scripts\python.exe scripts\validate_content.py`.
5. Keep `published: false` until a professor approves the lesson, video, notes, objectives, and questions.
6. Set the lesson and its level to `published: true`, run `seed_course.bat`, restart the bot, and test with a non-staff Discord account.

The loader upserts records by level number, lesson code, and question ID. Keep those identifiers stable after students begin. Renaming a title is safe; changing a code creates progression ambiguity and should be avoided.

## Lesson example

```yaml
- code: "2.7"
  title: Seed Phrases
  description: Learn what a recovery phrase controls and how to protect it.
  order: 7
  prerequisite: "2.6"
  video_url: "https://youtu.be/VERIFIED_VIDEO_ID"
  video_provider: "youtube_unlisted"
  video_duration_minutes: 9
  professor: Fortune & Finance Faculty
  objectives:
    - Explain what a seed phrase controls.
    - Identify safe offline storage practices.
    - Recognize common theft attempts.
  topics: [Seed phrases, Offline storage, Phishing]
  supporting_notes: Never type a real seed phrase into a website, bot, form, or support message.
  resources:
    - name: Seed Phrase Safety Checklist
      url: "https://your-approved-domain.example/checklist.pdf"
  passing_score: 80
  quiz_size: 10
  published: false
```

Only normal HTTPS video and resource URLs should be used. Never place a private token in YAML or in a video URL.

## Question example

```yaml
lesson_banks:
  "2.7":
    - id: L27-001
      prompt: Where should a seed phrase normally be stored?
      options:
        - In a secure offline location
        - In a public Discord message
        - In an unknown website form
        - In a screenshot shared with support
      correct: A
      topic: Seed phrase storage
      explanation: Optional staff-only authoring note.
```

Rules enforced by the validator:

- Exactly four non-empty options.
- `correct` must be `A`, `B`, `C`, or `D`.
- One correct answer only.
- Every published lesson must have at least `quiz_size` active questions.
- Every published level must have at least `exam_size` active level-exam questions.
- Question IDs must be globally unique and stable.

Prefer a bank larger than the presented count: for a 10-question quiz, author 20–30 approved questions. Retakes then use different subsets. Avoid trick questions, ambiguous wording, profit promises, real-time trade instructions, and questions that reward unsafe handling of credentials.

## Level exams

```yaml
level_exams:
  "2":
    exam_size: 15
    questions:
      - id: EX2-001
        prompt: Your approved question
        options: [Choice A, Choice B, Choice C, Choice D]
        correct: A
        topic: Wallet security
```

Students cannot open the level exam until every published lesson in the level and every enabled required assignment in that level is complete.

## Final examination

`final_exam.exam_size` and `final_exam.passing_score` are content settings. Build a bank substantially larger than the presented exam and write fresh integrative questions rather than copying lesson banks. The service draws only from the dedicated final bank.

## Practical assignments

Assignments are defined in `university.yaml`. Use `enabled: true` only when staff is ready to review submissions. `required: true` blocks the level exam until a professor approves the submission.

Submissions support text and an optional HTTPS attachment link. Instructions must never request brokerage credentials, exchange logins, API keys, private keys, seed phrases, or proof of real trades.

## Partner links

Set `partner_key` on a relevant lesson and put the real URL in `.env`, never in Python. The supported initial keys are `coinbase`, `tradingview`, and `bingx`. Referral language must remain clear, and no provider should be described as mandatory unless Fortune & Finance has deliberately made and disclosed that policy.
