"""Run all four scenarios offline and persist session artifacts under
the repo-local sessions/ directory so they can be committed and cited
from the Ex9 reflection.

Usage:
    python scripts/collect_sessions.py

The default `make ex{5,6,7}` runs put session dirs in a tempdir that
evaporates when the process exits. Ex8 persists under user-data dir,
outside the repo. This script monkey-patches the sessions-root context
manager and overrides Ex8's path so every run lands in sessions/.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SESSIONS_ROOT = REPO_ROOT / "sessions"


def _make_dir(scenario: str) -> Path:
    target = SESSIONS_ROOT / scenario
    target.mkdir(parents=True, exist_ok=True)
    return target


@contextlib.contextmanager
def _persist_to_repo(example_name: str, *, persist: bool):  # noqa: ARG001
    yield _make_dir(example_name)


def _patch_paths_module() -> None:
    import sovereign_agent._internal.paths as paths_mod

    paths_mod.example_sessions_dir = _persist_to_repo
    # Re-import sites in run.py modules pick up the patched symbol on import,
    # but modules imported earlier have already bound the original. We import
    # the run modules AFTER patching, so they pick up the patched version.


async def _run_ex5() -> None:
    from starter.edinburgh_research import run as ex5_run

    ex5_run.example_sessions_dir = _persist_to_repo
    print("\n=== Ex5 ===")
    await ex5_run.run_scenario(real=False)


async def _run_ex6() -> None:
    from starter.rasa_half import run as ex6_run

    ex6_run.example_sessions_dir = _persist_to_repo
    print("\n=== Ex6 ===")
    await ex6_run.run_scenario(real=False, auto=False)


async def _run_ex7() -> None:
    from starter.handoff_bridge import run as ex7_run

    ex7_run.example_sessions_dir = _persist_to_repo
    print("\n=== Ex7 ===")
    await ex7_run.run_scenario(real=False)


async def _run_ex8() -> None:
    from sovereign_agent.session.directory import create_session

    from starter.voice_pipeline.manager_persona import ManagerPersona
    from starter.voice_pipeline.voice_loop import run_text_mode

    print("\n=== Ex8 ===")
    target = _make_dir("ex8-voice-pipeline")
    session = create_session(
        scenario="ex8-voice-pipeline",
        task="Converse with Alasdair MacLeod (pub manager) to arrange a booking.",
        sessions_dir=target,
    )
    print(f"Session {session.session_id}")
    print(f"  dir: {session.directory}")

    import os

    if not os.environ.get("NEBIUS_KEY"):
        print("  skipped — NEBIUS_KEY not set; Ex8 text mode needs a live LLM.")
        return

    persona = ManagerPersona.from_env()
    script = (
        "Hi Alasdair, I'd like to book a table for Friday 19:30, party of 6.\n"
        "Great — the deposit is £200, and the catering tier is bar_snacks.\n"
        "Thanks, that's everything. Cheers!\n"
        "\n"
    )
    original_stdin = sys.stdin
    sys.stdin = io.StringIO(script)
    try:
        await run_text_mode(session, persona, max_turns=4)
    finally:
        sys.stdin = original_stdin


async def main() -> int:
    _patch_paths_module()
    SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    await _run_ex5()
    await _run_ex6()
    await _run_ex7()
    await _run_ex8()
    print(f"\nAll sessions written under: {SESSIONS_ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
