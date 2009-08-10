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
use data;

my $opt_help = 0;
my $opt_verbose = 0;

my $result = GetOptions('help|h|?' => \$opt_help,
                        'verbose|v' => sub { $opt_verbose++; });

exit(1) unless ($result);

if ($opt_help) {
	print "$Script [OPTIONS]\n";
	print "Options:\n";
	print " --help         This help message\n";
	print " --verbose      Be verbose\n";
	exit;
}

my $hostdb = new hostdb("hostdb.sqlite");

my $dbh = $hostdb->{dbh};

my $db = new data($RealBin);
my @compilers = @{$db->{compilers}};
my @hosts = @{$db->{hosts_list}};
my %trees = %{$db->{trees}};


foreach my $host (@hosts) {
    foreach my $tree (keys %trees) {
	foreach my $compiler (@compilers) {
	    if ($opt_verbose >= 2) {
		print "Looking for a log file for $host $compiler $tree...\n";
	    }

	    # By reading the log file this way, using only the list of
	    # hosts, trees and compilers as input, we ensure we
	    # control the inputs
	    my $log = $db->read_log($tree, $host, $compiler);
	    if (not $log) {
		next;
	    }

	    # This does double-work, but we need it to be able to stat the file
	    my $logfn = $db->build_fname($tree, $host, $compiler);
	    my $stat = stat($logfn . ".log");
    
	    if ($opt_verbose >= 2) {
		print "Processing $logfn...\n";
	    }
	    
	    my $st = $dbh->prepare("SELECT * FROM build WHERE age >= ? AND tree = ? AND host = ? AND compiler = ?");
	    
	    $st->execute($stat->mtime, $tree, $host, $compiler) or die("Unable to check for existing build data");
	    
	    # Don't bother if we've already processed this file
	    my $relevant_rows = $st->fetchall_arrayref();
	    
	    next if ($#$relevant_rows > -1);
	    
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
		next;
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
    }
}
