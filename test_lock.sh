#!/bin/bash

host=`hostname`

. build_test.fns

rm -f test.lck

echo testing plain
lock_file test.lck || exit 1
unlock_file test.lck || exit 1

echo testing nesting
lock_file test.lck || exit 1
lock_file test.lck || exit 1
unlock_file test.lck || exit 1
unlock_file test.lck || exit 1

echo testing machine
echo foobar:1 > test.lck
lock_file test.lck && exit 1
rm -f test.lck

echo testing stale
echo $host:1111111 > test.lck
lock_file test.lck || exit 1
rm -f test.lck

echo OK
exit 0
