# -*- coding: utf-8 -*-
"""Microsandbox-based execution tools.

These tools delegate execution of untrusted Python code to Microsandbox
(`microsandbox` Python SDK), so that workloads run inside a hardware-isolated
microVM instead of the main CoPaw process.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import Optional, Tuple, Type

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse


logger = logging.getLogger(__name__)


def _ensure_microsandbox() -> Tuple[Optional[Type[object]], Optional[str]]:
    """Ensure the Microsandbox Python SDK is available.

    Returns:
        (PythonSandbox class or None, error message or None).

    Behavior:
        - Try to import `microsandbox.PythonSandbox`.
        - On ImportError, attempt to install `microsandbox` into the current
          Python environment via `pip`, then retry the import.
        - If installation or re-import fails, return (None, error_message).
    """
    # First attempt: import without installing
    try:
        from microsandbox import PythonSandbox  # type: ignore[import]

        return PythonSandbox, None
    except ImportError:
        logger.info(
            "Microsandbox Python SDK not found; attempting automatic install "
            "via 'pip install microsandbox'.",
        )

    # Best-effort installation into the current environment
    try:
        subprocess.check_call(  # noqa: S603,S607
            [sys.executable, "-m", "pip", "install", "microsandbox"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Failed to install Microsandbox Python SDK: %s", exc)
        return (
            None,
            (
                "Microsandbox Python SDK is not available in this environment.\n"
                "Automatic installation with 'pip install microsandbox' "
                "failed.\n"
                f"Error: {exc}"
            ),
        )

    # Retry import after installation
    try:
        from microsandbox import PythonSandbox  # type: ignore[import]

        logger.info("Microsandbox Python SDK installed and imported successfully.")
        return PythonSandbox, None
    except ImportError as exc:  # pragma: no cover - defensive
        logger.warning(
            "Microsandbox Python SDK still not importable after installation: %s",
            exc,
        )
        return (
            None,
            (
                "Microsandbox Python SDK is still not available after an "
                "automatic installation attempt.\n"
                "Please install it manually inside the CoPaw environment with:\n"
                "    pip install microsandbox\n"
                "Then restart CoPaw and try again."
            ),
        )


async def microsandbox_python(
    code: str,
    name: str = "copaw-python",
) -> ToolResponse:
    """Run Python code in the sandbox and return the output. Use this when the user
    asks to run, execute, or build something in Python—call this tool instead of
    replying with code for them to run. Isolated execution via Microsandbox.

    Args:
        code (`str`):
            Python source to execute. Use print() for results; tool returns
            captured stdout/stderr.
        name (`str`, optional):
            Sandbox name label. Default "copaw-python".
    """

    normalized_code: str = (code or "").strip()
    if not normalized_code:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text="Microsandbox: no Python code provided to execute.",
                ),
            ],
        )

    python_sandbox_cls, error_msg = _ensure_microsandbox()
    if python_sandbox_cls is None:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=error_msg
                    or (
                        "Microsandbox Python SDK is not available and could "
                        "not be installed automatically.",
                    ),
                ),
            ],
        )

    try:
        async with python_sandbox_cls.create(name=name) as sandbox:  # type: ignore[attr-defined]
            exec_result = await sandbox.run(normalized_code)
            output: Optional[str] = await exec_result.output()

    except Exception as exc:  # pylint: disable=broad-except
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Microsandbox execution failed: {exc}",
                ),
            ],
        )

    cleaned_output = (output or "").strip()
    if not cleaned_output:
        cleaned_output = (
            "Microsandbox executed successfully, but produced no output.\n"
            "Print results inside the sandboxed code (e.g. `print(...)`) to "
            "see them here."
        )

    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text=cleaned_output,
            ),
        ],
    )

