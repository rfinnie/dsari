# Schedule Format

dsari's scheduler supports the standard 5-item [cron syntax](https://en.wikipedia.org/wiki/Cron):

     * * * * *
     │ │ │ │ └─ Day of week [0-7] (Sunday is 0 or 7)
     │ │ │ └───── Month [1-12]
     │ │ └───────── Day of month [1-31]
     │ └───────────── Hour [0-23]
     └───────────────── Minute [0-59]

In addition, dsari supports Jenkins' "H" hash syntax additions, which helps spread job runs evenly.
Since this is a hash (based on the job name) and not a randomizer, the translated hashed value for each job remains the same each time.

For example, both "job1" and "job2" may have the hourly schedule `H * * * *`.
On "job1", this may hash to `27 * * * *`, while "job2" may hash to `46 * * * *`.

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
