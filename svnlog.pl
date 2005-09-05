#!/usr/bin/perl -w
#
# Extract information about recent SVN commits
#
# tridge@samba.org, April 2001
# vance@samba.org, August 2004

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

	# we can assume that each entry is unique, due to the nature of svn
	# so we don't need any of the magic required for cvs
	if (($entry->{DATE} > time() - $days*24*60*60) &&
	    ($entry->{TREE} eq $tree)) {

		# we put these on in reverse order so that it's in order of
		# date.
		unshift(@{$log}, $entry);
	}

	return $log;
}

####################################
# return an array of logfile entries given a svn log file. 
# Only return entries newer than $days old
sub svn_parse($$$$)
{
	my $repo_url = shift;
	my $tree_dir = shift;
	my $days = shift;
	my $tree = shift;
	my $log;
	my $entry = {};

	# don't know what time zone this machine is, but given the granularity
	# of days, (intended to be about 60 days), a few hours either way makes
	# very little difference
	my $start_date = POSIX::strftime("%Y-%m-%d", gmtime(time() - $days*60*60*24));

	open(FILE, "svn log --verbose --non-interactive $repo_url/$tree_dir -r HEAD:'{$start_date}' |");
	#open(FILE, "< log.txt") or die "Could not open log: $!";
	while (defined (my $line = <FILE>)) {


		# separator line indicates new entry
		if ($line =~ /^\-{5,}$/) {
			# only add entry if one exists
			if ($entry->{DATE}) {
				$log = push_entry($entry, $log, $days, $tree);
			}

			$entry = {};

			next;
		}

		# the first line after the separator (which sets entry to {})
		# looks like:
		# r15 | vance | 2004-07-31 22:24:55 -0700 (Sat, 31 Jul 2004) | 4 lines
		if (! defined $entry->{DATE}) {

			my ($rev, $author, $date, $lines) = split /\s+\|\s+/, $line;
			$entry->{DATE} = str2time($date);

			# kill the r in the revision
			$rev =~ s/^r//;
			$entry->{REVISION} = $rev;
			$entry->{AUTHOR} = $author;
			$entry->{TREE} = $tree;
			next;
		}


		# read the list of changed/added/removed files
		if ($line =~ /^Changed paths:/) {

			while (<FILE>) {

				$line = $_;
				if ($line =~ /^\s*$/) { last; }

				elsif ($line =~ /\s+A (.*)/) {
					my $file = $1;
					$file =~ s#^/$tree_dir/##o;
					if ($entry->{ADDED}) {
						$entry->{ADDED} .= " $file";
					} else {
						$entry->{ADDED} = "$file";
					}
				}

				elsif ($line =~ /\s+M (.*)/) {
					my $file = $1;
					$file =~ s#^/$tree_dir/##o;
					if ($entry->{FILES}) {
						$entry->{FILES} .= " $file";
					} else {
						$entry->{FILES} = "$file";
					}
				}

				elsif ($line =~ /\s+R (.*)/) {
					my $file = $1;
					$file =~ s#^/$tree_dir/##o;
					if ($entry->{REMOVED}) {
						$entry->{REMOVED} .= " $file";
					} else {
						$entry->{REMOVED} = "$file";
					}
				}
			}

			next;
		}

		# add the line to the message
		if (defined $entry->{MESSAGE}) {
			$entry->{MESSAGE} .= $line;
		}
		else {
			$entry->{MESSAGE} = $line;
		}
	}

	if ($entry->{DATE}) {
		$log = push_entry($entry, $log, $days, $tree);
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
if ($#ARGV < 4 || $ARGV[0] eq '--help' || $ARGV[0] eq '-h') {
	print "
Usage: svnlog.pl <REPOSITORY-URL> <TREE-DIR> <DAYS> <TREE> <DEST>

Extract all commits to REPOSITORY-URL/TREE-DIR in the last
DAYS days. Store the results in DEST, indexed under TREE,
in a format easily readable by the build farm web scripts.
"
	exit(1);
}

my $repo_url = $ARGV[0];
my $tree_dir = $ARGV[1];
my $days = $ARGV[2];
my $tree = $ARGV[3];
my $dest = $ARGV[4];


my $log = svn_parse($repo_url, $tree_dir, $days, $tree);

util::SaveStructure($dest, $log);
