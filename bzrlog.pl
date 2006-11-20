#!/usr/bin/perl -w
#
# Extract information about recent bzr  commits
#
# tridge@samba.org, November 2006

use strict;
use lib "web";
use util;
use POSIX;
use Data::Dumper;
use File::stat;
use Date::Parse;

####################################
# push an entry onto the array

sub push_entry($$$)
{
	my $entry = shift;
	my $log = shift;
	my $days = shift;
	unshift(@{$log}, $entry);
#	printf("Adding entry\n");
#	print Dumper $entry;
	return $log;
}

####################################
# return an array of logfile entries given a bzr log file. 
# Only return entries newer than $days old
sub bzr_parse($$)
{
	my $bzr_path = shift;
	my $days = shift;
	my $log;
	my $entry = {};
	my $addto = "";

	open(FILE, "bzr log -v $bzr_path |");
	while (defined (my $line = <FILE>)) {
#		printf("line=$line");
		# separator line indicates new entry
		if ($line =~ /^\-{5,}$/) {
			# only add entry if one exists
			if ($entry->{DATE}) {
				$log = push_entry($entry, $log, $days);
			}

			$entry = {};

			next;
		}

		if ($line =~ /^\s\s(.*)$/) {
			my $s = $1;
			if ($addto eq "MESSAGE") {
				if (defined $entry->{MESSAGE}) {
					$entry->{MESSAGE} .= "$s\n";
				} else {
					$entry->{MESSAGE} = "$s\n";
				}
			} else {
				if (defined $entry->{$addto}) {
					$entry->{$addto} .= " $s";
				} else {
					$entry->{$addto} = "$s";
				}
			}
		} else {
			$addto = "";
		}

		if ($line =~ /^revno: (\d+)$/) {
			$entry->{REVISION} = $1;
		}

		if ($line =~ /^committer: (.*)$/) {
			$entry->{AUTHOR} = $1;
		}

		if ($line =~ /^branch nick: (.*)$/) {
			$entry->{TREE} = $1;
		}

		if ($line =~ /^timestamp: (.*)$/) {
			$entry->{DATE} = str2time($1);
		}

		if ($line =~ /^added:/) {
			$addto = "ADDED";
		}
		if ($line =~ /^modified:/) {
			$addto = "MODIFIED";
		}
		if ($line =~ /^removed:/) {
			$addto = "REMOVED";
		}
		if ($line =~ /^message:/) {
			$addto = "MESSAGE";
		}
	}

	if ($entry->{DATE}) {
		$log = push_entry($entry, $log, $days);
	}

	close(FILE);

	# cleanup the messages
	for (my $line = $#{$log}; $line > 0; $line--) {
		$entry = $log->[$line];
		if ($entry->{MESSAGE}) {
			while (chomp($entry->{MESSAGE})) { }
		}
	}

	return $log;
}


######################################
# main program
if ($#ARGV < 2 || $ARGV[0] eq '--help' || $ARGV[0] eq '-h') {
	print "
Usage: bzrlog.pl <PATH> <DAYS> <DEST>

Extract all commits bzr tree <PATH> in the last DAYS days. Store the
results in DEST in a format easily readable by the build farm web
scripts.  "; exit(1); }

my $bzr_path = $ARGV[0];
my $days = $ARGV[1];
my $dest = $ARGV[2];


my $log = bzr_parse($bzr_path, $days);

util::SaveStructure($dest, $log);
