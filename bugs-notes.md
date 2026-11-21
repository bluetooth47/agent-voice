# Bugs to look at (notes only, not fixing yet)

Started 2026-11-19 from the user, said on the open mic.

1. (User error, 2026-11-19: they changed permissions, which drops the
   session on purpose. Keep the note in case the drop should be softer.)
   Open mic (constant listening) chat is not being saved fully. Earlier
   open-mic turns in the same chat seem to go missing: Theo had no record
   of a request it made just before, and could not recall its own reply
   from before the last one. Check how open-mic turns are written to the
   saved chat and the resumed session.

   Lead (from the log, 2026-11-19): at 00:20:51 the permission level
   changed ("knobs updated", then "asks before every change"). The
   reconcile_agent docstring in daemon/wake_listen.py says a project or
   permission change rebuilds the agent and drops the session. The very
   next open-mic turn (00:21:21) started with no history. So a permission
   flip probably starts a new chat. Odd: the 00:23:19 flip to trusted did
   not seem to lose this chat, so check both paths.

2. Feels like it keeps starting new chats, with a random "be-deep" chime
   as if it just started listening again. In the log every reply ends with
   "still listening" (a chime), and a few turns were dropped as "open mic:
   not meant for it" or "nothing heard". Find which of those plays the
   chime the user hears out of nowhere, and whether any of them resets
   the chat.

3. Whenever Theo saves a note (writes a file), the whole shell seems to
   restart. Seen 2026-11-19 while writing this file from the open mic.
   Guess: something watches the plugin folder and reloads the shell on any
   file change, even a .md note. Check what watches the folder.

4. After turning open mic off, the "still listening" display stayed up
   longer than expected (user unsure, low confidence, 2026-11-19 late).
   Check whether turning open mic off clears the listening state right
   away or waits out the follow-up window.
