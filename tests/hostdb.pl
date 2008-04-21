#!/usr/bin/perl
# Samba.org buildfarm
# Copyright (C) 2008 Andrew Bartlett <abartlet@samba.org>
# Copyright (C) 2008 Jelmer Vernooij <jelmer@samba.org>
#   
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#   
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#   
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


use FindBin qw($RealBin);

use lib "$RealBin/..";
use lib "$RealBin/../web";

use Test::More tests => 15;
use strict;
use hostdb;

# make sure that provisioning adds the right table.
my $db = new hostdb("dbname=:memory:");
ok($db->provision());
is_deeply([], $db->{dbh}->selectall_arrayref("SELECT * FROM host"));

ok($db->createhost("gwalcmai", "vax", "jelmer", "jelmer\@example.com", "geheim", "Yo! Please put me on the buildfarm"));

is_deeply([["gwalcmai"]], $db->{dbh}->selectall_arrayref("SELECT name FROM host"));

my $expected_host = { name => "gwalcmai", owner => "jelmer", owner_email => "jelmer\@example.com", 
             platform => "vax", permission => 'Yo! Please put me on the buildfarm', fqdn => undef,
             password => "geheim", ssh_access => undef };

is_deeply([$expected_host], $db->hosts());

is_deeply($expected_host, $db->host("gwalcmai"));

is(undef, $db->host("foo"));

is("gwalcmai: vax\n", $db->create_hosts_list());

is("# rsyncd.secrets file\n" . 
   "# automatically generated by textfiles.pl. DO NOT EDIT!\n\n" .
   "# gwalcmai, owner: jelmer <jelmer\@example.com>\n" . 
   "gwalcmai:geheim\n\n", $db->create_rsync_secrets());

ok($db->update_platform("gwalcmai", "s390")); 

$expected_host->{platform} = "s390";

is_deeply($expected_host, $db->host("gwalcmai"));

ok($db->update_owner("gwalcmai", "Andrew", "abartlet\@example.com"));

$expected_host->{owner} = "Andrew";
$expected_host->{owner_email} = "abartlet\@example.com";

is_deeply($expected_host, $db->host("gwalcmai"));

ok($db->deletehost("gwalcmai"));
is_deeply([], $db->{dbh}->selectall_arrayref("SELECT name FROM host"));

1;