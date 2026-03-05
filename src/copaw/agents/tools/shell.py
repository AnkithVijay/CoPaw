# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long
"""The shell command tool."""

import asyncio
import locale
import subprocess
import sys
from pathlib import Path
from typing import Optional

from agentscope.tool import ToolResponse
from agentscope.message import TextBlock

from copaw.constant import WORKING_DIR


def _execute_subprocess_sync(
    cmd: str,
    cwd: str,
    timeout: int,
) -> tuple[int, str, str]:
    """Execute subprocess synchronously in a thread.

    This function runs in a separate thread to avoid Windows asyncio
    subprocess limitations.

    Args:
        cmd (`str`):
            The shell command to execute.
        cwd (`str`):
            The working directory for the command execution.
        timeout (`int`):
            The maximum time (in seconds) allowed for the command to run.

    Returns:
        `tuple[int, str, str]`:
            A tuple containing the return code, standard output, and
            standard error of the executed command. If timeout occurs, the
            return code will be -1 and stderr will contain timeout information.
    """
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            encoding=locale.getpreferredencoding(False) or "utf-8",
            errors="replace",
            check=True,
        )
        return (
            result.returncode,
            result.stdout.strip("\n"),
            result.stderr.strip("\n"),
        )
    except subprocess.TimeoutExpired:
        return (
            -1,
            "",
            f"Command execution exceeded the timeout of {timeout} seconds.",
        )
    except Exception as e:
        return -1, "", str(e)


# pylint: disable=too-many-branches, too-many-statements
async def execute_shell_command(
    command: str,
    timeout: int = 60,
    cwd: Optional[Path] = None,
) -> ToolResponse:
    """Run a shell command and return stdout/stderr. For running Python use
    microsandbox_python instead. For Node/JS or other runtimes in the sandbox
    use: msx node '...' or msb exe. Do not use sudo (it hangs). Cwd defaults
    to WORKING_DIR.

    Args:
        command (`str`):
            The shell command to execute.
        timeout (`int`, optional):
            Max seconds (default 60).
        cwd (`Path`, optional):
            Working directory. Default WORKING_DIR.
    """

    cmd = (command or "").strip()

    # Avoid sudo: it waits for a password (no TTY), so the command would hang
    # and then timeout, which can make the agent response stop.
    if cmd.lstrip().startswith("sudo "):
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=(
                        "Command rejected: sudo requires an interactive password "
                        "and will hang or timeout when run from here. "
                        "For Python packages use: pip install <package> (or run in "
                        "microsandbox). For system packages, suggest the user run "
                        "the command manually in their terminal."
                    ),
                ),
            ],
        )

    # Set working directory
    working_dir = cwd if cwd is not None else WORKING_DIR

    try:
        if sys.platform == "win32":
            # Windows: use thread pool to avoid asyncio subprocess limitations
            returncode, stdout_str, stderr_str = await asyncio.to_thread(
                _execute_subprocess_sync,
                cmd,
                str(working_dir),
                timeout,
            )
        else:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                bufsize=0,
                cwd=str(working_dir),
            )

            try:
                # Apply timeout to communicate directly; wait()+communicate()
                # can hang if descendants keep stdout/stderr pipes open.
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
                encoding = locale.getpreferredencoding(False) or "utf-8"
                stdout_str = stdout.decode(encoding, errors="replace").strip(
                    "\n",
                )
                stderr_str = stderr.decode(encoding, errors="replace").strip(
                    "\n",
                )
                returncode = proc.returncode

            except asyncio.TimeoutError:
                # Handle timeout
                stderr_suffix = (
                    f"⚠️ TimeoutError: The command execution exceeded "
                    f"the timeout of {timeout} seconds. "
                    f"Please consider increasing the timeout value if this command "
                    f"requires more time to complete."
                )
                returncode = -1
                try:
                    proc.terminate()
                    # Wait a bit for graceful termination
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=1)
                    except asyncio.TimeoutError:
                        # Force kill if graceful termination fails
                        proc.kill()
                        await proc.wait()

                    # Avoid hanging forever while draining pipes after timeout.
                    try:
                        stdout, stderr = await asyncio.wait_for(
                            proc.communicate(),
                            timeout=1,
                        )
                    except asyncio.TimeoutError:
                        stdout, stderr = b"", b""
                    encoding = locale.getpreferredencoding(False) or "utf-8"
                    stdout_str = stdout.decode(
                        encoding,
                        errors="replace",
                    ).strip(
                        "\n",
                    )
                    stderr_str = stderr.decode(
                        encoding,
                        errors="replace",
                    ).strip(
                        "\n",
                    )
                    if stderr_str:
                        stderr_str += f"\n{stderr_suffix}"
                    else:
                        stderr_str = stderr_suffix
                except ProcessLookupError:
                    stdout_str = ""
                    stderr_str = stderr_suffix

        # Format the response in a human-friendly way
        if returncode == 0:
            # Success case: just show the output
            if stdout_str:
                response_text = stdout_str
            else:
                response_text = "Command executed successfully (no output)."
        else:
            # Error case: show detailed information
            response_parts = [f"Command failed with exit code {returncode}."]
            if stdout_str:
                response_parts.append(f"\n[stdout]\n{stdout_str}")
            if stderr_str:
                response_parts.append(f"\n[stderr]\n{stderr_str}")
            response_text = "".join(response_parts)

        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=response_text,
                ),
            ],
        )

    except Exception as e:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: Shell command execution failed due to \n{e}",
                ),
            ],
        )
