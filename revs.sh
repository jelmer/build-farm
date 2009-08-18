#!/bin/bash

export PATH=$PATH:/usr/local/bin

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

alist=""

for f in `find . -maxdepth 1 -type f -name "*.log" -links 1`; do
    rev=`cat $f | egrep ^BUILD.REVISION | awk '{print $3}' | head -1`
    test -z "$rev" && rev=0;

    base=`basename $f .log`
    # possibly mail the culprits if the build broke
    ../analyse.pl $base.log
done

