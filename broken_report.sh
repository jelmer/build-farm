#!/bin/sh
# This shell script produces an email comparing current broken-ness results
# to that of the last run of this script
#
# Copyright (C) Vance Lankhaar  <vance@samba.org>      2005
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#   
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#   
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.


# exit immediately on failure
set -e

# fail on attempting to use unassigned variable
set -u

# clean up environment a little
PATH="/usr/local/bin:/usr/bin:/bin"
IFS=" 	
"


BASEDIR="/home/build/master"
RESULT_CACHE="$BASEDIR/cache/broken_results.txt"
RESULT_URL="http://build.samba.org/?function=Text_Summary"
FULL_RESULT_URL="http://build.samba.org/"

# split into two parts to obfuscate from spam engines
RESULT_EMAIL_USER="vance"
RESULT_EMAIL_DOMAIN="samba.org"

##################################################
# get the broken report from the build farm
function get_results {
    
    rm -f "$RESULT_CACHE"

    wget --output-file="$RESULT_CACHE".log \
	 --output-document="$RESULT_CACHE" \
         "$RESULT_URL"

    if [ $? -ne 0 ]; then
	echo "Could not retrieve results:" >&2
	cat "$RESULT_CACHE".log >&2
	return 1;
    else
	rm -rf "$RESULT_CACHE".log
    fi
}

##################################################
# compare the results of build 
function compare_results {

    if [ ! -e "$RESULT_CACHE" ]; then
	echo "Could not locate currrent results. $RESULT_CACHE not found" >&2
	return 1
    fi

    if [ ! -e "$RESULT_CACHE".old ]; then
	echo "Could not locate old results. $RESULT_CACHE.old not found" >&2
	return 1
    fi
    
    diff -u "$RESULT_CACHE".old "$RESULT_CACHE" >> "$RESULT_CACHE".report || true
    
    return 0
}

##################################################
# send report to the above-set email address
function send_report {

    if [ ! -e "$RESULT_CACHE".report ]; then
	echo "Results ($RESULT_CACHE.report) not found" >&2
	return 1
    fi

    subject=$1
    if [ x"$subject" = x ]; then 
	subject="Build Farm Status"
    fi

    mail -s "$subject" "$RESULT_EMAIL_USER"@"$RESULT_EMAIL_DOMAIN" < "$RESULT_CACHE".report
}
    

##################################################
# prepares the report, including subject and "blurb"
rm -f "$RESULT_CACHE".report "$RESULT_CACHE".old

if [ -e "$RESULT_CACHE" ]; then
    mv -f "$RESULT_CACHE" "$RESULT_CACHE".old
else 
    # get results if they don't exist
    get_results
    exit $?
fi
    
get_results

if [ $? -ne 0 ]; then
    echo "Failed to get the results. Bailing." >&2
	
    # remove any new results, as they're almost certainly foul
    rm -f "$RESULT_CACHE"
    mv -f "$RESULT_CACHE".old "$RESULT_CACHE"

    exit 1
fi
    

(
    # set report subject to show updated time
    echo "URL: $FULL_RESULT_URL"
    echo
) > "$RESULT_CACHE".report

compare_results

if [ $? -ne 0 ]; then
    echo "Failed to compare results. Bailing." >&2

    exit 1
fi

subject=$(head -n 1 "$RESULT_CACHE")
send_report "$subject"

