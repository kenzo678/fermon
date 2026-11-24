from datetime import UTC, datetime
from uuid import UUID

import pytest

from fermon.identity.create_admin import run
from fermon.identity.domain import Role
from tests.identity.fakes import FakePasswordHasher, InMemoryUserRepository

ARGV = ["--email", "Boss@Example.com", "--name", "The Boss"]
PASSWORD = "long-enough-password"


class Cli:
    def __init__(self, env: dict[str, str], prompts: list[str] | None = None) -> None:
        self.users = InMemoryUserRepository()
        self.hasher = FakePasswordHasher()
        self.asked: list[str] = []
        answers = iter(prompts or [])

        def prompt(text: str) -> str:
            self.asked.append(text)
            return next(answers)

        self.env = env
        self.prompt = prompt

    async def run(self, argv: list[str] = ARGV) -> int:
        return await run(
            argv,
            env=self.env,
            prompt=self.prompt,
            users=self.users,
            hasher=self.hasher,
            clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
            new_id=lambda: UUID(int=1),
        )


async def test_creates_an_admin_with_the_password_from_the_environment(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = Cli({"FERMON_ADMIN_PASSWORD": PASSWORD})

    assert await cli.run() == 0

    admin = await cli.users.get_by_email("boss@example.com")
    assert admin is not None and (admin.role, admin.display_name) == (Role.ADMIN, "The Boss")
    assert await cli.hasher.verify(admin.password_hash, PASSWORD)
    assert cli.asked == []
    assert PASSWORD not in capsys.readouterr().out


async def test_prompts_twice_when_the_environment_has_no_password() -> None:
    cli = Cli({}, prompts=[PASSWORD, PASSWORD])
    assert await cli.run() == 0
    assert len(cli.asked) == 2 and len(cli.users.users) == 1


async def test_mismatching_confirmation_creates_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = Cli({}, prompts=[PASSWORD, "something-different"])
    assert await cli.run() == 1
    assert cli.users.users == {} and "do not match" in capsys.readouterr().err


async def test_refuses_an_existing_email_and_a_weak_password(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = Cli({"FERMON_ADMIN_PASSWORD": PASSWORD})
    assert await cli.run() == 0
    assert await cli.run(["--email", "BOSS@example.com", "--name", "Again"]) == 1
    assert "already registered" in capsys.readouterr().err

    weak = Cli({"FERMON_ADMIN_PASSWORD": "short"})
    assert await weak.run() == 1
    assert "at least 10" in capsys.readouterr().err and weak.users.users == {}


def test_the_password_can_never_be_passed_on_the_command_line() -> None:
    import asyncio

    cli = Cli({"FERMON_ADMIN_PASSWORD": PASSWORD})
    with pytest.raises(SystemExit):
        asyncio.run(cli.run([*ARGV, "--password", "x"]))
