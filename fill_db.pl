#!/usr/bin/perl
# Write sqlite entries for test reports in the build farm
# Copyright (C) 2007 Jelmer Vernooij <jelmer@samba.org>
# Published under the GNU GPL

use FindBin qw($RealBin $Script);
use lib "$RealBin/web";
use DBI;
use Digest::SHA1 qw(sha1_hex);
use strict;
use util;
use File::stat;
use Getopt::Long;
use hostdb;

my $opt_help = 0;
my $opt_verbose = 0;

my $result = GetOptions('help|h|?' => \$opt_help,
                        'verbose|v' => sub { $opt_verbose++; });

exit(1) unless ($result);

if ($opt_help) {
	print "$Script [OPTIONS] [LOGFILE...]\n";
	print "Options:\n";
	print " --help         This help message\n";
	print " --verbose      Be verbose\n";
	exit;
}

my $hostdb = new hostdb("hostdb.sqlite");

my $dbh = $hostdb->{dbh};

foreach my $logfn (@ARGV) {
	if (not -f $logfn) {
		warn("Unable to open $logfn: $!");
		next;
	}

	if ($opt_verbose >= 2) {
		print "Processing $logfn...\n";
	}

	my $stat = stat($logfn);

	my ($tree, $host, $compiler) = ($logfn =~ /build\.([^.]+)\.([^.]+)\.([^.]+)\.log$/);

	my $st = $dbh->prepare("SELECT * FROM build WHERE age >= ? AND tree = ? AND host = ? AND compiler = ?");

	$st->execute($stat->mtime, $tree, $host, $compiler) or die("Unable to check for existing build data");

	# Don't bother if we've already processed this file
	my $relevant_rows = $st->fetchall_arrayref();

	next if ($#$relevant_rows > -1);

	my $sha1 = Digest::SHA1->new;
	my $data = "";
	open(LOG, "<$logfn") or die("Unable to open $logfn: $!");
	while (<LOG>) { $data .= $_; }
	close(LOG);
	
	# Don't bother with empty logs, they have no meaning (and would all share the same checksum)
	next if ($data eq "");

	my $checksum = sha1_hex($data);
	if ($dbh->selectrow_array("SELECT * FROM build WHERE checksum = '$checksum'")) {
		$dbh->do("UPDATE BUILD SET age = ? WHERE checksum = ?", undef, 
			 	($stat->mtime, $checksum));
	}
	if ($opt_verbose) { print "$logfn\n"; }

	my ($rev) = ($data =~ /BUILD REVISION: ([^\n]+)/);
	$st = $dbh->prepare("INSERT INTO build (tree, revision, host, compiler, checksum, age) VALUES (?, ?, ?, ?, ?, ?)");
	$st->execute($tree, $rev, $host, $compiler, $checksum, $stat->mtime);
	my $build = $dbh->func('last_insert_rowid');

	$st = $dbh->prepare("INSERT INTO test_run (build, test, result, output) VALUES ($build, ?, ?, ?)");

	while ($data =~ /--==--==--==--==--==--==--==--==--==--==--.*?
	Running\ test\ ([\w\-=,_:\ \/.&;]+).*?
	--==--==--==--==--==--==--==--==--==--==--
	(.*?)
	==========================================.*?
	TEST\ (FAILED|PASSED|SKIPPED):.*?
	==========================================\s+
	/sxg) {
		# Note: output is discarded ($2)
		$st->execute($1, $3, undef);
	}

	$st = $dbh->prepare("INSERT INTO build_stage_run (output, build, action, result, num) VALUES (?, $build, ?, ?, ?);");

	my $order = 0;
	while ($data =~ /(.*?)?ACTION (FAILED|PASSED): ([^\n]+)/sg) {
		# Note: output is discarded ($1)
		$st->execute(undef, $3, $2, $order);
		$order++;
	}
	$st->finish();
}
