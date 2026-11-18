# The night zone 4 ran for six hours

The overnight log for the fourteenth showed zone 4's valve open from 23:12 to 05:20, six
hours against a scheduled twenty minutes, and the morning bench told the same story
before anyone read a log: two trays of seedlings floating in their own cells, the mat
sodden through, and a waterline mark a centimetre up the cabinet wall. The controller
had reported a normal night. Nothing had alarmed.

The first suspicion was the valve itself, because a stuck solenoid is the boring answer
and the boring answer is usually right. But the bench test cleared it in ten minutes:
the valve seated cleanly on command, twenty cycles in a row, no hesitation warm or cold.
Whatever held it open that night had held it open on purpose.

The second suspicion was the schedule file, and this one looked promising for most of an
afternoon. A hand edit from the twelfth had left zone 4's stanza with an end time of
`5:20` where every other stanza wrote `05:20`, and the parser's documentation was silent
about unpadded hours. A malformed end time that parsed as midnight-plus-something would
explain everything. It explained nothing: the parser test read `5:20` exactly as
`05:20`, and the stanza had run correctly on the thirteenth with the same edit in place.

The actual cause surfaced by accident, in the water meter's own log rather than the
controller's. The meter recorded pressure loss at 23:11 — one minute before the valve
opened — when the misting loop on the adjacent bench kicked on for a frost warning. The
controller's watering routine reads line pressure before closing a valve, and it refuses
to close against a pressure fault, a guard written for winterised lines that must not
trap water. The frost misting held line pressure low all night; the guard held the valve
open all night; each subsystem behaved exactly as designed, and the design had never
been asked what happens when both run at once.

The fix was one line — close the valve first, then raise the fault — plus a test that
runs the misting loop and the watering schedule against the same simulated night. The
seedlings mostly recovered. The waterline mark is still on the cabinet wall, and it is
worth keeping: the system did not fail loudly, it failed politely, every component
correct and the whole thing wrong, which is the failure worth remembering when the next
guard is written.
