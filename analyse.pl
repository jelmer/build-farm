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

use strict qw{vars};
use FindBin qw($RealBin);

use lib "$RealBin";
use lib "$RealBin/web";
use util;
use history;
use POSIX;
use Data::Dumper;
use File::stat;
use Carp;

my $WEBDIR = "$RealBin/web";
my $BASEDIR = "$WEBDIR/..";
my $CACHEDIR = "$WEBDIR/../cache";
my $DATADIR = "$BASEDIR/data";

my $unpacked_dir = "/home/ftp/pub/unpacked";


#######################################
# find the build status as an integer
# it gets one point for passing each stage
sub build_status($)
{
	my $status = 0;
	my $fname = shift;
	my $log = util::FileLoad($fname) || confess "Unable to load log";
	if ($log =~ /^CONFIGURE STATUS: 0$/m) {
		$status++;
	}
	if ($log =~ /^BUILD STATUS: 0$/m) {
		$status++;
	}
	if ($log =~ /^INSTALL STATUS: 0$/m) {
		$status++;
	}
	if ($log =~ /^TEST STATUS: 0$/m) {
		$status++;
	}
	return $status;
}

#######################################
# find the build revision, or 0 if unknown
sub build_revision($)
{
	my $fname = shift;
	my $log = util::FileLoad($fname) || confess "Unable to load log";
	if ($log =~ /^BUILD REVISION: (\d+)$/m) {
		return $1;
	}
	return 0;
}


#######################################################
# main program

my $dry_run = 0;

if ($#ARGV >= 0 && $ARGV[0] eq "-n") {
  $dry_run = 1;
  shift @ARGV;
}
if ($#ARGV < 0 || $ARGV[0] eq "-h" || $ARGV[0] eq "--help") {
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
if ($fname =~ /^build\.([\w-]+)\.([\w-]+)\.([\w.-]+)\.log$/) {
	$tree = $1;
	$host = $2;
	$compiler = $3;
} else {
	confess "Unable to parse filename";
}

my $rev = build_revision($fname);
my $status = build_status($fname);

if ($dry_run) {
    printf("rev=$rev status=$status\n");
}

if ($rev == 0) {
	# we can't analyse trees without revisions
	exit(0);
}

# try and find the previous revision
my $rev2;

for ($rev2=$rev-1;$rev2 > 0;$rev2--) {
	$fname = "oldrevs/build.$tree.$host.$compiler-$rev2.log";
	last if (stat($fname));
}

if ($rev2 == 0) {
    $dry_run && printf("no previous revision\n");
	# no previous revision
	exit(0);
}

my $status2 = build_status($fname);

if ($dry_run) {
    printf("status=$status status2=$status2\n");
}

if ($status2 <= $status && !$dry_run) {
	# the build didn't get worse
	exit(0);
}

# rev2 itself didn't break the build
my $firstrev = $rev2 + 1;

my $log = `svn log --non-interactive -r $firstrev:$rev $unpacked_dir/$tree` || die "Unable to get svn log";

#print($log);

# get the list of possible culprits
my $log2 = $log;
my %culprits;

while ($log2 =~ /\nr\d+ \| (\w+) \|.*?lines\n(.*)$/s) {
    $culprits{$1} = 1; 
    $log2 = $2;
}

# Add a URL to the diffs for each change
$log =~ s/\n(r(\d+).*)/$1\nhttp:\/\/build.samba.org\/?function=diff;tree=${tree};revision=$2/g;

my $recipients = join(",", keys %culprits);

# send the nastygram
if ($dry_run) {
  open(MAIL,"|cat");
} else {
  open(MAIL,"|Mail -s \"BUILD of $tree BROKEN on $host with $compiler AT REVISION $rev\" $recipients");
}

print MAIL << "__EOF__";
Broken build for tree $tree on host $host with compiler $compiler
Build status for revision $rev is $status
Build status for revision $rev2 is $status2

See http://build.samba.org/?function=View+Build;host=$host;tree=$tree;compiler=$compiler

The build may have been broken by one of the following commits:

$log
__EOF__

close(MAIL);
