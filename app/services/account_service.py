"""AccountService — self-serve user-data deletion (SCOPE-05) + account summary (UI-07).

Phase 13 (SCOPE-05): deletes all tasks owned by the caller plus best-effort
cleanup of uploaded files; the users row itself is PRESERVED.

Phase 15 (UI-07): adds ``get_account_summary`` — pure read of the users row
for client-side hydration via ``GET /api/account/me``. Future Plan 15-04 will
add ``delete_account`` (full-row removal, SCOPE-06) reusing the same injected
``IUserRepository``.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidCredentialsError
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
