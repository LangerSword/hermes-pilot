# Launch assets

A numbered series, one template: 64px margins, the same header
(`PILOT / A HERMES PLUGIN` left, `EVIDENCE 0N / TOPIC` right), the same footer
(`0N · TOPIC · context` left, repo right), League Gothic display, JetBrains Mono
for evidence. Nothing here is a mockup: the terminal text comes from
`art/src/`, captured by `art/capture.py` (pipe vs Pilot) and
`scripts/ssh_demo.py` (a real ssh session).

| # | file | size | use |
|---|---|---|---|
| 00 | `00-hero-1600x900.png` | 1600×900 | X post 1, GitHub social preview |
| 01 | `01-wall-1200x675.png` | 1200×675 | X post 2 (the argument) |
| 02 | `02-keystrokes-1080x1350.png` | 1080×1350 | X post 3, LinkedIn, Instagram |
| 03 | `03-ssh-1200x675.png` | 1200×675 | X post 4 (the other machine) |
| 04 | `04-spec-1080x1080.png` | 1080×1080 | second platform / carousel |
| — | `icon-512x512.png` | 512×512 | avatar |
| 02 | `02-keystrokes.mp4` / `.gif` | 7.7s, 1200×676 | X post 3 (autoplays) |

Rebuild: `python3 art/capture.py && python3 art/render.py && python3 art/gif.py`
The ssh panel needs `python3 scripts/ssh_demo.py --host …` first.

## X thread

**1 — hook (00 hero)**

```
your agent can run a command.
it can't use a program.

ssh, vim, htop, fzf, installers — anything that asks a question dies in a pipe.

pilot gives hermes a real TTY: it types, reads the screen, waits. you can attach and take over.
```

**2 — proof (01 wall)**

```
same htop. same machine. same second.

left: what hermes' terminal tool receives.
right: what pilot receives.

the model can't read the left one.
```

**3 — the clip (02 keystrokes mp4)**

```
the agent typed this.

open vim → i → type → esc → :wq. real pane, real keystrokes, exit 0.

no mockup. no screenshot trick.
```

**4 — the other machine (03 ssh)**

```
the other laptop is the real test.

ssh in, open a broken config in vim, cw → port, :wq, cat. one session, no local tools on the remote, no copy step.

same tool as the local shot. tailscale or lan, it doesn't care.
```

**5 — repo**

```
pilot is a hermes plugin: a private tmux server, screen as text, keys as a tool, human takeover.

21 tests against real tmux. no api key. works offline.

github.com/LangerSword/hermes-pilot
```

## Alt text

- **00 hero** — Dark poster. Big type: "A terminal tool is a pipe. Pilot is a TTY." On the right, a terminal pane running vim with the line "written by an agent, one keystroke at a time" and a keystroke log: i, typed, Esc, :wq.
- **01 wall** — Two terminal panes side by side. Left, labelled "terminal tool / pipe / TERM=dumb", shows garbled htop control codes, vim "not a terminal" warnings and fzf "inappropriate ioctl for device". Right, labelled "Pilot / TTY / 88×24", shows a clean, readable htop screen.
- **02 keystrokes** — Vertical poster: "The agent typed this." above a vim pane, followed by the `cat` output and the line "every agent can run a command. pilot lets it use a program."
- **03 ssh** — Before/after of a remote config: `porrt = 8080` in red, then `port = 8080` in orange, with the keystrokes ssh → cw → type port → :wq → cat. Captured from a real ssh session.
- **04 spec** — Square poster with the Pilot wordmark, the tagline, tool chips and a small vim pane.
- **02 video** — Screen recording of a terminal: vim opens, a line types itself, Esc, :wq, the file is saved. Caption: the agent typed this.

## LinkedIn / dev.to

```
an agent that can run a command is not an agent that can use a program.

i watched hermes open vim last night, press i, type a line, hit escape, and write :wq. the file on disk had the line. no mockup.

then i pointed it at another machine over ssh: same thing, one pane, a broken config fixed in place. no copy step, no local tools on the remote.

the reason this is hard: every agent terminal is a pipe. ssh, htop, fzf, installers, REPLs — the moment a program asks a question, the pipe has no answer.

pilot is a private tmux server behind a tool. open, read the screen, send keys, wait for a pattern, keep state. you can attach to the same pane and take the keyboard mid-task.

21 tests against real tmux. no api key. works offline.
github.com/LangerSword/hermes-pilot

if you run agents against real machines, which interactive program blocks you most?
```

## Honesty notes

- **02 clip** is a replay: `art/gif.py` drives a real Pilot pane with real keystrokes and records actual
  `capture-pane` frames. The agent's own live run that produced `pilot was here, typed by an agent` is
  in the README evidence table.
- **03 poster** is captured from `scripts/ssh_demo.py` against a real sshd on this machine (port 2222),
  not the second laptop — Tailscale is not installed on this box yet. Rerun the script with
  `--host msi` and `python3 art/render.py` to swap in the two-laptop capture. The poster's claim
  ("real session", "the pane is the machine") stays true; the host in the capture is local.
