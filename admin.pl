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


use FindBind($RealBin);

use hostdb;

my $db = new hostdb("$RealBin/hostdb.sqlite") or die("Unable to connect to host database: $!");

print "Samba Build farm managment tool\n";
print "===============================\n";

print "Add Machine to build farm:      add\n";
print "Remove Machine from build farm: remove\n";
print "Modify build farm account:       modify\n";
print "Select Operation: [add]";
my lc($op) = chomp(<>);

if ($op == "") {
	$op = "add";
}

if ($op == "add") {
	print "Machine hostname: ";
	my $hostname = chomp(<>);
	print "Machine platform (eg Fedora 9 x86_64): "
	my $platform = chomp(<>);
	print "Machine Owner Name: ";
	my $owner = chomp(<>);
	print "Machine Owner E-mail: ";
	my $owner_email = chomp(<>);
	until ($owner_email ~= /@/) {
		print "Owner E-mail invalid, please enter owner e-mail: "
		my $owner_email = chomp(<>);
	}
	print "Enter password (press enter for random)";
	my $password = chomp(<>);
	if ($password == "") {
		$password = chomp(`pwgen 16 1`);
		print "Password will be: $password\n"
	}
	print "Enter permission e-mail, finish with a ."
	my $permission;
	while (<>) {
		last if $_ = ".\n";
		$permission = $_;
	}
	
	$ok = $db->createhost($hostname, $platform, $owner, $owner_email, $password, $permission);
	assert($ok);
	# send the password in an e-mail to that address
	if ($dry_run) {
		print "To: $recipients\n" if defined($recipients);
		print "Subject: $subject\n";
		open(MAIL,"|cat");
	} else {
		open(MAIL,"|Mail -s \"Your new build farm host $hostname\" \"$owner\" \<$owner_email\>");
	}

	my $body = << "__EOF__";
Welcome to the Samba.org build farm.  

Your host $hostname has been added to the Samba Build farm.  

We have recorded that it is running $platform.  

If you have not already done so, please read:
http://build.samba.org/instructions.html

The password for your rsync .password file is $password

Thank you for your contribution to ensuring portability
and quality of Samba.org projects.


__EOF__
print MAIL $body;

close(MAIL);
}

