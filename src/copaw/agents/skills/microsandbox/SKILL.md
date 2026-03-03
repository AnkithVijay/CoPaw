---
name: microsandbox
description: "Use this skill when you need to run untrusted or potentially dangerous Python code in a hardened, isolated environment instead of directly on the host. It delegates execution to Microsandbox microVMs via the microsandbox Python SDK, returning only the captured output back to the agent."
metadata:
  {
    "copaw":
      {
        "emoji": "🛡️",
        "requires": {
          "bins": ["msb"],
          "python": ["microsandbox"]
        }
      }
  }
---

# Microsandbox Skill (Isolated Execution)

**Strict: When the user says "you have sandbox", "use the sandbox", "run in sandbox", or "use that to run python scripts" — they mean YOU (the agent) must CALL the sandbox tool.** They are not saying they have a sandbox. Immediately call `microsandbox_python` with the Python code (or `execute_shell_command` for other runtimes) and return the tool output. Do NOT reply with "here is the updated script for the sandbox" or any code for the user to run. Call the tool.

**You must run code yourself — never ask the user to run it.** Do not say "run this in your terminal", "paste the code above", "Save this as `file.py`", "Run the script", "Install required dependencies: pip install...", "open your terminal and run", or "Quick Next Step: run this command". For requests like "create a task dashboard" or "build a script": (1) use `write_file` to create the files in the workspace, (2) use `microsandbox_python` (or `execute_shell_command`) to run the code and show output, (3) then reply with what you did and the result. Do not reply with only code + "How to use" steps. Call `microsandbox_python` (Python) or `execute_shell_command` (e.g. `msx node` for Node/JS) to execute the code, then report the tool output.

**For "build an app" or "show me in the browser":** Run app logic **in the sandbox**, not only by writing files on the host. Use `microsandbox_python` to generate or run the app (e.g. output HTML/JSON); use `execute_shell_command` with `msx node` or a project sandbox (`msr app`) for Node/JS apps. Only use host `write_file` + `browser_use` when you must (e.g. write generated HTML to a file and open it because the sandbox cannot serve a URL). Do **not** default to writing app files to the host and opening them—that bypasses the sandbox. The goal is to build and customize apps over time with execution isolated in the sandbox.

**Task dashboard / "view in browser" / "edit or play around":** Do **not** create only a static markdown file (e.g. `tasks.md`). The user needs an **interactive web UI**. (1) Create a single HTML file with a real UI (add task, list, mark done, delete) and client-side persistence (e.g. `localStorage`). (2) Write it to the workspace (e.g. `task-dashboard.html`). (3) Open it in the browser: `browser_use` with `action=start` (use `headed=true` so the user sees the window), then `action=open` with `url` = the file URL (e.g. `file:///.../task-dashboard.html` using the workspace path). So they can view and use the dashboard immediately.

**Microsandbox is not limited to Python.** It can run Node/JavaScript, and other runtimes via OCI images. For Python you have the **`microsandbox_python`** tool. For JavaScript/Node or other runtimes, use **`execute_shell_command`** with `msx node` (or `msb exe --image node`) to run code in a sandbox when you need isolated execution.

Use this skill to run code inside a hardware-isolated Microsandbox microVM, **not** directly on the host. Prefer this whenever the code is:

- Coming from untrusted input (user-provided scripts, snippets from the web, etc.).
- Manipulating files or data that should stay inside a sandbox.
- Experimental or potentially dangerous (shelling out, network access, etc.).

Tools: **`microsandbox_python`** (Python); for JS/Node/other use **`execute_shell_command`** with `msx <image>` (e.g. `msx node`).

---

## Runtime Dependencies

- **Microsandbox Python SDK** (installed into the CoPaw virtualenv):
  - `pip install microsandbox`
- **Microsandbox CLI & server**:
  - Installed via `https://get.microsandbox.dev` (provides `msb`, `msr`, etc.).
  - Start the server before using this skill:

```bash
msb server start --dev
```

If the SDK is missing or the server is unreachable, the tool will return a clear error message instead of running code on the host.

---

## Tool: `microsandbox_python`

Call this tool to execute Python code inside a Microsandbox `PythonSandbox`.

### Signature

```jsonc
{
  "tool": "microsandbox_python",
  "arguments": {
    "code": "<python_source_code>",
    "name": "copaw-python"   // optional sandbox name label
  }
}
```

- **`code`** (required): Full Python snippet to run in the sandbox.
  - Any values you want to see must be printed.
  - The tool returns the captured output (stdout/stderr) from inside the sandbox.
- **`name`** (optional): Logical sandbox name.
  - You may reuse the same name across calls when you want Microsandbox to keep state, depending on its configuration.

### Behavior

- The agent receives a single text block with everything printed by the code (plus any error message).
- If there is **no output**, the tool responds that execution succeeded but produced no output, and reminds you to use `print(...)` in the code.
- On import / execution failure (e.g., missing SDK, server down), the tool responds with a descriptive error message and **does not** fall back to running code on the host.

---

## When to Prefer `microsandbox_python` vs `execute_shell_command`

- **Use `microsandbox_python`** when:
  - Running untrusted or user-supplied Python snippets.
  - You need isolation guarantees (microVM boundary).
  - You want all computation to happen inside Microsandbox, with only text output coming back.

- **Use `execute_shell_command`** when:
  - You explicitly need to operate on the host filesystem or environment.
  - The operation is trusted, local, and already part of CoPaw’s normal toolchain.

If you are unsure and the user emphasizes safety or isolation, **default to `microsandbox_python`**.

---

## Usage Patterns

- Wrap the user’s code into a complete snippet that:
  - Imports required libraries (if available in the sandbox image).
  - Prints final results in a clear, structured form (e.g., JSON or labeled sections).
- For multi-step workflows, you can:
  - Call `microsandbox_python` multiple times with related snippets.
  - Or write a small orchestrator script that performs all steps and prints a final summary.

If you encounter repeated failures due to missing dependencies or server issues, explain the limitation to the user and suggest checking the Microsandbox installation and `msb server` status.

---

## Project Sandboxes and Reusable Environments

Microsandbox also supports **project-based sandboxes** with persistent environments, similar to a dev container that you can reuse across runs. Use these when you want the same sandbox (packages, files, state) to be available over time instead of a one-off `PythonSandbox`.

### 1. Initialize a project sandbox (once per project)

Use `execute_shell_command` to run the Microsandbox CLI in the CoPaw working directory:

```bash
msb init
msb add app \
  --image python \
  --cpus 1 \
  --memory 1024 \
  --start 'python -c "print(\"hello from project sandbox\")"'
```

This creates a `Sandboxfile` and an `app` sandbox definition. All sandbox state for the project (installed packages, files created in the sandbox) is persisted under `./menv`.

### 2. Run the project sandbox (reusable)

To reuse the same environment later, call:

```bash
msr app         # or: msb run --sandbox app
```

Use `execute_shell_command` to run these commands when you need to:

- Install dependencies inside the sandbox (e.g., `pip install` inside the sandbox image).
- Run long-lived services or scripts whose environment you want to preserve.

### 3. How this relates to Git

- Keep **source code and versioning** in a Git repository on the host (normal CoPaw workspace).
- Use Microsandbox project sandboxes to provide a **persistent, isolated runtime** (`Sandboxfile` + `./menv`).
- When asked to create or reuse a sandboxed environment, prefer:
  - Project sandboxes (`msb init`, `msb add`, `msr app`) for **long-lived, reusable setups**.
  - `microsandbox_python` for **quick, stateless Python execution** where you only need code → output.


