#!/bin/bash
# Read-only: list Calendar.app events for the next N days (arg1, default 14),
# from every calendar except the ones named in OPS_EXCLUDE_CALENDARS (comma
# separated, see ops-pack.env.example). One line per event, sorted by start:
# YYYY-MM-DD HH:MM | <calendar> | <summary> | <location or ->
# Uses a date-bounded "whose" clause so Calendar.app does not have to walk every event.

DAYS="${1:-14}"
EXCLUDE="${OPS_EXCLUDE_CALENDARS:-Birthdays,Siri Suggestions,Holidays}"

RAW=$(osascript - "$DAYS" "$EXCLUDE" <<'APPLESCRIPT'
on run argv
    set numDays to (item 1 of argv) as integer
    set excludeCsv to (item 2 of argv)
    set excludeNames to my splitCsv(excludeCsv)
    set d1 to current date
    set time of d1 to 0
    set d2 to d1 + numDays * days
    set out to ""
    tell application "Calendar"
        repeat with cal in calendars
            set calName to name of cal
            if excludeNames does not contain calName then
                set theEvents to (every event of cal whose start date >= d1 and start date <= d2)
                repeat with ev in theEvents
                    set evStart to start date of ev
                    set evSummary to summary of ev
                    try
                        set evLoc to location of ev
                        if evLoc is missing value or evLoc is "" then set evLoc to "-"
                    on error
                        set evLoc to "-"
                    end try
                    set dateStr to (year of evStart as string) & "-" & my pad2(month of evStart as integer) & "-" & my pad2(day of evStart) & " " & my pad2(hours of evStart) & ":" & my pad2(minutes of evStart)
                    set out to out & dateStr & " | " & calName & " | " & evSummary & " | " & evLoc & "\n"
                end repeat
            end if
        end repeat
    end tell
    return out
end run

on pad2(n)
    set n to n as integer
    if n < 10 then
        return "0" & n
    else
        return n as string
    end if
end pad2

on splitCsv(theText)
    set oldDelims to text item delimiters
    set text item delimiters to ","
    set theList to text items of theText
    set text item delimiters to oldDelims
    return theList
end splitCsv
APPLESCRIPT
)

if [ -z "$RAW" ]; then
    echo "no events"
else
    echo "$RAW" | sort
fi
