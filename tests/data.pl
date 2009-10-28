#!/usr/bin/perl

use FindBin qw($RealBin);

use lib "$RealBin/..";
use lib "$RealBin/../web";

use Test::More tests => 4;
use strict;
use warnings;

use data;

is(new data("somedirthatdoesn'texist"), undef);

mkdir("tmpdir");
mkdir("tmpdir/data");
mkdir("tmpdir/cache");
mkdir("tmpdir/web");
mkdir("tmpdir/lcov");
mkdir("tmpdir/lcov/data");
my $x = new data("tmpdir");
ok($x);

is($x->build_fname("mytree", "myhost", "cc", undef), "tmpdir/data/upload/build.mytree.myhost.cc");
is($x->build_fname("mytree", "myhost", "cc", 123), "tmpdir/data/oldrevs/build.mytree.myhost.cc-123");

rmdir("tmpdata");

1;
