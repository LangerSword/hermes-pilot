# 60-second demo

One idea: **the agent can use programs that need a keyboard.** Terminal split on screen the whole time:
left = Hermes, right = `hermes pilot attach <name>` so the viewer watches the agent type.

## 0. Hook (8s)

> "Every agent terminal tool is a pipe. So `ssh`, `vim`, `htop`, `fzf`, installers, REPLs — anything
> that asks a question — is off-limits. Watch what happens when Hermes gets a real TTY."

## 1. It can answer a prompt (12s)

```sh
hermes -t pilot -z "Use pilot to open: printf 'Name? '; read n; echo \"hello \$n\". Wait for 'Name?', type Lakshaya, show me the screen."
```

```
Name? Lakshaya
hello Lakshaya
```

## 2. It can drive a REPL (10s)

```sh
hermes -t pilot -z "Use pilot: open python3 -q as calc, type x = 6*7, then x, show the screen."
```

```
>>> x = 6*7
>>> x
42
```

## 3. It can use vim (15s) — the money shot

```sh
rm -f /tmp/pilot-e2e.txt
hermes -t pilot -z "Use pilot to edit /tmp/pilot-e2e.txt in vim: i, type 'typed by an agent', Escape, :wq. Then cat the file."
```

```
typed by an agent
```

Right pane, live: the cursor moves, insert mode opens, the text appears, `:wq` lands.

## 4. It can read a curses dashboard (10s)

```sh
hermes -t pilot -z "Use pilot to open htop, read the top of the screen, and tell me the load average. Then quit it."
```

The model quotes the real `Load average:` line from the pane.

## 5. You can take over (5s)

```sh
hermes pilot list
hermes pilot attach calc
```

Type in the pane. Detach (`Ctrl-b d`). Ask the agent to `screen` it — it sees what you typed.

## 6. The gate (5s)

```sh
python3 -m unittest discover -s tests     # 19 tests, OK (real tmux, real vim)
hermes plugins validate .                 # Validation passed
hermes plugins doctor .                   # 1 tool
```

## Close (5s)

> "Pilot doesn't simulate a terminal. It is one — tmux, a private socket, a screen read as text.
> That's the difference between an agent that can run commands and an agent that can use programs."
