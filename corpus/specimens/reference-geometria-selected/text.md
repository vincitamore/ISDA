# Rack Scheduler configuration reference

Settings are read from `scheduler.toml`, top of file wins on duplicate keys. Every
setting below shows its default.

## [rack]

Physical description of the germination rack.

### rows

Integer, default `6`. Rows the planner may use. Lower it to reserve bench space; the
planner never assigns above this count.

### cells_per_row

Integer, default `8`. Cells in each row. All rows are assumed equal; ragged racks need
one `[rack.override]` block per short row.

### reserved

List of cell coordinates, default empty. Cells the planner must leave empty, written as
`"row:cell"` strings.

## [watering]

When and how trays are watered.

### mode

Enum, default `"mat"`. One of `"mat"`, `"top"`, `"manual"`. Covered trays are always
excluded from `"top"` regardless of this setting.

### window

Two clock times, default `["07:00", "09:00"]`. The daily span in which watering may
run. A cycle that cannot finish inside the window is deferred, never truncated.

### skip_when_humid

Boolean, default `true`. Skip the cycle when cabinet humidity exceeds the threshold
below.

#### humidity_threshold

Integer percent, default `85`. Only read when `skip_when_humid` is true.

## [alerts]

Where problems are reported.

### channel

Enum, default `"log"`. One of `"log"`, `"email"`, `"none"`. The `"none"` channel still
writes the daily summary line.

### email

String, no default. Required when `channel = "email"`; the send fails closed at startup
if unset, not at first alert.

### quiet_hours

Two clock times, default `["21:00", "06:00"]`. Alerts raised in this span are queued and
delivered at span end, oldest first.
