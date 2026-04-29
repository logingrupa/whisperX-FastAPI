"""AccountService — self-serve user-data deletion (SCOPE-05) + account summary (UI-07) + full-account delete (SCOPE-06).

Phase 13 (SCOPE-05): deletes all tasks owned by the caller plus best-effort
cleanup of uploaded files; the users row itself is PRESERVED.

Phase 15 (UI-07): ``get_account_summary`` — pure read of the users row
for client-side hydration via ``GET /api/account/me``.

Phase 15 (SCOPE-06): ``delete_account`` orchestrates a 3-step cascade
(``delete_user_data`` → ``rate_limit_buckets`` prefix-match →
``user_repository.delete`` to fire ORM CASCADE for the 4 CASCADE FKs).
Email-confirm guard is enforced at the service boundary (case-insensitive).
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.logging import logger
from app.core.upload_config import UPLOAD_DIR
from app.domain.repositories.user_repository import IUserRepository
from app.infrastructure.database.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)

TUS_UPLOAD_DIR: Path = UPLOAD_DIR / "tus"


class AccountService:
    """Delete user-owned tasks + files; expose account summary read.

    SCOPE-05: ``delete_user_data`` removes tasks + uploaded files (user row preserved).
    UI-07:    ``get_account_summary`` returns the safe-to-render fields for /me.
    Phase 15 SCOPE-06 will extend with full row deletion (DELETE /api/account).
    """

    def __init__(
        self,
        session: Session,
        user_repository: IUserRepository | None = None,
    ) -> None:
        """Bind a DB session and (optionally) a pre-built user repository.

        SCOPE-05 callers pass ``session`` only; we lazy-construct the repo to
        keep them working untouched. Plan 15-03+15-04 callers inject the repo
        for testability and to share a single instance across methods (DRY).
        """
        self.session = session
        self._user_repository: IUserRepository = (
            user_repository or SQLAlchemyUserRepository(session)
        )

    def delete_user_data(self, user_id: int) -> dict[str, int]:
        """Delete tasks + uploaded files for a single user.

        Returns counts: ``{"tasks_deleted": N, "files_deleted": M}``.
        File deletion is best-effort (no failure if file missing).
        Users row is intentionally preserved.
        """
        file_names = self._collect_user_file_names(user_id)
        tasks_deleted = self._delete_tasks_for_user(user_id)
        files_deleted = self._delete_files(file_names)
        logger.info(
            "Account data deleted user_id=%s tasks=%s files=%s",
            user_id, tasks_deleted, files_deleted,
        )
        return {"tasks_deleted": tasks_deleted, "files_deleted": files_deleted}

    def get_account_summary(self, user_id: int) -> dict:
        """GET /api/account/me service path — pure read of the users row.

        Returns a dict whose keys mirror ``AccountSummaryResponse`` field
        names (T-15-11 allowlist: only safe-to-render fields). Caller wraps
        the return value in the Pydantic schema for response serialization.

        Raises:
            InvalidCredentialsError: User not found (generic — anti-enumeration;
                authenticated requests reaching here without a row indicate a
                race-condition delete, surface uniformly with auth failures).

        Tiger-style: boundary assertion + flat guard + single return.
        """
        assert user_id > 0, "user_id must be positive"

        user = self._user_repository.get_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError()

        return {
            "user_id": int(user.id),
            "email": user.email,
            "plan_tier": user.plan_tier,
            "trial_started_at": user.trial_started_at,
            "token_version": user.token_version,
        }

    def delete_account(
        self, user_id: int, email_confirm: str
    ) -> dict[str, int]:
        """SCOPE-06: full-row delete + cascade. Email-confirm verified.

        Cascade strategy (RESEARCH §"FK Cascade Coverage" — Strategy C
        LOCKED): service-orchestrated explicit pre-delete + ORM cascade.

            Step 1  delete_user_data(uid)             tasks (SET NULL FK)
                                                      + on-disk files
            Step 2  DELETE rate_limit_buckets         no FK; bucket_key
                                                      text prefix match
            Step 3  user_repository.delete(uid)       ORM cascade fires
                                                      for the 4 CASCADE
                                                      FKs (api_keys,
                                                      subscriptions,
                                                      usage_events,
                                                      device_fingerprints)

        Order matters: Pitfall 2 — ``tasks.user_id`` is NOT NULL after
        migration 0003; a bare user delete would IntegrityError because
        ON DELETE SET NULL fires before user-row removal.

        Args:
            user_id: Authenticated caller's user id (must be positive).
            email_confirm: Email typed by user; case-insensitive match
                against ``user.email`` (UI-SPEC §190 + CONTEXT D-RES).

        Returns:
            Counts dict: ``{tasks_deleted, files_deleted,
            rate_limit_buckets_deleted}``.

        Raises:
            InvalidCredentialsError: User not found (anti-enumeration,
                T-15-05). Same generic error used by AuthService.login.
            ValidationError: Email confirmation does not match
                (code=``EMAIL_CONFIRM_MISMATCH``).

        Tiger-style: boundary assertions on both args; flat early-raise
        guards (no nested-if). Logging discipline: ``user_id`` only,
        never ``user.email`` (AUTH-09 + T-13-13 + T-15-11).
        """
        assert user_id > 0, "user_id must be positive"
        assert email_confirm and email_confirm.strip(), (
            "email_confirm required"
        )

        user = self._user_repository.get_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError()

        if email_confirm.strip().lower() != user.email.lower():
            raise ValidationError(
                message="Confirmation email does not match",
                code="EMAIL_CONFIRM_MISMATCH",
                user_message="Confirmation email does not match",
            )

        # Step 1: tasks (SET NULL FK) + uploaded files. Reuses SCOPE-05
        # path which commits internally — that is fine; steps are
        # independent and idempotent.
        counts = self.delete_user_data(user_id)

        # Step 2: rate_limit_buckets (no FK; prefix-match avoids ip:*
        # keys). Pattern locked: 'user:<uid>:%' — matches user:42:hour,
        # user:42:concurrent, user:42:tx:hour, user:42:audio_min:day.
        # NEVER matches ip:10.0.0.0/24:*.
        bucket_count = self.session.execute(
            text(
                "DELETE FROM rate_limit_buckets "
                "WHERE bucket_key LIKE :pattern"
            ),
            {"pattern": f"user:{user_id}:%"},
        ).rowcount or 0

        # Step 3: user row → ORM CASCADE fires for the 4 CASCADE FKs.
        # PRAGMA foreign_keys=ON enforced globally (Phase 10-04 boot).
        deleted = self._user_repository.delete(user_id)
        if not deleted:
            # Race-defensive: another delete won. Treat as user-not-found.
            raise InvalidCredentialsError()
        self.session.commit()

        logger.info(
            "Account deleted user_id=%s tasks=%s files=%s buckets=%s",
            user_id,
            counts["tasks_deleted"],
            counts["files_deleted"],
            bucket_count,
        )
        return {**counts, "rate_limit_buckets_deleted": bucket_count}

    def _collect_user_file_names(self, user_id: int) -> list[str]:
        rows = self.session.execute(
            text(
                "SELECT file_name FROM tasks "
                "WHERE user_id = :uid AND file_name IS NOT NULL"
            ),
            {"uid": user_id},
        ).all()
        return [row[0] for row in rows if row[0]]

    def _delete_tasks_for_user(self, user_id: int) -> int:
        result = self.session.execute(
            text("DELETE FROM tasks WHERE user_id = :uid"),
            {"uid": user_id},
        )
        self.session.commit()
        return int(result.rowcount or 0)

    def _delete_files(self, file_names: list[str]) -> int:
        count = 0
        for name in file_names:
            count += self._unlink_safe(UPLOAD_DIR / name)
            count += self._unlink_safe(TUS_UPLOAD_DIR / name)
        return count

    @staticmethod
    def _unlink_safe(path: Path) -> int:
        if not path.exists():
            return 0
        try:
            path.unlink()
            return 1
        except OSError as exc:
            logger.warning("Failed to delete file path=%s err=%s", path, exc)
            return 0
