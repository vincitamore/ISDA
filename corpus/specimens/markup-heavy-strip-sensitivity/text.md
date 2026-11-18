---
title: potting-bench CLI reference
version: 0.4.2
status: draft
---

# potting-bench — command reference

`potting-bench` schedules seed trays across a shared germination rack. This page lists
every flag the `plan` and `rotate` verbs accept. Values shown are the defaults.

## potting-bench plan

Builds a fourteen-day tray layout from the seed manifest.

| Flag | Type | Default | Meaning |
|------|------|---------|---------|
| `--manifest` | path | `trays.toml` | Seed manifest to read |
| `--days` | int | `14` | Planning horizon in days |
| `--rack-rows` | int | `6` | Rows available on the rack |
| `--min-gap` | int | `1` | Empty cells kept between species |
| `--strict` | bool | `false` | Refuse layouts that split a species |
| `--format` | enum | `table` | One of `table`, `json`, `ics` |

Example — plan a ten-day layout and emit JSON:

```bash
potting-bench plan --manifest spring.toml --days 10 --format json > layout.json
```

The exit code is `0` for a complete layout, `3` for a layout with orphaned trays, and
`64` for a malformed manifest. A partial layout is still written on exit `3`.

## potting-bench rotate

Advances the rack by one day and reports which trays move.

```bash
potting-bench rotate --apply     # mutate the rack state file
potting-bench rotate             # dry-run: print moves, change nothing
```

| Flag | Type | Default | Meaning |
|------|------|---------|---------|
| `--apply` | bool | `false` | Write the new rack state |
| `--state` | path | `rack.json` | Rack state file |
| `--quiet` | bool | `false` | Suppress the move table |

Moves are listed oldest-tray-first. A tray that would exit the rack before its
germination window closes is flagged `EARLY` and never moved by `--apply`; resolve it
by re-running `plan` with a longer horizon or by clearing the blocking row. See the
[germination notes](notes/germination.md) for species-specific windows.
