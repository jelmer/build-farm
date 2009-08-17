#!/bin/sh

sqlite3 `dirname $0`/hostdb.sqlite 'VACUUM;'
cd `dirname $0` && exec ./mail-dead-hosts.pl
