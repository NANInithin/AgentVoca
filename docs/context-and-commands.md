# Context, Commands & Adaptive Vocabulary

AgentVoca v2 adds three "intelligence" features on top of the v1 pipeline. All
three are **off by default** and each is an independent config flag, so you can
enable exactly what you want. With everything off, behavior is identical to v1.

- [Context engine](#context-engine) — pick a cleanup style based on the active app.
- [Voice commands](#voice-commands) — say "new paragraph" instead of typing it.
- [Adaptive vocabulary](#adaptive-vocabulary) — the app learns your corrections.

---

## Context engine

The context engine looks at the **foreground application** and chooses a cleanup
style for that app — `technical` while you dictate into VS Code or a terminal,
`professional` while you dictate into your mail client, and your global style
everywhere else.

```yaml
context:
  enabled: true
  profiles:
    "Code*": technical      # VS Code (Code.exe / Code)
    "*terminal*": technical
    "*outlook*": professional
    "*": standard           # fallback for everything else
```

### How matching works

- Keys are matched against the active app/window name with **glob patterns**
  (`fnmatch`): `Code*` matches `Code.exe`, `*terminal*` matches anything with
  "terminal" in the name.
- An exact match wins over a glob match.
- The special key `"*"` is the fallback used when nothing else matches.
- Values must be valid styles: `raw`, `light`, `standard`, `technical`,
  `professional`, `custom`. An unknown style is ignored with a warning.

### It is advisory only

If app detection fails (permissions, an unusual shell, an unsupported platform),
the engine returns no style and the orchestrator falls back to your global
`cleanup.style`. **Dictation is never blocked by context resolution.**

### Privacy

By default the engine reads only the **application name and window title** —
nothing else. Reading screen or clipboard content is gated behind explicit
opt-in and is **logged each time it is used**:

```yaml
context:
  enabled: true
  read_screen: false      # off by default
  read_clipboard: false   # off by default
```

A default install reads nothing beyond the app name. Turn these on only if you
understand and want that trade-off.

---

## Voice commands

When enabled, a small set of **high-precision** editing phrases are recognized
and acted on instead of being typed literally.

```yaml
commands:
  enabled: true
```

### Built-in commands

| Say | Action |
|---|---|
| "new line" | insert a single newline (`\n`) |
| "new paragraph" | insert a blank line (`\n\n`) |
| "scratch that" | undo the last insertion |
| "undo that" | undo the last insertion |
| "capitalize that" | re-insert the last text capitalized |

### Precision over recall

Commands match only when the phrase is at the **start of the utterance** (a
leading or standalone command). Anything ambiguous is treated as ordinary
dictation, so a sentence that merely *contains* the words "new line" mid-phrase
is typed normally rather than swallowed.

### Customizing phrases

Add or override phrase → action mappings. Valid actions are `newline`,
`paragraph`, `delete_last`, `undo`, `capitalize`.

```yaml
commands:
  enabled: true
  phrases:
    "next line": newline
    "remove that": delete_last
```

---

## Adaptive vocabulary

The app can **learn your corrections**. When you undo an inserted word and then
re-dictate it differently, that `wrong → right` pair is recorded. Once you make
the same correction `promote_threshold` times, the mapping is promoted into your
live vocabulary and applied automatically from then on.

```yaml
adaptive:
  enabled: true
  promote_threshold: 3                       # corrections before auto-applying (min 2)
  learned_vocab_path: ~/.agentvoca/learned_vocab.txt   # where promotions persist
```

### How it works

1. You dictate, the app inserts `nini`.
2. You undo it and re-dictate; the app inserts `NANI`.
3. The pair `nini → NANI` is recorded (a `CorrectionLearnedEvent` is emitted).
4. After `promote_threshold` occurrences, `nini → NANI` is added to your
   vocabulary and saved to `learned_vocab.txt`.
5. From then on, `nini` is automatically rewritten to `NANI` before insertion.

The learned file is a plain text file you can inspect or edit:

```
# one term per line, or a mapping with " -> "
nini -> NANI
```

This is deterministic substitution (no ML), reusing the same vocabulary path as
your manually configured terms. Disable it any time by setting
`adaptive.enabled: false`.

---

## Putting it together

A "smart developer" config might look like:

```yaml
asr:
  provider: faster_whisper
  model: large-v3
  streaming: true
  streaming_model: base.en

cleanup:
  provider: rules
  style: standard

context:
  enabled: true
  profiles:
    "Code*": technical
    "*terminal*": technical
    "*": standard

commands:
  enabled: true

adaptive:
  enabled: true
  promote_threshold: 3
```

See [docs/config-reference.md](config-reference.md) for every key and default,
and [docs/performance.md](performance.md) for the streaming and warm-up knobs.
