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

#use strict qw{vars};
use FindBin qw($RealBin);

use lib "$RealBin";
use lib "$RealBin/web";
use util;
use history;
use POSIX;
use Data::Dumper;
use File::stat;
use Carp;
use Net::XMPP;
use Getopt::Long;
use strict;

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

while ($log2 =~ /\nr\d+ \| (\w+) \|.*?line(s?)\n(.*)$/s) {
    $culprits{$1} = 1; 
    $log2 = $3;
}

# Add a URL to the diffs for each change
$log =~ s/\n(r(\d+).*)/$1\nhttp:\/\/build.samba.org\/?function=diff;tree=${tree};revision=$2/g;

my $recipients = join(",", keys %culprits);

my $subject = "BUILD of $tree BROKEN on $host with $compiler AT REVISION $rev";

# send the nastygram
if ($dry_run) {
  print "$subject\n";
  open(MAIL,"|cat");
} else {
  open(MAIL,"|Mail -s \"$subject\" $recipients");
}

my $body = << "__EOF__";
Broken build for tree $tree on host $host with compiler $compiler
Build status for revision $rev is $status
Build status for revision $rev2 is $status2

See http://build.samba.org/?function=View+Build;host=$host;tree=$tree;compiler=$compiler

The build may have been broken by one of the following commits:

$log
__EOF__
print MAIL $body;

close(MAIL);

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
    
    die ("no correct config found in $cfg_file") 
      unless (scalar(%config));       

    return \%config;	           
}

my $jabber_config = read_config_file("$ENV{HOME}/.sendxmpprc");

$cnx->AuthSend(%$jabber_config);

# set the presence
my $users = {
	jelmer => "ctrlsoft\@jabber.org"
};

# Send messages to individual users where the Jabber adress is known
foreach (keys %culprits) {
	next unless(defined($users->{$_}));

	$cnx->MessageSend('to' => $users->{$_}, 'subject' => $subject, 'body' => "You might have broken the build!\n\n" . $body);
}

# set the presence
my $pres = new Net::XMPP::Presence;
my $res = $pres->SetTo("samba-build-breakage\@conference.jabber.org/analyse");

$cnx->Send($pres); 

my $groupmsg = new Net::XMPP::Message;
$groupmsg->SetMessage(to => "samba-build-breakage\@conference.jabber.org", body => $body, type => 'groupchat');

$cnx->Send($groupmsg);

# leave the group
$pres->SetPresence (Type=>'unavailable',To=>"samba-build-breakage\@conference.jabber.org");

$cnx->Disconnect();
