#!/usr/bin/perl

use FindBin qw($RealBin);

use lib "$RealBin/..";
use lib "$RealBin/../web";

use Test::More tests => 2;
use strict;
use hostdb;

# make sure that provisioning adds the right table.
my $db = new hostdb("foo.sqlite");
ok($db->provision());
is_deeply([], $db->{dbh}->selectall_arrayref("SELECT * FROM host"));

1;