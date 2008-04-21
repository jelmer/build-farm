#!/usr/bin/perl

use FindBin qw($RealBin);

use lib "$RealBin/..";
use lib "$RealBin/../web";

use Test::More tests => 6;
use strict;
use hostdb;

# make sure that provisioning adds the right table.
my $db = new hostdb("foo.sqlite");
ok($db->provision());
is_deeply([], $db->{dbh}->selectall_arrayref("SELECT * FROM host"));

ok($db->createhost("gwalcmai", "vax", "jelmer", "jelmer\@example.com", "geheim", "Yo! Please put me on the buildfarm"));

is_deeply([["gwalcmai"]], $db->{dbh}->selectall_arrayref("SELECT name FROM host"));

ok($db->deletehost("gwalcmai"));
is_deeply([], $db->{dbh}->selectall_arrayref("SELECT name FROM host"));

1;