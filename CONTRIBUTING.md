# Contributing

The working notes for this project live in [CLAUDE.md](CLAUDE.md), and they
are the real document: what earns a test, how to run the installer against a
machine that is not yours, why a setting is three things rather than one, the
four ways the permission system can fail open, and which claims in the README
have measurements behind them.

It is named for the tool that reads it automatically, which is a poor name for
something a person should read first. Hence this file.

The short version:

```bash
./bin/agentvoice-check                     # before every commit, ~2.5min
AGENTVOICE_BOX=1 ./bin/agentvoice-check    # plus eight real installs, ~10min
bin/agentvoice-deploy [COMMIT]             # put a commit into the live plugin
```

Work in a clone outside `~/.config/omarchy/plugins` (here,
`~/Projects/agent-voice`), never in the installed plugin folder: Omarchy
reloads every plugin on any write in that folder. `agentvoice-deploy` is the
one way the live copy changes, and it leaves the live checkout on a detached
HEAD, so `omarchy plugin update` is not the way to update this plugin
here. Deploy a commit instead. The details are in CLAUDE.md, "Where to
work".

Run the first one. Run the second if you touched `install.sh` — every install
bug this project has had hid behind something the development machine already
had.

To see a QML change without restarting your shell, render it beside the live
one: `bench/preview/preview.sh settings` (or `popup`, or `--help` for the
rest). It never takes the keyboard and never writes your settings, and
`--state bench/preview/states/showcase.json` shows it as if the service were
running.
