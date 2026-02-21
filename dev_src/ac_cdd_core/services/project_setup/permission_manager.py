import os
import pwd
from pathlib import Path

from ac_cdd_core.utils import logger


class PermissionManager:
    """Manages file permissions and ownership."""

    async def fix_permissions(self, *paths: Path) -> None:  # noqa: C901, PLR0912, PLR0915
        """Fix file ownership to current user if created with elevated privileges."""
        uid: int | None = None
        gid: int | None = None
        target_user: str | None = None

        if "HOST_UID" in os.environ and "HOST_GID" in os.environ:
            try:
                uid = int(os.environ["HOST_UID"])
                gid = int(os.environ["HOST_GID"])
                target_user = f"host user (UID={uid})"
                logger.info(f"Detected Docker environment: HOST_UID={uid}, HOST_GID={gid}")
            except ValueError:
                logger.debug("Invalid HOST_UID/HOST_GID values")

        if uid is None and "SUDO_USER" in os.environ:
            actual_user = os.environ["SUDO_USER"]
            try:
                pw_record = pwd.getpwnam(actual_user)
                uid = pw_record.pw_uid
                gid = pw_record.pw_gid
                target_user = actual_user
                logger.info(f"Detected sudo environment: user={actual_user}")
            except KeyError:
                logger.debug(f"User {actual_user} not found")

        if uid is None:
            current_user = os.environ.get("USER")
            if current_user and current_user != "root":
                try:
                    pw_record = pwd.getpwnam(current_user)
                    uid = pw_record.pw_uid
                    gid = pw_record.pw_gid
                    target_user = current_user
                except KeyError:
                    pass

        if uid is not None and gid is not None and uid != 0:
            try:
                for path in paths:
                    if path.exists():
                        for item in [path, *list(path.rglob("*"))]:
                            try:
                                os.chown(item, uid, gid)
                            except (PermissionError, OSError) as e:
                                logger.debug(f"Could not fix ownership for {item}: {e}")
                logger.info(f"✓ Fixed file ownership for {target_user}")
            except Exception as e:
                logger.debug(f"Could not chown: {e}")

        try:
            for path in paths:
                if path.exists():
                    for item in [path, *list(path.rglob("*"))]:
                        try:
                            if item.is_dir():
                                item.chmod(0o777)
                            else:
                                item.chmod(0o666)
                        except (PermissionError, OSError) as e:
                            logger.debug(f"Could not relax permissions for {item}: {e}")
            logger.debug("✓ Set permissive file permissions (rw-rw-rw-)")
        except Exception as e:
            logger.debug(f"Could not fix permissions via chmod: {e}")
