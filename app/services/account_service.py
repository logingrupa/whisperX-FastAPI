"""AccountService — self-serve user-data deletion (SCOPE-05).

Deletes all tasks owned by the caller plus best-effort cleanup of uploaded
files. The users row itself is PRESERVED (full account deletion is Phase 15
SCOPE-06).
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.core.upload_config import UPLOAD_DIR

TUS_UPLOAD_DIR: Path = UPLOAD_DIR / "tus"


class AccountService:
    """Delete user-owned tasks + files; user row preserved.

    Phase 15 SCOPE-06 will extend with full row deletion (DELETE /api/account).
    """

    def __init__(self, session: Session) -> None:
        self.session = session

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
