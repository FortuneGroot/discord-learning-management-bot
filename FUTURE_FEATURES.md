# Future AI Professor and Platform Roadmap

Version 1 deliberately treats the professor video as an HTTPS resource. `Lesson.video_url`, `video_provider`, duration, objectives, topics, notes, resources, and professor name already separate course content from any avatar vendor.

## Phase 2: managed avatar generation

Add a provider interface such as:

```python
class AvatarProvider:
    async def create_video(self, script: str, presenter_id: str, voice_id: str) -> Job: ...
    async def get_status(self, job_id: str) -> JobStatus: ...
```

Implement HeyGen, Synthesia, or another provider behind that interface. Store provider job IDs and asset status in new tables; keep API keys in server environment variables. A background worker should poll jobs, validate the final HTTPS URL, and require professor approval before updating the published lesson. The Discord bot should never wait synchronously for video generation.

## Phase 3: curriculum-grounded tutor

Create a retrieval service over approved lesson transcripts, notes, objectives, glossary entries, and staff FAQs. Answers should cite the relevant lesson section, avoid current price predictions/personalized financial advice, refuse requests for quiz answers or secrets, and recommend University Chat or human sessions when confidence is low. Store moderation/audit events, not trading credentials.

The tutor must receive only content a student has unlocked unless professors explicitly approve broader glossary access. It should never reveal the question bank, correct-answer fields, or another student's records.

## Phase 4: interactive professor classroom

- Short question-and-answer interactions grounded in the current lesson.
- Optional speech-to-text and text-to-speech.
- Captions and downloadable transcripts for accessibility.
- Session time/usage limits and clear AI disclosure.
- Human escalation to University Chat, mentor, or professor.
- Evaluation sets for factual accuracy, safety, answer-key leakage, and financial-advice boundaries.

Real-time avatars should remain a presentation layer over the same course/progression services. They must not rewrite progression logic or become a dependency for quizzes.

## Platform roadmap

- PostgreSQL and Alembic migrations for hosted/multi-process deployment.
- Redis-backed active quiz state for process failover.
- Staff web dashboard with SSO and privacy controls.
- Certificate verification page using existing certificate ID and verification code; QR codes can point there.
- Scheduled session entitlement tracking (4 mentor / 2 professor sessions monthly), without exposing calendar data broadly.
- Transcript/version approval workflow and curriculum change audit history.
- Optional S3-compatible private resource storage with expiring links.
- Accessibility review, localization, and caption quality checks.
- Analytics for difficult topics, stalled students, question quality, and fairness—not public student rankings.

Out of scope unless Fortune & Finance deliberately starts a separate, regulated project: trade execution, custody, exchange credential storage, automated investment advice, unsupervised professional derivatives instruction, or blockchain-based certificates.
