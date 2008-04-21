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

my $db = new hostdb("$RealBin/hostdb.sqlite") or die("Unable to connect to host database: $!");
my $dry_run = true;

print "Samba Build farm managment tool\n";
print "===============================\n";

my $op;

if ($#ARGV > -1) {
	$op = shift(@ARGV);
} else {
	print "Initialize host database:       init\n";
	print "Add Machine to build farm:      add\n";
	print "Remove Machine from build farm: remove\n";
	print "Modify build farm account:      modify\n";
	print "Select Operation: [add]";

	$op = lc(<STDIN>);
	chomp($op);

	if ($op eq "") {
		$op = "add";
	}
}

if ($op eq "remove") {
	print "Please enter hostname to delete: \n";
	my $hostname = <>;
	chomp($hostname);
	$db->deletehost($hostname) or die("Unable to create host $hostname");
} elsif ($op eq "modify") {
	print "Please enter hostname to modify: \n";
	my $hostname = <>;
	chomp($hostname);
	my $host = $db->host($hostname);
	print "Owner: $host->{owner} <$host->{owner_email}>\n";
	print "Platform: $host->{platform}\n";
	print "\n";
	print "Modify owner or platform: [platform]:";
	my $mod_op = <>;
	chomp($mod_op);
	if ($mod_op eq "") {
		$mod_op = "platform";
	}
	if ($mod_op eq "platform") {
		print "Enter new platform: ";
		my $platform = <>;
		chomp($platform);
		$db->update_platform($hostname, $platform) or die "Unable to update platform";
	} elsif ($mod_op eq "owner") {
		print "Enter new owner's name: ";
		my $owner = <>;
		chomp($owner);
		print "Enter new owner's e-mail address: ";
		my $owner_email = <>;
		chomp($owner_email);
		$db->update_platform($hostname, $owner, $owner_email) or die "Unable to update owner";
		
	}	
} elsif ($op eq "add") {
	print "Machine hostname: ";
	my $hostname = <>;
	chomp($hostname);
	print "Machine platform (eg Fedora 9 x86_64): ";
	my $platform = <>;
	chomp($platform);
	print "Machine Owner Name: ";
	my $owner = <>;
	chomp($owner);
	print "Machine Owner E-mail: ";
	my $owner_email = <>;
	chomp($owner_email);
	print "Enter password (press enter for random)";
	my $password = <>;
	chomp($password);
	if ($password eq "") {
		$password = `pwgen 16 1`;
		chomp($password);
		print "Password will be: $password\n";
	}
	print "Enter permission e-mail, finish with a .";
	my $permission;
	while (<>) {
		last if $_ eq ".\n";
		$permission = $_;
	}
	
	$db->createhost($hostname, $platform, $owner, $owner_email, $password, $permission) or die("Unable to create host $hostname");
	
	# send the password in an e-mail to that address
	if ($dry_run) {
		print "To: $recipients\n" if defined($recipients);
		print "Subject: $subject\n";
		open(MAIL,"|cat");
	} else {
		open(MAIL,"|Mail -s \"Your new build farm host $hostname\" \"$owner \<$owner_email\>\" -b build\@samba.org");
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
} elsif ($op eq "init") {
	$db->provision();
	print "Host database initialized successfully.\n";
} else {
	die("Unknown command $op");
}

1;