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
use POSIX qw(strftime);
use hostdb;
use Mail::Send;
use warnings;
use strict;

my $db = new hostdb("$RealBin/hostdb.sqlite") or die("Unable to connect to host database: $!");
my $dry_run = 0;

my $hosts = $db->dead_hosts(7 * 86400);
foreach (@$hosts) {
	
	my ($fh, $msg);
	
	$db->sent_dead_mail($_->{host}) or die "Could not update 'last dead mail sent' record for $_->{host}";

	# send the password in an e-mail to that address
	my $subject = "Your build farm host $_->{host} appears dead";
	if ($dry_run) {
		print "To: $_->{owner} <$_->{owner_email}>\n";
		print "Subject: $subject\n";
		open(MAIL,"|cat");
	} else {
		$msg = new Mail::Send(Subject=>$subject, To=>"$_->{owner} <$_->{owner_email}>", Bcc=>"build\@samba.org");
		$fh = $msg->open; 
	}

        my $last_update = strftime ("%a %b %e %H:%M:%S %Y", gmtime($_->{last_update}));

	my $body = << "__EOF__";	
Your host $_->{host} has been part of the Samba Build farm, hosted
at http://build.samba.org.

Sadly however we have not heard from it since $last_update.

Could you see if something has changed recently, and examine the logs
(typically in ~build/build_farm/build.log and ~build/cron.err) to see
why we have not heard from your host?

If you no longer wish your host to participate in the Samba Build
Farm, then please let us know so we can remove its records.

You can see the summary for your host at:
http://build.samba.org/?function=View+Host;host=$_->{host}

Thanks,

The Build Farm administration team.

__EOF__

	if ($dry_run) {
		print MAIL $body;

		close(MAIL);
	} else {
		print $fh "$body";
		$fh->close;
	}
}

1;
