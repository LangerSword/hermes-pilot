# Submission — Hermes Agent Plugin Hackathon

Deadline: **22:00 UTC, Nov 11 2026** (03:30 IST). Entry = the plugin, judged on usefulness, reliability,
polish and creativity. Accepted entries go to the Hermes Marketplace.

## Status

| step | state |
|---|---|
| 1. Catalog PR | **open / mergeable** — https://github.com/NousResearch/hermes-agent/pull/153787 (`plugin-catalog/pilot.yaml`, pinned at `db6da49`) |
| 2. Demo video on X, tag @NousResearch | **posted** — https://x.com/langersword/status/2120594050629972220 |
| 3. Typeform with both links | **SUBMITTED** — “Submission Received”, receipt: `art/out/submission-received.png` |

## X post (attach `art/out/02-keystrokes.mp4`)

```
hermes can run commands. it can't use programs.

ssh, vim, htop, fzf, installers die in a pipe.

pilot gives it a real TTY: private tmux, screen as text, keys as a tool. attach and take over.

@NousResearch #HermesPluginHackathon
```

Reply thread (optional, more proof):

1. `same htop, same second. left: what the terminal tool receives. right: what pilot receives.` — attach `art/out/01-wall-1200x675.png`
2. `the agent typed this. open vim → i → type → esc → :wq. real pane, real keystrokes.` — attach `art/out/02-keystrokes-1080x1350.png`
3. `the other laptop is the real test. ssh in, fix a config in vim, cat it. one session, no copy step.` — attach `art/out/03-ssh-1200x675.png`
4. `open source, MIT, 21 tests against real tmux. no api key, works offline. github.com/LangerSword/hermes-pilot`

## Typeform answers

| field | value |
|---|---|
| Plugin Title | `Pilot` |
| Plugin Description | `A real interactive TTY for Hermes: drive ssh, vim, htop, fzf, installers and REPLs, with human takeover.` |
| Email Address | `lakshaya@langersword.in` |
| Discord Username | `nya-laksu` |
| X Demo Post Link | _the URL from step 2_ |
| GitHub Link to your Hermes Plugin Pull Request | `https://github.com/NousResearch/hermes-agent/pull/153787` |

## Why this entry fits the rubric

- **Usefulness:** unlocks a class of tasks the built-in pipe terminal cannot do (`ssh`, `vim`, `htop`,
  `fzf`, `psql`, installers, REPLs). 123 interactive-shaped invocations and 100 workarounds in 10 weeks
  of one developer's terminal history.
- **Reliability:** 21 stdlib tests against real tmux (stdin, REPL, vim keystrokes, fzf, exit status,
  dead-pane reaping); `hermes plugins validate` passes, security scan safe; `doctor` registers one tool.
- **Polish:** numbered launch set, recorded demo, a runbook for the two-laptop shot, `DEMO-SSH.md`.
- **Creativity:** it is a real TTY, not a prompt: private tmux server, screen-as-text, keys, `wait`,
  human takeover on the same pane.
