# Launch assets

Everything in `art/out/` is generated from `art/render.py` (posters) and `art/gif.py` (the vim clip).
The terminal text is not lorem ipsum: `art/capture.py` runs `htop`/`vim`/`fzf` through a pipe for the
left panel and through Pilot for the right one, and stores the bytes in `art/src/`.

## Files

| file | size | use |
|---|---|---|
| `pilot-hero-1600x900.png` | 1600×900 | X post 1, GitHub social preview |
| `pilot-proof-1200x675.png` | 1200×675 | X post 2 (the argument) |
| `pilot-agent-1080x1350.png` | 1080×1350 | X post 3, LinkedIn, Instagram |
| `pilot-square-1080x1080.png` | 1080×1080 | second platform / carousel |
| `pilot-icon-512x512.png` | 512×512 | avatar |
| `pilot-vim.mp4` | 7.7s, 1200×676 | X post 3 (autoplays) |
| `pilot-vim.gif` | 7.7s | platforms without video |

Rebuild: `python3 art/capture.py && python3 art/render.py && python3 art/gif.py`

## X thread

**1 — hook (hero image)**

```
your agent can run a command.
it can't use a program.

ssh, vim, htop, fzf, installers — anything that asks a question dies in a pipe.

pilot gives hermes a real TTY: it types, reads the screen, waits. you can attach and take over.
```

**2 — proof (proof image)**

```
same htop. same machine. same second.

left: what hermes' terminal tool receives.
right: what pilot receives.

the model can't read the left one.
```

**3 — the clip (pilot-vim.mp4)**

```
the agent typed this.

open vim → i → type → esc → :wq. real pane, real keystrokes, exit 0.

no mockup. no screenshot trick.
```

**4 — repo**

```
pilot is a hermes plugin: a private tmux server, screen as text, keys as a tool, human takeover.

21 tests against real tmux. no api key. works offline.

github.com/LangerSword/hermes-pilot
```

## Alt text

- **hero** — Dark poster. Big type: "A terminal tool is a pipe. Pilot is a TTY." On the right, a terminal pane running vim with the line "written by an agent, one keystroke at a time" and a keystroke log: i, typed, Esc, :wq.
- **proof** — Two terminal panes side by side. Left, labelled "terminal tool / pipe / TERM=dumb", shows garbled htop control codes, vim "not a terminal" warnings and fzf "inappropriate ioctl for device". Right, labelled "Pilot / TTY / 88×24", shows a clean, readable htop screen.
- **agent** — Vertical poster: "The agent typed this." above a vim pane, followed by the `cat` output and the line "every agent can run a command. pilot lets it use a program."
- **square** — Square poster with the Pilot wordmark, the tagline, tool chips and a small vim pane.
- **video** — Screen recording of a terminal: vim opens, a line types itself, Esc, :wq, the file is saved. Caption: the agent typed this.

## LinkedIn / dev.to

```
an agent that can run a command is not an agent that can use a program.

i watched hermes open vim last night, press i, type a line, hit escape, and write :wq. the file on disk had the line. no mockup.

the reason this is hard: every agent terminal is a pipe. ssh, htop, fzf, installers, REPLs — the moment a program asks a question, the pipe has no answer.

pilot is a private tmux server behind a tool. open, read the screen, send keys, wait for a pattern, keep state. you can attach to the same pane and take the keyboard mid-task.

21 tests against real tmux. no api key. works offline.
github.com/LangerSword/hermes-pilot

if you run agents against real machines, which interactive program blocks you most?
```

## Note on honesty

The clip is a replay: `art/gif.py` drives a real Pilot pane with real keystrokes and records actual
`capture-pane` frames — the agent's own live run that produced
`pilot was here, typed by an agent` is the one in the README's evidence table. The posters use only
captured output and no invented screenshots.
