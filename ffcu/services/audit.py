from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ffcu.models import AuditLog


def record_audit(
    session: Session,
    actor_discord_id: int,
    action: str,
    *,
    student_discord_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_discord_id=actor_discord_id,
        action=action[:80],
        student_discord_id=student_discord_id,
        details=details or {},
    )
    session.add(entry)
    return entry
