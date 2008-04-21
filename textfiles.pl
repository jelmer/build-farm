#!/usr/bin/perl

use FindBind($RealBin);

use hostdb;

my $db = new hostdb("$RealBin/hostdb.sqlite") or die("Unable to connect to host database: $!");

$db->create_rsync_secrets("rsyncd.secrets");

$db->create_hosts_list("web/host.list");

1;