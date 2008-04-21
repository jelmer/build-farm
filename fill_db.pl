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

my $opt_help = 0;
my $opt_init = 0;

my $result = GetOptions(
	'help|h|?' => \$opt_help,
	'init' => \$opt_init);

exit(1) unless ($result);

if ($opt_help) {
	print "$Script [OPTIONS] <LOG-FILE>\n";
	print "Options:\n";
	print " --help         This help message\n";
	print " --init         (Re-)Initialize the database\n";
	exit;
}

my $dbh = DBI->connect( "dbi:SQLite:hostdb.sqlite" ) || die "Cannot connect: $DBI::errstr";

if ($opt_init) {
	$dbh->do("CREATE TABLE build ( id integer primary key autoincrement, tree text, revision text, host text, compiler text, checksum text, age int );");
	$dbh->do("CREATE TABLE test_run ( build int, test text, result text, output text);");
	$dbh->do("CREATE TABLE build_stage_run ( build int, action text, result text, output text, num int);");
}

foreach my $logfn (@ARGV) {
	if (not -f $logfn) {
		warn("Unable to open $logfn: $!");
		next;
	}

	my ($tree, $host, $compiler) = ($logfn =~ /build\.([^.]+)\.([^.]+)\.([^.]+)\.log$/);

	my $sha1 = Digest::SHA1->new;
	my $data = "";
	open(LOG, "<$logfn") or die("Unable to open $logfn: $!");
	while (<LOG>) { $data .= $_; }
	close(LOG);

	my $checksum = sha1_hex($data);
	$dbh->selectrow_array("SELECT * FROM build WHERE checksum = '$checksum'") and next;
	print "$logfn\n";

	my ($rev) = ($data =~ /BUILD REVISION: ([^\n]+)/);
	my $st = $dbh->prepare("INSERT INTO build (tree, revision, host, compiler, checksum, age) VALUES (?, ?, ?, ?, ?, ?)");
	my $stat = stat($logfn);
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
		$st->execute($1, $3, $2);
	}

	$st = $dbh->prepare("INSERT INTO build_stage_run (output, build, action, result, num) VALUES (?, $build, ?, ?, ?);");

	my $order = 0;
	while ($data =~ /(.*?)?ACTION (FAILED|PASSED): ([^\n]+)/sg) {
		$st->execute($1, $3, $2, $order);
		$order++;
	}
	$st->finish();
}
