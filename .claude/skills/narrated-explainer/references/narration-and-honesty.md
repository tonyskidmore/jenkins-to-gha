# Writing the narration, and keeping it honest

## Audience and shape

- Write for a mixed audience: a plain-language story in the narration, the technical detail on screen. A viewer who
  only listens should still follow; a viewer who reads the screen gets the exact command or setting.
- Structure that worked: title, a short "what this is and is not" note, the problem in one paragraph, the fundamentals
  (one idea per scene, one analogy at most), then the hands-on walkthrough, then a summary.
- Define a term the first time it appears. Prefer "the SSH server" over a bare daemon name until you have said it once.
- One command per beat in terminal scenes, 15 to 40 words per beat. Explain *why* the command is run and what to look
  for in the output before or while it appears. Skipping the trivial commands (cd, ls) is a mistake only if the viewer
  would wonder where a file came from.
- Aim for 2.5 to 6 minutes per video. A long source (an hour-long walkthrough) becomes a series, one scenes.json per
  chapter, each with the same disclaimer and a short recap.

## What to say about the limits

Say plainly, at the start and again in the summary, what the demo is and is not (a model, a subset, a lab). If the
source doc has a "limits", "not done" or "acceptance" section, the summary must carry it. Never imply something is
deployed, proven in production or complete beyond what the source says. A video that sounds more certain than its
source doc is a defect, even if each sentence can be defended.

## Facts and sources

- Every claim comes from the source docs, a capture, or a command you ran. Put the pointer in the scene's `source`.
- Keep a short `source-facts.md` next to the script: "safe claims" with doc/section pointers, and "do not claim" (things
  that sound true but the source does not support). Re-read the whole source doc before writing it; summaries of docs
  (including your own, or a subagent's) drop caveats.
- Soften absolutes the source softens: "can", "in the tested image", "in the common case".
- No host names, customer names, people, ticket numbers or incident history unless the source doc itself is public and
  the user says so. Redact captures (NX_REDACT, see SKILL.md) for owner names, tokens, run ids and URLs with ids.

## Do not narrate the source doc's mistakes

When a capture disagrees with the source doc's "expected" text, tell the user (in your report, with both versions quoted)
and let them fix the doc. Do not put "the guide says X but the tool printed Y" in the narration or on screen: it goes stale
the moment the doc is corrected, and it makes the video argue with its own source. Narrate what really happened. The
exception is a limitation the doc itself states ("the approver cannot be reproduced"): that stays.

## Text-to-speech friendly writing

- Write numbers as words ("fifty-one", "zero zero", "version nine"). Say file names in words and show them on screen.
- No code symbols in narration (underscores, slashes, equals, braces, camelCase). Say "the main configuration file".
- Acronyms and product names the voice may mangle need phonemes or a respelling in pronunciations.json. The audio step
  prints every word with no phonemes: treat each as a bug, because such words are silently skipped in the audio.
- A word the voice says the wrong way round (e.g. "recreation" as the pastime) goes in `respell` ("re-creation").
- Prefer short sentences. Commas make natural pauses; avoid parentheses.
- You cannot hear the result. Never say a pronunciation "sounds right"; say it was audited, and ask the user to listen.
  Record user-approved pronunciations in pronunciations.json (with a note) so they are not re-litigated.

## Terminal output

- Real output only. Capture it with `nx capture`; do not retype, shorten or "tidy" it. If a real run produces something
  surprising, that is usually a better video than the planned one: say what happened.
- Expected output written in the source doc is not a capture. Run the commands and compare; mismatches are findings for
  the user, not things to paper over.
- Commands that spend money, push to a remote, send messages or need sudo are never run to produce a capture unless the
  user explicitly approved that exact action. Reuse results that already exist on disk, or run only the local, free tier.
