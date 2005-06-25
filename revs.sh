#!/bin/sh

cd data || exit 1

mkdir -p oldrevs

for f in *.log; do
    rev=`cat $f | egrep ^BUILD.REVISION | awk '{print $3}'`
    test -z "$rev" && continue;

    base=`basename $f .log`
    log_revname="oldrevs/$base-$rev.log"
    err_revname="oldrevs/$base-$rev.err"
    test -r $log_revname && continue;

    ln -f $base.log $log_revname
    ln -f $base.err $err_revname
done

# delete really old ones
find oldrevs -type f -mtime +14 | xargs rm -f
