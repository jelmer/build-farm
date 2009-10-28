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
use Carp;

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

my $unpacked_dir = "/home/ftp/pub/unpacked";

# we open readonly here as only apache(www-run) has write access
my $db = new data($RealBin, 1);

my $hostdb = new hostdb("$RealBin/hostdb.sqlite");

my $dbh = $hostdb->{dbh};

my @compilers = @{$db->{compilers}};
my @hosts = @{$db->{hosts_list}};
my %trees = %{$db->{trees}};

sub get_log_svn($$$$$)
{
	my ($host, $tree, $compiler, $cur, $old) = @_;
	my $firstrev = $old->{rev} + 1;
	my $cmd = "svn log --non-interactive -r $firstrev:$cur->{rev} $unpacked_dir/$tree";
	my $log = undef;

	$log->{change_log} = `$cmd` || confess "$cmd: failed";
	#print($log->{change_log});

	# get the list of possible culprits
	my $log2 = $log->{change_log};

	while ($log2 =~ /\nr\d+ \| (\w+) \|.*?line(s?)\n(.*)$/s) {
		$log->{committers}->{"$1\@samba.org"} = 1;
		$log2 = $3;
	}

	# Add a URL to the diffs for each change
	$log->{change_log} =~ s/\n(r(\d+).*)/\n$1\nhttp:\/\/build.samba.org\/?function=diff;tree=${tree};revision=$2/g;

	$log->{recipients} = $log->{committers};

	return $log;
}

sub get_log_git($$$$$)
{
	my ($host, $tree, $compiler, $cur, $old) = @_;
	my $cmd = "cd $unpacked_dir/$tree && git log --pretty=full $old->{rev}..$cur->{rev} ./";
	my $log = undef;

	$log->{change_log} = `$cmd` || confess "$cmd: failed";
	#print($log->{change_log});

	# get the list of possible culprits
	my $log2 = $log->{change_log};

	while ($log2 =~ /[\n]*Author: [^<]*<([^>]+)>\nCommit: [^<]*<([^>]+)>\n(.*)$/s) {
		my $author = $1;
		my $committer = $2;
		$log2 = $3;
		
		# handle cherry-picks from svnmirror repo
		$author =~ s/0c0555d6-39d7-0310-84fc-f1cc0bd64818/samba\.org/;
		
		# for now only send reports to samba.org addresses.
		$author = undef unless $author =~ /\@samba\.org/;
		# $committer = undef unless $committer =~ /\@samba\.org/;

		$log->{authors}->{$author} = 1 if defined($author);
		$log->{committers}->{$committer} = 1 if defined($committer);
	}

	# Add a URL to the diffs for each change
	$log->{change_log} =~ s/([\n]*commit ([0-9a-f]+))/$1\nhttp:\/\/build.samba.org\/?function=diff;tree=${tree};revision=$2/g;

	my @all = ();
	push(@all, keys %{$log->{authors}}) if defined($log->{authors});
	push(@all, keys %{$log->{committers}}) if defined($log->{committers});
	my $all = undef;
	foreach my $k (@all) {
		$all->{$k} = 1;
	}
	$log->{recipients} = $all;

	return $log;
}

sub get_log($$$$$)
{
	my ($host, $tree, $compiler, $cur, $old) = @_;
	my $treedir = "$unpacked_dir/$tree";

	if (-d "$treedir/.svn") {
		return get_log_svn($host, $tree, $compiler, $cur, $old);
	} elsif (-d "$treedir/.git") {
		return get_log_git($host, $tree, $compiler, $cur, $old);
	}

	return undef;
}

sub check_and_send_mails($$$$$) 
{
    my ($tree, $host, $compiler, $cur, $old) = @_;
    my $t = $trees{$tree};
    
    printf("rev=$cur->{rev} status=$cur->{string}\n") if $dry_run;
    
    printf("old rev=$old->{rev} status=$old->{string}\n") if $dry_run;
    
    my $cmp = $db->status_info_cmp($old, $cur);
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
	    open(MAIL,"|Mail -a \"Content-Type: text/plain;charset=utf-8\" -a \"Precedence: bulk\" -s \"$subject\" $recipients");
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
	    my $rev;
	    my $retry = 0;
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
	    
	    eval {
		my $st = $dbh->prepare("SELECT checksum FROM build WHERE age >= ? AND tree = ? AND host = ? AND compiler = ?");
	    
		$st->execute($stat->mtime, $tree, $host, $compiler);
	    
		# Don't bother if we've already processed this file
		my $relevant_rows = $st->fetchall_arrayref();
		
		$st->finish();

		if ($#$relevant_rows > -1) {
		    die "next please"; #Moves to the next record in the exception handler
		}
	    
		# By reading the log file this way, using only the list of
		# hosts, trees and compilers as input, we ensure we
		# control the inputs
		my $data = util::FileLoad($logfn.".log");
		
		# Don't bother with empty logs, they have no meaning (and would all share the same checksum)
		if (not $data or $data eq "") {
		    die "next please"; #Moves to the next record in the exception handler
		}
		
		my $err = util::FileLoad($logfn.".err");
		$err = "" unless defined($err);
		
		my $checksum = sha1_hex($data);
		if ($dbh->selectrow_array("SELECT checksum FROM build WHERE checksum = '$checksum'")) {
		    $dbh->do("UPDATE BUILD SET age = ? WHERE checksum = ?", undef, 
			     ($stat->mtime, $checksum));
		    die "next please"; #Moves to the next record in the exception handler
		}
		if ($opt_verbose) { print "$logfn\n"; }
		
		($rev) = ($data =~ /BUILD REVISION: ([^\n]+)/);
		my $commit;
		
		if ($data =~ /BUILD COMMIT REVISION: (.*)/) {
		    $commit = $1;
		} else {
		    $commit = $rev;
		}
		my $status_html = $db->build_status_from_logs($data, $err);
		
		# Look up the database to find the previous status
		$st = $dbh->prepare("SELECT status, revision, commit_revision FROM build WHERE tree = ? AND host = ? AND compiler = ? AND revision != ? AND commit_revision != ? ORDER BY id DESC LIMIT 1");
		$st->execute( $tree, $host, $compiler, $rev, $commit);
		
		my $old_status_html;
		my $old_rev;
		my $old_commit;
		while ( my @row = $st->fetchrow_array ) {
		    $old_status_html = @row[0];
		    $old_rev = @row[1];
		    $old_commit = @row[2];
		}
		
		$st->finish();
		
		$st = $dbh->prepare("INSERT INTO build (tree, revision, commit_revision, host, compiler, checksum, age, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)");
		$st->execute($tree, $rev, $commit, $host, $compiler, $checksum, $stat->mtime, $status_html);


#   SKIP This code, as it creates massive databases, until we get code to use the information, and a way to expire the results
#	    my $build = $dbh->func('last_insert_rowid');
#	    
#	    $st = $dbh->prepare("INSERT INTO test_run (build, test, result, output) VALUES ($build, ?, ?, ?)");
#	    
#	    while ($data =~ /--==--==--==--==--==--==--==--==--==--==--.*?
#	Running\ test\ ([\w\-=,_:\ \/.&;]+).*?
#	--==--==--==--==--==--==--==--==--==--==--
#	(.*?)
#	==========================================.*?
#	TEST\ (FAILED|PASSED|SKIPPED):.*?
#	==========================================\s+
#	/sxg) {
#		# Note: output is discarded ($2)
#		$st->execute($1, $3, undef);
#	    }

		$st->finish();

		my $cur_status = $db->build_status_info_from_html($rev, $commit, $status_html);
		my $old_status;
		
		# Can't send a nastygram until there are 2 builds..
		if (defined($old_status_html)) {
		    $old_status = $db->build_status_info_from_html($old_rev, $old_commit, $old_status_html);
		    check_and_send_mails($tree, $host, $compiler, $cur_status, $old_status);
		}
		
		if ($dry_run) {
		    $dbh->rollback;
		    die "next please"; #Moves to the next record in the exception handler
		}

		$dbh->commit;
	    };

	    if ($@) {
		local $dbh->{RaiseError} = 0;
		$dbh->rollback;
		
		if ($@ eq "next please") {
		    # Ignore errors and hope for better luck next time the script is run
		    next;
		} elsif ($@ =~ /database is locked/ and $retry < 3) {
		    $retry++;
		    sleep(1);
		    redo;
		}
		
		print "Failed to process record for reason: $@";
		next;
	    }

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

$dbh->disconnect();
