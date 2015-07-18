# Notifications

dsari does not support notifications directly, but with the environment variables available in a run, you can construct notifications tailored to your own situation.
For example, this script runs the desired command, then mails someone if the command fails or returns to normal.

    #!/bin/sh -e
    
    EMAIL="joe@example.com"
    
    EXIT_CODE=0
    desired_command || EXIT_CODE=$?
    
    if [ "$EXIT_CODE" != "0" ]; then
        echo "$JOB_NAME has failed ($RUN_ID)" | mail "$EMAIL"
    elif [ -n "$PREVIOUS_EXIT_CODE" ] && [ "$PREVIOUS_EXIT_CODE" != "0" ]; then
        echo "$JOB_NAME is back to normal ($RUN_ID)" | mail "$EMAIL"
    fi
    exit $EXIT_CODE
