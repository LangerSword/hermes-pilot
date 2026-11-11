# Pilot

**A real TTY for Hermes.**

Hermes's terminal tool runs one command through a pipe. Programs that ask a question, draw a full screen,
or wait for a keystroke die there: `ssh` logins, `vim`, `htop`, `fzf`, `less`, installers, `gh auth login`,
REPLs. The usual workarounds are `-y` flags, `yes |`, `expect`, `script -qec`, or giving up.

Pilot gives the agent a real terminal: a private tmux server, one session per task. It opens a program,
reads the screen as text, types literal text and named keys, waits for a pattern, and keeps the session
alive across tool calls. You can attach to the same pane and take over at any time.

**demo:** [video](https://x.com/langersword/status/2120637238585573737) ·
**site:** [langersword.github.io/hermes-portal](https://langersword.github.io/hermes-portal/) ·
**catalog:** [PR #153787](https://github.com/NousResearch/hermes-agent/pull/153787)

If this is useful, a star helps the next person find it.

| the plugin, recorded | the page, hosted |
|---|---|
| ![Pilot typing in a real tmux pane](art/media/demo.gif) | [![Pilot site on GitHub Pages](art/media/site.png)](https://langersword.github.io/hermes-portal/) |
| **recorded:** real keystrokes, 900×506 | **hosted:** GitHub Pages, 1600×900 |

## How it works

![How Pilot works: a coloured whiteboard sketch](art/media/whiteboard.png)

*Agent calls pilot, pilot drives a private tmux pane, the screen comes back as text, and you can attach
to the same pane at any time.*

Five decisions carry it:

- **Private tmux server** (`-L hermes-pilot`): your own tmux sessions are never listed or touched.
- **`remain-on-exit` before the pane is created**: a command that exits instantly still leaves its final
  screen and `#{pane_dead_status}` to read.
- **Text, not ANSI**: `capture-pane -p -J` returns the screen a human sees, with no escape parser.
- **`wait` before reading**: full-screen apps redraw asynchronously, so poll for a pattern or a quiet pane
  instead of sleeping.
- **argv, not interpolation**: commands go through `sh -c` as argv, named keys are allow-listed, and session
  names match `[A-Za-z0-9_-]{1,32}`.

## Tools

The suite registers **24 tools**. `pilot` keeps the full open/screen/type/wait loop; the focused tools are
cheaper to call and add operations the single tool never had.

| tool | what it does |
|---|---|
| `pilot` | the full loop: open, screen, type, wait, list, status, attach, close |
| `pilot_open` | open a program in a new persistent pane |
| `pilot_screen` | read the visible screen plus scrollback |
| `pilot_type` | type literal text and named keys |
| `pilot_wait` | wait for a regex, or for the pane to settle |
| `pilot_list` | list sessions with pid, command, size, dead state, exit status |
| `pilot_status` | status for one session |
| `pilot_attach` | print the human attach command |
| `pilot_close` | close one session |
| `pilot_killall` | close every session |
| `pilot_run` | one-shot command in a fresh TTY; output, exit status, duration |
| `pilot_expect` | scripted wait/type/keys/sleep sequence with a step trace |
| `pilot_search` | regex search the screen and scrollback with context |
| `pilot_diff` | snapshot a pane, then diff the current screen |
| `pilot_log` | record a pane to a log file, stop, or read the tail |
| `pilot_signal` | send Ctrl-C, Ctrl-\\ or Ctrl-Z |
| `pilot_resize` | resize the pane |
| `pilot_rename` | rename a session |
| `pilot_health` | tmux, socket, session counts and limits |
| `pilot_upload` | write a local file into a shell session over base64 |
| `pilot_download` | read a remote file out through base64 |
| `pilot_send` | type text/keys and optionally wait in one call |
| `pilot_snapshot` | save the current screen to a text file |
| `pilot_cleanup` | reap finished sessions past a TTL |

State survives between calls: a REPL keeps its variables, `ssh` keeps its shell, `vim` keeps its buffer.

## Terminal backend

`hermes pilot backend on` sets `terminal.backend: pilot`. Every `terminal` call then runs in a persistent
tmux shell instead of a pipe:

- `cd`, exports and aliases survive across calls and turns;
- `TERM=tmux-256color` and a real `/dev/pts`, so pagers and curses work;
- a timed-out command returns `exit 124` and is left running; `pilot screen` and `pilot type` can inspect it;
- the next call refuses to type into a running program (`exit 126`), so a REPL never receives your next echo.

Restart once from outside the agent with `hermes gateway restart`. Turn it off with `hermes pilot backend off`.

## Run it

```sh
git clone https://github.com/LangerSword/hermes-pilot ~/.hermes/plugins/pilot
hermes plugins enable pilot
hermes pilot list            # sessions, pids, attach commands
hermes pilot attach live1    # Ctrl-b d to detach
hermes pilot killall
```

Needs `tmux` 3.x on PATH. No Python dependencies. The `pilot` tool appears in the next session.
Backend switching needs a restart and `plugins.isolation: in_process` (the default).

## Limits

- Text, not pixels: it reads the terminal grid, so GUI apps are out.
- Full-screen programs redraw. `wait` for a pattern before treating the screen as final.
- An unclosed session keeps running; `hermes pilot killall` cleans up.
- It adds a TTY, not privilege: the agent could already run commands as you.

## Evidence

| check | command | result |
|---|---|---|
| unit tests | `python3 -m unittest discover -s tests` | 46 tests, OK, against real tmux |
| admission | `hermes plugins validate .` | validation passed |
| runtime | `hermes plugins doctor .` | 24 tools registered, 0 hooks |

The suite covers stdin, REPL, vim keystrokes, fzf, exit status and dead-pane reaping. `scripts/demo.py`
runs the same flow on camera.

## Stack

| component | role |
|---|---|
| Python 3 standard library | plugin, tmux wrapper, CLI |
| tmux 3.x | panes, screen capture, keys, exit status |
| Hermes >= 0.22 | plugin host, tool and terminal backend registration |

## Layout

```
plugin.yaml        manifest (24 tools)
__init__.py        register(ctx): tools, terminal backend, /pilot, hermes pilot
pilot_tmux.py      tmux layer: open, screen, type, wait, status, close, attach
pilot_env.py       terminal backend: persistent shell, markers, busy guard, timeout handoff
pilot_tools.py     legacy pilot tool schema and JSON handlers
pilot_toolset.py   the 24-tool suite: schemas, wrappers, dispatch
pilot_features.py  run_once, expect, search, diff, log, transfer, health
pilot_cli.py       hermes pilot and /pilot
tests/             46 stdlib unittest cases (skip cleanly without tmux)
scripts/demo.py    recorded demo: stdin, REPL, vim, fzf, htop
art/media/         README media: demo gif, site shot, whiteboard
```

MIT, Lakshaya Sharma ([@LangerSword](https://github.com/LangerSword)) · v0.3.0.
