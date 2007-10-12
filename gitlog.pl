#!/usr/bin/perl -w
#
# Extract information about recent git commits (based on bzrlog.pl
#
# tridge@samba.org, November 2006
# bjacke@samba.org, October 2007

use strict;
use lib "web";
use util;
use POSIX;
use Data::Dumper;
use File::stat;
use Date::Parse;

####################################
# push an entry onto the array

sub push_entry($$$$)
{
	my $entry = shift;
	my $log = shift;
	my $days = shift;
	my $tree = shift;
	unshift(@{$log}, $entry);
#	printf("Adding entry\n");
#	print Dumper $entry;
	return $log;
}

####################################
# return an array of logfile entries given a git log file. 
# Only return entries newer than $days old
sub git_parse($$$)
{
	my $git_path = shift;
	my $days = shift;
	my $tree = shift;
	my $log;
	my $entry = {};
	my $addto = "";

	my $magicstart = "---GIT-COMMIT-MAGIC-START---";
	my $magicmsg = "---GIT-COMMIT-MAGIC-MESSAGE---";
	my $magicdiff = "---GIT-COMMIT-MAGIC-DIFF---";
	my $format = $magicstart."%n%H%n%ct%n%an%n".$magicmsg."%n%s%b%n".$magicdiff;
	my $sincedays;
	$sincedays = "--since='$days days'" if defined($days);
	# the number of entries is also being limited to a maximum number
	# in the "git log" command. This is required because we
	# checked in 11 years of samba development 1 days ago :-)

	# git log --pretty=format:---GIT-COMMIT-MAGIC-START---%n%H%n%ct%n%an%n---GIT-COMMIT-MAGIC-MESSAGE---%n%s%b%n---GIT-COMMIT-MAGIC-DIFF--- --numstat --since='1 days'
	open(FILE, "cd $git_path; git log --pretty=format:$format --numstat $sincedays -500 $tree |");
	my $line_count;
	while (defined (my $line = <FILE>)) {
#		printf("line=$line");
		# separator line indicates new entry
		if ($line =~ /^$magicstart$/ ) {
			# only add entry if one exists
			if ($entry->{DATE}) {
				$log = push_entry($entry, $log, $days, $tree);
			}

			$entry = {};
			$line_count = 0;
			next;
		}
		$line_count++;
		
		if ($line_count == 1) {
			chomp $line;
			$entry->{REVISION} = $line;
			next;
		} elsif ($line_count == 2) {
			chomp $line;
			$entry->{DATE} = $line;
			next;
		} elsif ($line_count == 3) {
			chomp $line;
			$entry->{AUTHOR} = $line;
			next;
		}

		if ($line =~ /^$magicmsg$/) {
			$addto = "MESSAGE";
			next;
		}

		if ($line =~ /^$magicdiff$/) {
			$addto = "DIFF_STUFF";
			next;
		}
		
		if ($addto eq "MESSAGE") {
			$entry->{MESSAGE} .= $line;
			next;
		}
		chomp $line;
		

		if ($addto eq "DIFF_STUFF") {
			$line =~ m/^([0-9]*)[ \t]*([0-9]*)[ \t]*(.*)/;
			my $a = $1;
			my $b = $2;
			my $f = $3;
			if (($b eq "0") and ($a ne "0")) {
				$entry->{ADDED} .= "$f ";
			} elsif (($a eq "0") and ($b ne "0")) {
				$entry->{REMOVED} .= "$f ";
			} else {
				$entry->{FILES} .= "$f ";
			}
			next;
		}
	}
	# the last log entry should be caught here:
	if ($entry->{DATE}) {
		$log = push_entry($entry, $log, $days, $tree);
	}

	close(FILE);

	# cleanup the messages
#	for (my $line = $#{$log}; $line > 0; $line--) {
#		$entry = $log->[$line];
#		if ($entry->{MESSAGE}) {
#			while (chomp($entry->{MESSAGE})) { }
#		}
#	}

	return $log;
}


######################################
# main program
if ($#ARGV < 2 || $ARGV[0] eq '--help' || $ARGV[0] eq '-h') {
	print "
Usage: gitlog.pl <PATH> <DAYS> <DEST>

Extract all commits git tree <PATH> in the last DAYS days. Store the
results in DEST in a format easily readable by the build farm web
scripts.  "; exit(1); }

my $git_path_arg = $ARGV[0];
my $days_arg = $ARGV[1];
my $tree_arg = $ARGV[2];
my $dest_arg = $ARGV[3];


my $log_data = git_parse($git_path_arg, $days_arg, $tree_arg);

util::SaveStructure($dest_arg, $log_data);
