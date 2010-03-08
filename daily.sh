#!/bin/sh

cd $HOME/master || exit 1
set -x

(
date
set -x
sqlite3 `dirname $0`/hostdb.sqlite 'VACUUM;'
cd `dirname $0` && ./mail-dead-hosts.pl

echo "deleting old file that are not used any more"
find `dirname $0`/data/oldrevs -type f -mtime +10 -links 1 -print0 | xargs -i -0 rm -f \{\}

echo "deleting any really old data"
find `dirname $0`/data -type f -mtime +120  -print0 | xargs -i -0 rm -f \{\}

echo "delete old cache data"
find `dirname $0`/cache -type f -name "build.*" -mtime +1 -print0 | xargs -i -0 rm -f \{\}

echo "delete partially uploaded files (crashed rsync)"
find `dirname $0`/data/upload -type f -mtime +2 -name ".build.*" -print0 | xargs -i -0 rm -f \{\}

) >> daily.log 2>&1
