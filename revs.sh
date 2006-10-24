#!/bin/sh

ulimit -v 300000
ulimit -m 300000

if [ $# > 0 ]; then
    if [ x"$1" = x"-h" ] || [ x"$1" = x"--help" ]; then
	echo "Usage: revs.sh"
	echo
	echo "Maintains the previous revision information used on the build"
	echo "farm, as well as removing any stale build data."
	exit 1
    fi
fi

cd data || exit 1

mkdir -p oldrevs

for f in `find . -maxdepth 1 -type f -name "*.log" -links 1`; do
    rev=`cat $f | egrep ^BUILD.REVISION | awk '{print $3}' | head -1`
    test -z "$rev" && rev=0;

    base=`basename $f .log`
    log_revname="oldrevs/$base-$rev.log"
    err_revname="oldrevs/$base-$rev.err"

    rm -f $log_revname $err_revname
    ln -f $base.log $log_revname
    ln -f $base.err $err_revname

    # possibly mail the culprits if the build broke
    ../analyse.pl $base.log
done

# delete old ones that are not used any more
find oldrevs -type f -mtime +4 -links 1 | xargs rm -f

# delete any really old data
find . -type f -mtime +120 | xargs rm -f

# delete old cache data
find ../cache -type f -name "build.*" -mtime +1 | xargs rm -f

# delete partially uploaded files (crashed rsync)
find . -type f -mtime +2 -name ".build.*" | xargs rm -f

