#!/usr/bin/perl -w

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

my $fname = $ARGV[0];
my ($tree, $host, $compiler);

# break up the name into components
if ($fname =~ /^build\.([\w-]+)\.(\w+)\.(\w+)\.log$/) {
	$tree = $1;
	$host = $2;
	$compiler = $3;
} else {
	confess "Unable to parse filename";
}

my $rev = build_revision($fname);
my $status = build_status($fname);

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
	# no previous revision
	exit(0);
}


my $status2 = build_status($fname);

if ($status2 <= $status) {
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

my $recipients = join(",", keys %culprits);

# send the nastygram
open(MAIL,"|Mail -s \"BUILD BROKEN AT REVISION $rev\" $recipients");
print MAIL "Build status for revision $rev is $status\n";
print MAIL "Build status for revision $rev2 is $status2\n\n";
print MAIL "The build may have been broken by one of the following commits:\n\n";
print MAIL "$log";
close(MAIL);

exit(0);
