#!/usr/bin/perl -w
# This CGI script presents the results of the build_farm build
# tridge@samba.org, April 2001

use strict;
use util;
use POSIX;
use Data::Dumper;
use File::stat;
use Date::Parse;

####################################
# parse a CVS date 
sub cvs_parse_date($)
{
    my $s = shift;

    if (! ($s =~ /@/)) {
      return str2time($s);
    }

    if ($s =~ /(.*) (.*) ([0-9]+), ([0-9]+) @ ([0-9]+):([0-9]+)/) {
	my $day = $1;
	my $month = $2;
	my $mday = $3;
	my $year = $4;
	my $hour = $5;
	my $min = $6;
	my (%months) = ('January' => 1, 'February' => 2, 'March' => 3, 'April' => 4,
			'May' => 5, 'June' => 6, 'July' => 7, 'August' => 8, 'September' => 9,
			'October' => 10, 'November' => 11, 'December' => 12);
	my $t = mktime(0, $min, $hour, $mday, $months{$month}-1, $year-1900);
	return $t;
    }

    print "ERROR: bad date format $s\n";
    return 0;
}


####################################
# push an entry onto the array

# FIXME: This incorrectly handles multiple commits with the same log
# message.  The cvslog output only shows the revisions for the last
# commit, but actually we want to either not coalesce, or show the
# overall delta.

sub push_entry($$$$$)
{
  my $entry = shift;
  my $log = shift;
  my $days = shift;
  my $tree = shift;
  my $tag = shift;
  my $lastentry = $log->[$#{$log}];

  if ($lastentry->{DATE} && $lastentry->{AUTHOR} &&
      ($lastentry->{DATE} > $entry->{DATE}-600) &&
      ($lastentry->{AUTHOR} eq $entry->{AUTHOR}) &&
      ((!$lastentry->{TAG} && !$entry->{TAG}) ||
       ($lastentry->{TAG} eq $entry->{TAG})) &&
      ((!$lastentry->{MESSAGE} && !$entry->{MESSAGE}) ||
       ($lastentry->{MESSAGE} eq $entry->{MESSAGE}))) {

    if (exists $lastentry->{FILES}) {
      $lastentry->{FILES} .= " $entry->{FILES}";
    } else {
      $lastentry->{FILES} = $entry->{FILES};
    }

    if (exists $lastentry->{ADDED}) {
      $lastentry->{ADDED} .= " $entry->{ADDED}";
    } else {
      $lastentry->{ADDED} = $entry->{ADDED};
    }

    if (exists $lastentry->{REMOVED}) {
      $lastentry->{REMOVED} .= " $entry->{REMOVED}";
    } else {
      $lastentry->{REMOVED} = $entry->{REMOVED};
    }

    if (exists $lastentry->{REVISIONS}) {
	    $lastentry->{REVISIONS} = {%{$lastentry->{REVISIONS}},%{$entry->{REVISIONS}}};
    } else {
	    $lastentry->{REVISIONS} = $entry->{REVISIONS};
    }
  } else {
    if (($entry->{DATE} > time() - $days*24*60*60) &&
	((!$entry->{TAG} && !$tag) || 
	 ($entry->{TAG} eq $tag)) &&
	($entry->{TREE} eq $tree)) {
      push(@{$log}, $entry);
    }
  }
  return $log;
}

####################################
# return an array of logfile entries given a cvs log file. 
# Only return entries newer than $days old
sub cvs_parse($$$$)
{
    my $file = shift;
    my $days = shift;
    my $tree = shift;
    my $tag = shift;
    my $log;
    my $entry;

    open(FILE, "< $file");
    while (<FILE>) {
	my $line = $_;

	# ignore separator lines
	if ($line =~ /^[*]+/) { next; }

	if ($line =~ /^Date:\s*(.*)/) {
	    if ($entry->{DATE}) {
	      $log = push_entry($entry, $log, $days, $tree, $tag);
	    }
	    $entry = {};
	    $entry->{DATE} = cvs_parse_date($1);
	    $entry->{DIR} = "";
	    next;
	}

	if ($line =~ /^Author:\s*(.*)/) {
	    $entry->{AUTHOR} = $1;
	    next;
	}

	if ($line =~ /^Update of (.*)/) {
	    $entry->{TREE} = $1;
	    if ($entry->{TREE} =~ /\/(data|home)\/cvs\/([^\/]*)\/?(.*)/) {
		$entry->{TREE} = $2;
		$entry->{DIR} = $3;
		if ($entry->{DIR}) { $entry->{DIR} .= "/"; }
	    } elsif ($entry->{TREE} =~ /\/home\/tridge\/cvstest\/([^\/]*)\/?(.*)/) {
		$entry->{TREE} = $1;
		$entry->{DIR} = $2;
		if ($entry->{DIR}) { $entry->{DIR} .= "/"; }
	    } else {
		print "badly formed tree $entry->{TREE}\n";
	    }
	    if (! $entry->{DIR}) { $entry->{DIR} = ""; }
	    next;
	}

	if ($line =~ /^Modified Files:/) {
	    while (<FILE>) {
		$line = $_;
		if ($line =~ /^[*A-Z]/) { last; }

		if ($line =~ /^\s*Tag: (.*)/) {
		    $entry->{TAG} = $1;
		    next;
		}
		
		while ($line =~ /\s*([^\s]+)(.*)/) {
		  if ($entry->{FILES}) { 
		      $entry->{FILES} .= " $entry->{DIR}$1";
		    } else {
			$entry->{FILES} = "$entry->{DIR}$1";
		    }
		  $line = $2;
		}
	    }
	}

	if ($line =~ /^Added Files:/) {
	    while (<FILE>) {
		$line = $_;
		if ($line =~ /^[*A-Z]/) { last; }

		if ($line =~ /^\s*Tag: (.*)/) {
		    $entry->{TAG} = $1;
		    next;
		}
		
		while ($line =~ /\s*([^\s]+)(.*)/) {
		    if ($entry->{ADDED}) { 
			$entry->{ADDED} .= " $entry->{DIR}$1";
		    } else {
			$entry->{ADDED} = "$entry->{DIR}$1";
		    }
		    $line = $2;
		}
	    }
	}

	if ($line =~ /^Removed Files:/) {
	    while (<FILE>) {
		$line = $_;
		if ($line =~ /^[*A-Z]/) { last; }

		if ($line =~ /^\s*Tag: (.*)/) {
		    $entry->{TAG} = $1;
		    next;
		}
		
		while ($line =~ /\s*([^\s]+)(.*)/) {
		    if ($entry->{REMOVED}) { 
			$entry->{REMOVED} .= " $entry->{DIR}$1";
		    } else {
			$entry->{REMOVED} = "$entry->{DIR}$1";
		    }
		    $line = $2;
		}
	    }
	}

	if ($line =~ /^Log Message:/) {
	    while (<FILE>) {
		$line = $_;
		if ($line eq "****************************************\n") { last; }
		if ($line =~ /^Revisions:/) { last; }
		$entry->{MESSAGE} .= $line;
	    }
	}

	if ($line =~ /^Revisions:/) {
	    while (<FILE>) {
		$line = $_;
		if ($line =~ /^[*]/) { last; }
		if ($line =~ /^\s*http/) { next; }
		if ($line =~ /^\s*(.*?)\s*(NONE|[0-9][0-9.]*) => (NONE|[0-9][0-9.]*)/) { 
		  my $file = "$entry->{DIR}$1";
		  my $rev1 = $2;
		  my $rev2 = $3;
		  $entry->{REVISIONS}->{$file}->{REV1} = $rev1;
		  $entry->{REVISIONS}->{$file}->{REV2} = $rev2;
		}
	    }
	}
    }

    if ($entry->{DATE}) {
      $log = push_entry($entry, $log, $days, $tree, $tag);
    }

    close(FILE);

    # cleanup the messages
    for (my $line=0; $line <= $#{$log}; $line++) {
	$entry = $log->[$line];
	if ($entry->{MESSAGE}) {
	    while (chomp($entry->{MESSAGE})) { }
	}
    }
    
    return $log;
}


######################################
# main program
if ($#ARGV < 4) {
    print "
Usage: cvslog.pl <file> <days> <tree> <tag> <dest>
}";
    exit(1);
}

my $file = $ARGV[0];
my $days = $ARGV[1];
my $tree = $ARGV[2];
my $tag =  $ARGV[3];
my $dest = $ARGV[4];

my $log = cvs_parse($ARGV[0], $days, $tree, $tag);

util::SaveStructure($dest, $log);
