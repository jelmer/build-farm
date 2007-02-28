#!/usr/bin/perl

use FindBin qw($RealBin);

use lib "$RealBin/..";
use lib "$RealBin/../web";

use Test::More tests => 4;
use strict;
use warnings;

use data;

is(new data("somedirthatdoesn'texist"), undef);

mkdir("tmpdata");
my $x = new data("tmpdata");
ok($x);

is($x->build_fname("mytree", "myhost", "cc", undef), "tmpdata/build.mytree.myhost.cc");
is($x->build_fname("mytree", "myhost", "cc", 123), "tmpdata/oldrevs/build.mytree.myhost.cc-123");

rmdir("tmpdata");

1;
