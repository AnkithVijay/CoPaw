# -*- coding: utf-8 -*-
"""Microsandbox-based execution tools.

These tools delegate execution of untrusted Python code to Microsandbox
(`microsandbox` Python SDK), so that workloads run inside a hardware-isolated
microVM instead of the main CoPaw process.
"""

from typing import Optional

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse


async def microsandbox_python(
    code: str,
    name: str = "copaw-python",
) -> ToolResponse:
    """Execute Python code inside a Microsandbox PythonSandbox.

    Args:
        code: Python source code to execute inside the sandbox.
            The code should print or otherwise emit any results you want
            returned; the tool captures the sandbox process output.
        name: Optional sandbox name label. Multiple calls with the same name
            may reuse VM state depending on Microsandbox configuration.

    Returns:
        ToolResponse containing the captured stdout/stderr from the sandbox
        execution, or an error message if execution fails.
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

    try:
        # Import here so CoPaw can still run when microsandbox is not installed.
        from microsandbox import PythonSandbox  # type: ignore[import]
    except ImportError:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=(
                        "Microsandbox Python SDK is not available in this "
                        "environment.\n"
                        "Install it inside the CoPaw virtual environment with:\n"
                        "    pip install microsandbox\n"
                        "Then restart CoPaw and try again."
                    ),
                ),
            ],
        )

    try:
        async with PythonSandbox.create(name=name) as sandbox:
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

