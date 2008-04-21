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

use hostdb;
use warnings;
use strict;

my $db = new hostdb("$RealBin/hostdb.sqlite") or die("Unable to connect to host database: $!");

open(RSYNC_SECRETS, ">../rsyncd.secrets.new") or die("Unable to open rsyncd.secrets file: $!");
print RSYNC_SECRETS $db->create_rsync_secrets();
close(RSYNC_SECRETS);

rename("../rsyncd.secrets.new", "../rsyncd.secrets");

open(HOSTS, ">web/host.list.new") or die("Unable to open hosts file: $!");
print HOSTS $db->create_hosts_list();
close(HOSTS);

rename("web/host.list.new", "web/host.list");

1;