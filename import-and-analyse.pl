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
my $dry_run = 0;
my $result = GetOptions('help|h|?' => \$opt_help,
                        'dry-run|n' => sub { $dry_run++; },
                        'verbose|v' => sub { $opt_verbose++; });

exit(1) unless ($result);

if ($opt_help) {
	print "$Script [OPTIONS]\n";
	print "Options:\n";
	print " --help         This help message\n";
	print " --verbose      Be verbose\n";
	print " --dry-run      Dry run\n";
	exit;

	print <<EOU;

Script to parse build farm log files from the data directory, import
them into the database, add links to the oldrevs/ directory and send
some mail chastising the possible culprits when the build fails, based
on recent commits.

-n  Will cause the script to send output to stdout instead of
    to sendmail.
EOU
	exit(1);
}

# we open readonly here as only apache(www-run) has write access
my $db = new data($RealBin, 1);

my $hostdb = new hostdb("$RealBin/hostdb.sqlite");

my $dbh = $hostdb->{dbh};

my @compilers = @{$db->{compilers}};
my @hosts = @{$hostdb->{hosts}};
my %trees = %{$db->{trees}};

sub check_and_send_mails($$$$$) 
{
    my ($tree, $host, $compiler, $cur, $old) = @_;
    my $t = $trees{$tree};
    
    printf("rev=$cur->{rev} status=$cur->{string}\n") if $dry_run;
    
    printf("old rev=$old->{rev} status=$old->{string}\n") if $dry_run;
    
    my $cmp = $db->status_cmp($old, $cur);
#printf("cmp: $cmp\n");
    
    if ($cmp <= 0) {
	printf("the build didn't get worse ($cmp)\n") if $dry_run;
	return unless $dry_run;
    }
    
    my $log = get_log($host, $tree, $compiler, $cur, $old);
    if (not defined($log)) {
	printf("no log\n") if $dry_run;
	return;
    }
    
    my $recipients = undef;
    $recipients = join(",", keys %{$log->{recipients}}) if defined($log->{recipients});
    
    my $subject = "BUILD of $tree:$t->{branch} BROKEN on $host with $compiler AT REVISION $cur->{rev}";
    
# send the nastygram
    if ($dry_run) {
	print "To: $recipients\n" if defined($recipients);
	print "Subject: $subject\n";
	open(MAIL,"|cat");
    } else {
	if (defined($recipients)) {
	    open(MAIL,"|Mail -a \"Content-Type: text/plain;charset=utf-8\" -s \"$subject\" $recipients");
	} else {
	    open(MAIL,"|cat >/dev/null");
	}
    }
    
    my $body = << "__EOF__";
Broken build for tree $tree on host $host with compiler $compiler

Tree $tree is $t->{scm} branch $t->{branch}.

Build status for new revision $cur->{rev} is $cur->{string}
Build status for old revision $old->{rev} was $old->{string}

See http://build.samba.org/?function=View+Build;host=$host;tree=$tree;compiler=$compiler

The build may have been broken by one of the following commits:

$log->{change_log}
__EOF__
    print MAIL $body;

    close(MAIL);
}




foreach my $host (@hosts) {
    foreach my $tree (keys %trees) {
	foreach my $compiler (@compilers) {
	    if ($opt_verbose >= 2) {
		print "Looking for a log file for $host $compiler $tree...\n";
	    }

	    # By building the log file name this way, using only the list of
	    # hosts, trees and compilers as input, we ensure we
	    # control the inputs
	    my $logfn = $db->build_fname($tree, $host, $compiler);
	    my $stat = stat($logfn . ".log");
	    next if (!$stat);
    
	    if ($opt_verbose >= 2) {
		print "Processing $logfn...\n";
	    }
	    
	    my $st = $dbh->prepare("SELECT * FROM build WHERE age >= ? AND tree = ? AND host = ? AND compiler = ?");
	    
	    $st->execute($stat->mtime, $tree, $host, $compiler) or die("Unable to check for existing build data");
	    
	    # Don't bother if we've already processed this file
	    my $relevant_rows = $st->fetchall_arrayref();
	    
	    next if ($#$relevant_rows > -1);
	    
	    # By reading the log file this way, using only the list of
	    # hosts, trees and compilers as input, we ensure we
	    # control the inputs
	    my $data = util::FileLoad($logfn.".log");

	    # Don't bother with empty logs, they have no meaning (and would all share the same checksum)
	    if (not $data or $data eq "") {
		next;
	    }

	    my $err = util::FileLoad($logfn.".err");
	    $err = "" unless defined($err);

	    $dbh->begin_work() or die "could not get transaction lock";
		
	    my $checksum = sha1_hex($data);
	    if ($dbh->selectrow_array("SELECT FROM build WHERE checksum = '$checksum'")) {
		$dbh->do("UPDATE BUILD SET age = ? WHERE checksum = ?", undef, 
			 ($stat->mtime, $checksum));
		next;
	    }
	    if ($opt_verbose) { print "$logfn\n"; }
	    
	    my ($rev) = ($data =~ /BUILD REVISION: ([^\n]+)/);
	    my $commit;
	    
	    if ($data =~ /BUILD COMMIT REVISION: (.*)/) {
		$commit = $1;
	    } else {
		$commit = $rev;
	    }
	    my $status_html = $db->build_status_from_logs($data, $err);

	    # Look up the database to find the previous status
	    $st = $dbh->prepare("SELECT status FROM build WHERE tree = '?' AND host = '?' AND compiler = '?' AND revision < '?' AND commit != '?' ORDER BY revision LIMIT 1");
	    $st->execute( $tree, $host, $compiler, $rev, $commit );

	    my $old_status_html;
	    while ( my @row = $st->fetchrow_array ) {
		$old_status_html = @row[0];
	    }


	    $st = $dbh->prepare("INSERT INTO build (tree, revision, commit, host, compiler, checksum, age, status) VALUES (?, ?, ?, ?, ?, ?, ?)");
	    $st->execute($tree, $rev, $commit, $host, $compiler, $checksum, $stat->mtime, $status_html);
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

	    $st->finish();

	    my $cur_status = $db->build_status_info_from_html($rev, $commit, $status_html);
	    my $old_status;
	    if (defined($old_status_html)) {
		$old_status = $db->build_status_info_from_html($rev, $commit, $old_status_html);
	    }
	    
	    check_and_send_mails($tree, $host, $compiler, $cur_status, $old_status);

	    if ($dry_run) {
		$dbh->cancel();
		next;
	    }

	    $dbh->commit() or die "Could not commit transaction";
	    if ($rev) {
		# If we were able to put this into the DB (ie, a
		# one-off event, so we won't repeat this), then also
		# hard-link the log files to the revision, if we know
		# it.


		# This ensures that the names under 'oldrev' are well known and well formed 
		my $log_rev = $db->build_fname($tree, $host, $compiler, $rev) . ".log";
		my $err_rev = $db->build_fname($tree, $host, $compiler, $rev) . ".err";
		unlink $log_rev;
		unlink $err_rev;
		link($logfn, $log_rev);
		link($db->build_fname($tree, $host, $compiler) . ".err", $err_rev);
	    }
	}
    }
}
