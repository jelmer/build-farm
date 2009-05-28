#!/usr/bin/perl -w
#
# Script to parse a build farm log file and send some mail chastising
# the possible culprits based on recent commits.
#
# To use in test mode (output sent to stdout instead of sendmail),
# pass the -n option followed by the log file name.  For example:
#
# $ cd ~build/master/data
# $ ../analyse.pl -n build.$PRODUCT.$HOST.$COMPILER.log
#

use strict;
use warnings;

use FindBin qw($RealBin);

use lib "$RealBin";
use lib "$RealBin/web";
use data;
use util;
use history;
use POSIX;
use Data::Dumper;
use File::stat;
use Carp;
use Net::XMPP;
use Getopt::Long;

my $BASEDIR = "$RealBin";

my $unpacked_dir = "/home/ftp/pub/unpacked";

# we open readonly here as only apache(www-run) has write access
my $db = new data($BASEDIR, 1);

my %trees = %{$db->{trees}};

#####################################t#
# find the build status as an integer
# it gets one point for passing each stage
sub build_status($$$$)
{
	my ($host, $tree, $compiler, $rev_seq) = @_;
	my $rev = $db->build_revision($host, $tree, $compiler, $rev_seq);
	my $status_html = $db->build_status($host, $tree, $compiler, $rev_seq);
	my $status_raw = util::strip_html($status_html);
	my @status_split = split("/", $status_raw);
	my $status_str = "";
	my @status_arr = ();
	my $status_val = 0;
	my $status = undef;

	foreach my $r (@status_split) {
		$r =~ s/^\s+//;
		$r =~ s/\s+$//;

		my $e;
		if ($r eq "ok") {
			$e = 0;
		} elsif ($r =~ /(\d+)/) {
			$e = $1;
			$e = 1 unless defined($e);
			$e = 1 unless $e > 0;
		} else {
			$e = 1;
		}

		$status_str .= "/" unless $status_str eq "";
		$status_str .= $r;

		$status_val += $e;

		push(@status_arr, $e);
	}

	$status->{rev}		= $rev;
	$status->{rev_seq}	= $rev_seq;
	$status->{array}	= \@status_arr;
	$status->{string}	= $status_str;
	$status->{html}		= $status_html;
	$status->{value}	= $status_val;

	return $status;
}

sub cur_status($$$)
{
	my ($host, $tree, $compiler) = @_;

	return build_status($host, $tree, $compiler, 0);
}

sub old_status($$$$)
{
	my ($cur, $host, $tree, $compiler) = @_;
	my %revs = $db->get_old_revs($tree, $host, $compiler);
	my $old = undef;

	foreach my $or (reverse sort keys %revs) {
		$old = build_status($host, $tree, $compiler, $or);
		if ($old->{rev} eq $cur->{rev}) {
			$old = undef;
			next;
		}
		last;
	}

	return $old;
}

sub status_cmp($$)
{
	my ($s1, $s2) = @_;
	my @a1 = @{$s1->{array}};
	my @a2 = @{$s2->{array}};
	my $c1 = 0;
	my $c2 = 0;

	for (my $i = 0; ; $i++) {
		$c1++ if defined($a1[$i]);
		$c2++ if defined($a2[$i]);
		last unless defined($a1[$i]);
		last unless defined($a2[$i]);

		return $c2 - $c1 if ($c1 != $c2);

		return $a2[$i] - $a1[$i] if ($a1[$i] != $a2[$i]);
	}

	return $s2->{value} - $s1->{value};
}

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

#######################################################
# main program

my $dry_run = 0;

if ($#ARGV >= 0 && $ARGV[0] eq "-n") {
	$dry_run = 1;
	shift @ARGV;
} if ($#ARGV < 0 || $ARGV[0] eq "-h" || $ARGV[0] eq "--help") {
	print <<EOU;
Usage: analyse.pl [-n] <LOGFILE>

Script to parse a build farm log file, \$LOGFILE, and send some mail
chastising the possible culprits based on recent commits.

-n  Will cause the script to send output to stdout instead of
    to sendmail.
EOU
	exit(1);
}

my $fname = $ARGV[0];
my ($tree, $host, $compiler);

# break up the name into components
if ($fname =~ /build\.([\w-]+)\.([\w-]+)\.([\w.-]+)\.log$/) {
	$tree = $1;
	$host = $2;
	$compiler = $3;
} else {
	confess "Unable to parse filename";
}

my $t = $trees{$tree};
if (not defined($t)) {
	confess "Unknown tree[$tree]";
}

my $cur = cur_status($host, $tree, $compiler);

if (not defined($cur)) {
	# we can't analyse trees without revisions
	exit(0);
}

printf("rev=$cur->{rev} status=$cur->{string}\n") if $dry_run;

my $old = old_status($cur, $host, $tree, $compiler);

if (not defined($old)) {
	printf("no previous revision\n") if $dry_run;
	# no previous revision
	exit(0);
}

printf("old rev=$old->{rev} status=$old->{string}\n") if $dry_run;

my $cmp = status_cmp($old, $cur);
#printf("cmp: $cmp\n");

if ($cmp <= 0) {
	printf("the build didn't get worse ($cmp)\n") if $dry_run;
	exit(0) unless $dry_run;
}

my $log = get_log($host, $tree, $compiler, $cur, $old);
if (not defined($log)) {
	printf("no log\n") if $dry_run;
	exit(0);
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
		open(MAIL,"|Mail -s \"$subject\" $recipients");
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

if ($dry_run) {
	print "skip jabber messages\n";
	exit(0);
}

# Send message to jabber group
my $cnx = new Net::XMPP::Client();

$cnx->Connect(hostname => "jabber.org");

sub read_config_file ($) {
	# This function was copied from the sendxmpp source, (C) DJCBB
	my $cfg_file = shift;
    
	open (CFG,"<$cfg_file") || die("cannot open $cfg_file for reading: $!");

	my $line = 0;
	my %config;
	while (<CFG>) {
		++$line;
		next if (/^\s*$/);     # ignore empty lines
		next if (/^\s*\#.*/);  # ignore comment lines
	
		s/\#.*$//; # ignore comments in lines

		if (/([-\.\w]+)@([-\.\w:]+)\s+(\S+)\s*$/) {
			%config = ('username' => $1,
				   'jserver'  => $2,
				   'port'     => 0,
				   'password' => $3);

			if ($config{'jserver'} =~ /(.*):(\d+)/) {
				$config{'jserver'} = $1;
				$config{'port'}    = $2;
			}
		} else {
			close CFG;
			die("syntax error in line $line of $cfg_file");
		}
	}

	close CFG;

	die ("no correct config found in $cfg_file") unless (scalar(%config));

	return \%config;
}

my $jabber_config = read_config_file("$ENV{HOME}/.sendxmpprc");

$cnx->AuthSend(%$jabber_config);

# set the presence
my $users = {
	'jelmer\@samba.org' => "ctrlsoft\@jabber.org"
};

# Send messages to individual users where the Jabber adress is known
foreach (keys %{$log->{recipients}}) {
	next unless(defined($users->{$_}));

	$cnx->MessageSend('to' => $users->{$_},
			  'subject' => $subject,
			  'body' => "You might have broken the build!\n\n" . $body);
}

# set the presence
my $pres = new Net::XMPP::Presence;
my $res = $pres->SetTo("samba-build-breakage\@conference.jabber.org/analyse");

$cnx->Send($pres); 

my $groupmsg = new Net::XMPP::Message;
$groupmsg->SetMessage('to' => "samba-build-breakage\@conference.jabber.org",
		      'body' => $body,
		      'type' => 'groupchat');

$cnx->Send($groupmsg);

# leave the group
$pres->SetPresence('Type' => 'unavailable',
		   'To' => "samba-build-breakage\@conference.jabber.org");

$cnx->Disconnect();
