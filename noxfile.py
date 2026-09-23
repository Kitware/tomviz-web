from __future__ import annotations

import shutil
from pathlib import Path

import nox

DIR = Path(__file__).parent.resolve()

nox.needs_version = ">=2024.3.2"
nox.options.sessions = ["lint", "tests"]
nox.options.default_venv_backend = "uv|virtualenv"


@nox.session
def lint(session: nox.Session) -> None:
    """
    Run the linter.
    """
    session.install("pre-commit")
    session.run(
        "pre-commit", "run", "--all-files", "--show-diff-on-failure", *session.posargs
    )


@nox.session(venv_backend="none")
def build_js(session: nox.Session) -> None:
    """
    Build the Vue components (vue-components/) into the tomviz_trame.widgets module.
    Needs node (22+) and npm on the PATH.
    """
    session.chdir(DIR / "vue-components")
    session.run("npm", "install", external=True)
    session.run("npm", "run", "build", external=True)


@nox.session(venv_backend="none")
def test_js(session: nox.Session) -> None:
    """
    Run the Vue components' unit tests, type check and lint.
    """
    session.chdir(DIR / "vue-components")
    session.run("npm", "install", external=True)
    session.run("npm", "test", external=True)
    session.run("npm", "run", "type-check", external=True)
    session.run("npx", "eslint", ".", external=True)


@nox.session
def tests(session: nox.Session) -> None:
    """
    Run the unit and regular tests.
    """
    session.install(".[dev]")
    session.run("pytest", *session.posargs)


@nox.session
def build(session: nox.Session) -> None:
    """
    Build an SDist and wheel.
    """

    build_path = DIR.joinpath("build")
    if build_path.exists():
        shutil.rmtree(build_path)

    session.install("build")
    session.run("python", "-m", "build")
