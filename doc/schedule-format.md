# Schedule Format

dsari's scheduler supports several scheduling formats.

## Cron Syntax

When the `croniter` Python package is installed, dsari's scheduler supports the standard 5-field [cron syntax](https://en.wikipedia.org/wiki/Cron), with an optional 6th field as seconds:

    * * * * * *
    └─│─│─│─│─│── Minute [0-59]
      └─│─│─│─│── Hour [0-23]
        └─│─│─│── Day of month [1-31]
          └─│─│── Month [1-12]
            └─│── Day of week [0-7] (Sunday is 0 or 7)
              └── Second [0-59] (optional, non-standard)

In addition, dsari supports Jenkins' "H" hash syntax additions, which helps spread job runs evenly.
Since this is a hash (based on the job name) and not a randomizer, the translated hashed value for each job remains the same each time.

For example, both "job1" and "job2" may have the hourly schedule `H * * * *`.
On "job1", this may hash to `27 * * * *`, while "job2" may hash to `46 * * * *`.

If an actual random position is desired, use "R" instead of "H".

If the 6th field (second) is not present in a definition, it is assumed to be "H" (hashed within the minute).
If "*", it will be run every second, which is probably not what you want.

Here are a few examples of the extended syntax:

    H H * * *
    # Hash on the minute and hour, running once daily.
    # Example result: 53 18 * * *
    
    H H(0-7) * * *
    # Hash on the minute, and hash between midnight and 7AM on the hour, running
    # once daily.
    # Example result: 22 6 * * *
    
    H/15 * * * *
    # Every 15 minutes, offset a hashed amount.
    # Example result: 7-59/15 * * * * (i.e. 7,22,37,52)
    
    H(30-59)/10 * * * *
    # Every 10 minutes, offset a hashed amount, but only between :30 and :59 each
    # hour.
    # Example result: 34-59/10 (i.e. 34,44,54)

    @midnight
    # Alias for: H H(0-2) * * *

    @hourly
    # Alias for: H * * * *

    @daily
    # Alias for: H H * * *

    @weekly
    # Alias for: H H * * H

    @monthly
    # Alias for: H H H * *

    @annually
    @yearly
    # Aliases for: H H H H *

## iCalendar RRULE

When the `python-dateutil` Python package is installed, dsari's scheduler supports the [iCalendar](https://tools.ietf.org/html/rfc5545) RRULE syntax.
This syntax allows for more expansive expressions than the cron syntax, though the format is complex and not as well understood by most people.

Here are a few examples:

    RRULE:FREQ=MINUTELY;INTERVAL=5
    # Every 5 minutes

    RRULE:FREQ=DAILY
    # Daily

    RRULE:FREQ=DAILY;BYDAY=MO,TH;BYHOUR=14;BYMINUTE=30
    # Each Monday and Thursday, at 14:30

    RRULE:FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1
    # The last weekday of the month

    RRULE:FREQ=HOURLY;UNTIL=20181225T080000
    # Run hourly, but do not schedule runs after Christmas morning 2018

When a position is not supplied, it is hashed according to the job name.
For example, "RRULE:FREQ=DAILY" is the same as "H H * * *", and the job will run at the same hour/minute/second each day.
For more information about job name hashing, see above.

dsari's scheduler supports nearly all RRULE properties defined by RFC 5545 (or more accurately, supported by `python-dateutil`), with the exception of COUNT.
