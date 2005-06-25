#!/bin/sh

cd data || exit 1

mkdir -p oldrevs

for f in `find . -maxdepth 1 -type f -name "*.log" -links 1`; do
    rev=`cat $f | egrep ^BUILD.REVISION | awk '{print $3}'`
    test -z "$rev" && rev=0;

    base=`basename $f .log`
    log_revname="oldrevs/$base-$rev.log"
    err_revname="oldrevs/$base-$rev.err"
    test -r $log_revname && continue;

    ln -f $base.log $log_revname
    ln -f $base.err $err_revname
done

# delete really old ones
find oldrevs -type f -mtime +14 -links 1 | xargs rm -f
