#!/usr/bin/perl -w
# Simple database query script for the buildfarm
#
# Copyright (C) Andrew Tridgell <tridge@samba.org>     2001-2005
# Copyright (C) Andrew Bartlett <abartlet@samba.org>   2001
# Copyright (C) Vance Lankhaar  <vance@samba.org>      2002-2005
# Copyright (C) Martin Pool <mbp@samba.org>            2001
# Copyright (C) Jelmer Vernooij <jelmer@samba.org>	   2007
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#   
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#   
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

package data;

use util;
use POSIX;
use File::stat;
use CGI qw/:standard/;
use FindBin qw($RealBin);

require Exporter;
@ISA = qw(Exporter);
@EXPORT_OK = qw(@hosts %hosts @compilers @pseudo_trees %trees $OLDAGE $DEADAGE
                build_age_mtime build_age_ctime build_revision
				build_status err_count read_log read_err get_old_revs);

use strict;
use warnings;

my $WEBDIR = "$RealBin";
my $CACHEDIR = "$WEBDIR/../cache";
my $LCOVDIR = "$WEBDIR/../../lcov/data";
my $LCOVHOST = "tridge";
our $OLDAGE = 60*60*4;
our $DEADAGE = 60*60*24*4;

##############################################
# this defines what it is possible to build 
# and what boxes. Should be in a config file
our @compilers = util::load_list("$WEBDIR/compilers.list");
our (%hosts) = util::load_hash("$WEBDIR/hosts.list");
our @hosts = sort { $hosts{$a} cmp $hosts{$b} } keys %hosts;
our (%trees) = util::load_hash("$WEBDIR/trees.list");
# these aren't really trees... they're just things we want in the menu.
# (for recent checkins)
our @pseudo_trees = util::load_list("$WEBDIR/pseudo.list");

################################
# get the name of the build file
sub build_fname($$$$)
{
    my ($tree, $host, $compiler, $rev) = @_;
    if ($rev) {
	    return "oldrevs/build.$tree.$host.$compiler-$rev";
    }
    return "build.$tree.$host.$compiler";
}

###################
# the mtime age is used to determine if builds are still happening
# on a host.
# the ctime age is used to determine when the last real build happened

##############################################
# get the age of build from mtime
sub build_age_mtime($$$$)
{
	my ($host, $tree, $compiler, $rev) = @_;
    my $file=build_fname($tree, $host, $compiler, $rev);
    my $age = -1;
    my $st;

    $st = stat("$file.log");
    if ($st) {
		$age = time() - $st->mtime;
    }

    return $age;
}

##############################################
# get the age of build from ctime
sub build_age_ctime($$$$)
{
	my ($host, $tree, $compiler, $rev) = @_;
    my $file = build_fname($tree, $host, $compiler, $rev);
    my $age = -1;
    my $st;

    $st = stat("$file.log");
    if ($st) {
		$age = time() - $st->ctime;
    }

    return $age;
}

##############################################
# get the svn revision of build
sub build_revision($$$$)
{
	my ($host, $tree, $compiler, $rev) = @_;
    my $file = build_fname($tree, $host, $compiler, $rev);
    my $log;
    my $ret = 0;

    if ($rev) {
	    return $rev;
    }

    my $st1 = stat("$file.log");

    if (!$st1) {
	    return $ret;
    }
    my $st2 = stat("$CACHEDIR/$file.revision");

    # the ctime/mtime asymmetry is needed so we don't get fooled by
    # the mtime update from rsync 
    if ($st1 && $st2 && $st1->ctime <= $st2->mtime) {
	    return util::FileLoad("$CACHEDIR/$file.revision");
    }

    $log = util::FileLoad("$file.log");

    if ($log =~ /BUILD REVISION:(.*)/) {
	$ret = $1;
    }

    util::FileSave("$CACHEDIR/$file.revision", $ret);

    return $ret;
}

##############################################
# get status of build
sub build_status($$$$)
{
	my ($host, $tree, $compiler, $rev) = @_;
    my $file = build_fname($tree, $host, $compiler, $rev);
    my $cachefile="$CACHEDIR/$file.status";
    my ($cstatus, $bstatus, $istatus, $tstatus, $sstatus, $dstatus);
    $cstatus = $bstatus = $istatus = $tstatus = $sstatus = $dstatus = 
      span({-class=>"status unknown"}, "?");

    my $st1 = stat("$file.log");
    if (!$st1) {
	    return "Unknown Build";
    }
    my $st2 = stat($cachefile);

    if ($st1 && $st2 && $st1->ctime <= $st2->mtime) {
		return util::FileLoad($cachefile);
    }

    my $log = util::FileLoad("$file.log");

	sub span_status($)
	{
		my $st = shift;
		if ($st == 0) {
	    	return span({-class=>"status passed"}, "ok");
		} else {
			return span({-class=>"status failed"}, $st);
		}
	}

    if ($log =~ /TEST STATUS:(.*)/) {
		$tstatus = span_status($1);
    }
    
    if ($log =~ /INSTALL STATUS:(.*)/) {
		$istatus = span_status($1);
    }
    
    if ($log =~ /BUILD STATUS:(.*)/) {
		$bstatus = span_status($1);
    }

    if ($log =~ /CONFIGURE STATUS:(.*)/) {
		$cstatus = span_status($1);
    }
    
    if ($log =~ /(PANIC|INTERNAL ERROR):.*/ ) {
	$sstatus = "/".span({-class=>"status panic"}, "PANIC");
    } else {
	$sstatus = "";
    }

    if ($log =~ /No space left on device.*/ ) {
	$dstatus = "/".span({-class=>"status failed"}, "disk full");
    } else {
	$dstatus = "";
    }

    if ($log =~ /CC_CHECKER STATUS: (.*)/ && $1 > 0) {
	$sstatus .= "/".span({-class=>"status checker"}, $1);
    }

    my $ret = "$cstatus/$bstatus/$istatus/$tstatus$sstatus$dstatus";

    util::FileSave("$cachefile", $ret);

    return $ret;
}

##############################################
# get status of build
sub lcov_status($)
{
    my ($tree) = @_;
    my $cachefile="$CACHEDIR/lcov.$LCOVHOST.$tree.status";
    my $file = "$LCOVDIR/$LCOVHOST/$tree/index.html";
    my $st1 = stat($file);
    if (!$st1) {
	    return "";
    }
    my $st2 = stat($cachefile);

    if ($st1 && $st2 && $st1->ctime <= $st2->mtime) {
	return util::FileLoad($cachefile);
    }

    my $ret;
    my $lcov_html = util::FileLoad($file);
    if ($lcov_html =~ /\<td class="headerItem".*?\>Code\&nbsp\;covered\:\<\/td\>.*?\n.*?\<td class="headerValue".*?\>([0-9.]+) \%/) {
    
	$ret = '<a href="/lcov/data/'."$LCOVHOST/$tree\">$1 %</a>";
    }  else {
	$ret = "";
    }
    util::FileSave("$cachefile", $ret);
    return $ret;
}

##############################################
# get status of build
sub err_count($$$$)
{
    my ($host, $tree, $compiler, $rev) = @_;
    my $file = build_fname($tree, $host, $compiler, $rev);
    my $err;

    my $st1 = stat("$file.err");
    if ($st1) {
	    return 0;
    }
    my $st2 = stat("$CACHEDIR/$file.errcount");

    if ($st1 && $st2 && $st1->ctime <= $st2->mtime) {
	    return util::FileLoad("$CACHEDIR/$file.errcount");
    }

    $err = util::FileLoad("$file.err") or return 0;

    my $ret = util::count_lines($err);

    util::FileSave("$CACHEDIR/$file.errcount", "$ret");

    return $ret;
}

##############################################
# read full log file
sub read_log($$$$)
{
    my ($tree, $host, $compiler, $rev) = @_;

	return util::FileLoad(build_fname($tree, $host, $compiler, $rev).".log");
}

##############################################
# read full err file
sub read_err($$$$)
{
    my ($tree, $host, $compiler, $rev) = @_;

	return util::FileLoad(build_fname($tree, $host, $compiler, $rev).".err");
}

###########################################
# get a list of old builds and their status
sub get_old_revs($$$)
{
    my ($tree, $host, $compiler) = @_;
    my @list = split('\n', `ls oldrevs/build.$tree.$host.$compiler-*.log`);
    my %ret;
    for my $l (@list) {
	    if ($l =~ /-(\d+).log$/) {
		    my $rev = $1;
		    $ret{$rev} = build_status($host, $tree, $compiler, $rev);
	    }
    }

    return %ret;
}

1;
