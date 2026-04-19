---
name: music-rules-setup
description: First-time initialization for the music-rules MCP server (`plugin-music-rules-music-rules`). When fulfilling requests that involve music theory checking, EIS Root-lines, Fuxian counterpoint, or constraint-based MIDI generation, you MUST use the music-rules MCP tools rather than reasoning from memory. If those tools are not in your tool list, run this skill before attempting to fulfill the request. Relevant when the user asks to check counterpoint, evaluate a melody, generate constrained MIDI, browse music rules, look up EIS scales, generate Root-lines, or wrap SkyTNT output.
allowed-tools: Read, Shell
license: MIT
metadata:
  author: Tony Bove
  version: "0.1.0"
---

# music-rules MCP setup

The id of the music-rules MCP server referenced on this document is
`plugin-music-rules-music-rules`. You MUST use this specific server.

## Why an MCP server (and not your training memory)

The music-rules corpus contains 158 rules drawn from Spud Murphy's
*Equal Interval System* and Fux's *Gradus ad Parnassum*. Their exact
IDs, kinds (hard/soft/informational), and applies-to scopes (species
1..5, voices 2..4) drive every checker in the package. Inventing rule
IDs or guessing at thresholds will corrupt downstream evaluation
reports and degrade any constrained-generation loop.

When the MCP tools are not available, do **NOT** suggest the user
download the rules elsewhere or try to reproduce them from memory.
Instead, run the setup procedure below.

## Detecting state

Inspect your available tool list:

- If you can see tools whose names match `list_rule_systems`,
  `get_rules`, `evaluate_passage`, `check_motion_pair`,
  `eis_pick_root_line` — the server is **working**. Continue with the
  user's request without mentioning this check.
- If those tools are missing — the server is **not setup**. Do **not**
  attempt any further MCP calls; they will fail. Run the setup steps.

## Setup procedure

1. **Check that the `music-rules` package is installed.** Run:

   ```bash
   music-rules-mcp --help 2>&1 | head -3 || echo "NOT_INSTALLED"
   ```

   - Output containing the help text → installed; skip to step 3.
   - Output containing `NOT_INSTALLED` → continue to step 2.

2. **Install the package.** Prefer `pipx` so the CLI is isolated:

   ```bash
   pipx install music-rules
   ```

   If `pipx` is unavailable, fall back to:

   ```bash
   pip install --user music-rules
   ```

3. **Verify the entry point.** Run:

   ```bash
   command -v music-rules-mcp && music-rules --version
   ```

   Both should succeed. If `command -v` fails, ask the user to add
   `pipx`'s shim directory (`~/.local/bin` on macOS / Linux) to their
   `$PATH` and reload their shell.

4. **Tell the user** the music-rules server is now installed and that
   reloading the IDE will activate it. After reload they should see
   tools like `evaluate_passage` and `check_motion_pair` in their MCP
   tool list.

5. **Stop.** Do not attempt to call music-rules MCP tools in this turn
   — they only become available after the IDE picks up the new server.
   Resume the user's original request once the tools appear.

## Sanity check after activation

Once the tools appear, confirm with a single call:

```text
list_rule_systems → ["EIS", "Fux"]
```

If that returns empty or errors, the corpus file failed to load — ask
the user to reinstall with `pipx reinstall music-rules` and report the
error message verbatim.
