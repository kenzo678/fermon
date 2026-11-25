"""Create the first administrator.

Usage: ``python -m fermon.identity.create_admin --email ... --name ...``

The password is read from ``FERMON_ADMIN_PASSWORD`` or prompted for, never taken from the command
line (argv is visible to other users through the process list and the shell history).
"""

import argparse
import asyncio
import getpass
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fermon.identity.application import BootstrapAdmin, Clock, PasswordHasher, UserRepository
from fermon.identity.domain import IdentityError

PASSWORD_ENV = "FERMON_ADMIN_PASSWORD"


async def run(
    argv: Sequence[str],
    *,
    env: Mapping[str, str],
    prompt: Callable[[str], str],
    users: UserRepository,
    hasher: PasswordHasher,
    clock: Clock,
    new_id: Callable[[], UUID] = uuid4,
) -> int:
    """Create the admin; returns the process exit code (0 on success)."""
    parser = argparse.ArgumentParser(prog="python -m fermon.identity.create_admin")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True, help="display name")
    args = parser.parse_args(argv)

    password = env.get(PASSWORD_ENV)
    if not password:
        password = prompt("Password: ")
        if prompt("Repeat password: ") != password:
            print("error: the passwords do not match", file=sys.stderr)
            return 1
    try:
        admin = await BootstrapAdmin(users, hasher, clock, new_id).execute(
            args.email, args.name, password
        )
    except IdentityError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"created admin {admin.email}")
    return 0


async def _main() -> int:
    # Imported here so the use of ``run`` in tests does not need a database configuration.
    from fermon.identity.infrastructure.hashing import Argon2PasswordHasher
    from fermon.identity.infrastructure.persistence import SqlAlchemyUserRepository
    from fermon.shared.config import Settings
    from fermon.shared.db import create_engine, create_session_factory

    engine = create_engine(Settings())
    try:
        return await run(
            sys.argv[1:],
            env=os.environ,
            prompt=getpass.getpass,
            users=SqlAlchemyUserRepository(create_session_factory(engine)),
            hasher=Argon2PasswordHasher(),
            clock=lambda: datetime.now(UTC),
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
