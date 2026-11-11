# The two-laptop shot

Goal: Hermes, on the Legion, SSHes into the MSI over Tailscale, opens a broken config in vim, fixes the
typo, and `cat`s it — while you watch it type in the pane.

**Status on this machine:** Tailscale is not installed and no peer is visible, so the capture in
`art/out/03-ssh-1200x675.png` is a real ssh session against an isolated local sshd (`127.0.0.1:2222`).
The tooling is verified; the two-laptop capture needs the steps below.

## Once

On the **MSI**:

```sh
sudo pacman -S --needed openssh tailscale
sudo systemctl enable --now sshd tailscaled
sudo tailscale up
hostname -s            # note this, e.g. "msi"
```

On the **Legion**:

```sh
sudo pacman -S --needed tailscale
sudo systemctl enable --now tailscaled
sudo tailscale up
tailscale status | grep -i msi
ssh-copy-id <user>@msi           # key auth: the pane must not stop at a password prompt
ssh <user>@msi hostname          # must print the name with no prompt
```

## Capture the still (rebuilds poster 03)

```sh
python3 scripts/ssh_demo.py --host msi --user <user>
python3 art/render.py
```

The script opens `ssh <user>@msi` in Pilot, writes `~/pilot-demo/app.conf` with `porrt = 8080`, opens
vim over ssh, fixes it with `cw` → `port`, saves with `:wq`, and captures the before/after screens.
Exit code 0 means both captures contain the typo and the fix.

## Film the live run (the actual shot)

Terminal A — the agent, with the session named `remote` so you can attach:

```sh
hermes -t pilot -z "Use pilot. Open one session named remote running: ssh <user>@msi . Wait for the shell prompt. Then run: mkdir -p ~/pilot-demo && printf 'porrt = 8080\n' > ~/pilot-demo/app.conf && cat ~/pilot-demo/app.conf . Open it in vim, change porrt to port with cw, save with :wq, then cat the file. Close the session when done."
```

Terminal B — watch it type:

```sh
hermes pilot list
hermes pilot attach remote        # Ctrl-b d to detach
```

Record terminal B with OBS (or `ffmpeg -f x11grab` on X11 / `wf-recorder` on Wayland). The result is
the shot: a real remote shell, vim opening, `cw`, the fix, `:wq`, `cat`.

## Why `cw` and not `:%s`

`cw` changes the word under the cursor — one keystroke, visible on camera, and it proves the agent is
driving vim rather than shelling out to `sed`. The same pattern works for any interactive fix:
`systemctl edit`, `nmtui`, `psql`, an installer prompt, a root-owned config opened in the pane.
