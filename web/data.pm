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
@EXPORT_OK = qw(@hosts %hosts @compilers @pseudo_trees %trees $OLDAGE $DEADAGE);

use strict;
use warnings;

my $WEBDIR = "$RealBin";
my $CACHEDIR = "$WEBDIR/../cache";
my $LCOVDIR = "$WEBDIR/../lcov/data";
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

sub new($;$) {
	my ($this, $path, $readonly) = @_;

	return undef if not (-d $path);
	$readonly = 0 unless defined($readonly);

	my $self = {
		path => $path,
		readonly => $readonly,

		compilers	=> \@compilers,
		hosts_hash	=> \%hosts,
		hosts_list	=> \@hosts,
		trees		=> \%trees,
		pseudo_trees	=> \@pseudo_trees,
		OLDAGE		=> \$OLDAGE,
		DEADAGE 	=> \$DEADAGE
	};

	bless $self;
	return $self;
}

sub cache_fname($$$$$)
{
	my ($self, $tree, $host, $compiler, $rev) = @_;
	if ($rev) {
		return "$CACHEDIR/oldrevs/build.$tree.$host.$compiler-$rev";
	}
	return "$CACHEDIR/build.$tree.$host.$compiler";
}

################################
# get the name of the build file
sub build_fname($$$$$)
{
	my ($self, $tree, $host, $compiler, $rev) = @_;
	if ($rev) {
		return "$self->{path}/oldrevs/build.$tree.$host.$compiler-$rev";
	}
	return "$self->{path}/build.$tree.$host.$compiler";
}

###################
# the mtime age is used to determine if builds are still happening
# on a host.
# the ctime age is used to determine when the last real build happened

##############################################
# get the age of build from mtime
sub build_age_mtime($$$$$)
{
	my ($self, $host, $tree, $compiler, $rev) = @_;
	my $file=$self->build_fname($tree, $host, $compiler, $rev);
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
sub build_age_ctime($$$$$)
{
	my ($self, $host, $tree, $compiler, $rev) = @_;
	my $file = $self->build_fname($tree, $host, $compiler, $rev);
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
sub build_revision_details($$$$$)
{
	my ($self, $host, $tree, $compiler, $rev) = @_;
	my $file = $self->build_fname($tree, $host, $compiler, $rev);
	my $cachef = $self->cache_fname($tree, $host, $compiler, $rev);
	my $log;
	my $ret = 0;

	# don't fast-path for trees with git repository:
	# we get the timestamp as rev and want the details
	if ($rev && ($tree ne "samba_3_2_test")) {
		return $rev;
	}

	my $st1 = stat("$file.log");

	if (!$st1) {
		return $ret;
	}
	my $st2 = stat("$cachef.revision");

	# the ctime/mtime asymmetry is needed so we don't get fooled by
	# the mtime update from rsync 
	if ($st1 && $st2 && $st1->ctime <= $st2->mtime) {
		return util::FileLoad("$cachef.revision");
	}

	$log = util::FileLoad("$file.log");

	if ($log =~ /BUILD COMMIT REVISION: (.*)/) {
		$ret = $1;
	} elsif ($log =~ /BUILD REVISION: (.*)/) {
		$ret = $1;
	}

	if ($log =~ /BUILD COMMIT TIME: (.*)/) {
		$ret .= ":".$1;
	}

	util::FileSave("$cachef.revision", $ret) unless $self->{readonly};

	return $ret;
}

sub build_revision($$$$$)
{
	my ($self, $host, $tree, $compiler, $rev) = @_;

	my $r = $self->build_revision_details($host, $tree, $compiler, $rev);

	$r =~ s/:.*//;

	return $r;
}

sub build_revision_time($$$$$)
{
	my ($self, $host, $tree, $compiler, $rev) = @_;

	my $r = $self->build_revision_details($host, $tree, $compiler, $rev);

	$r =~ s/^[^:]*://;

	return $r;
}

##############################################
# get status of build
sub build_status($$$$$)
{
	my ($self, $host, $tree, $compiler, $rev) = @_;
	my $file = $self->build_fname($tree, $host, $compiler, $rev);
	my $cachefile = $self->cache_fname($tree, $host, $compiler, $rev).".status";
	my ($cstatus, $bstatus, $istatus, $tstatus, $sstatus, $dstatus, $tostatus);
	$cstatus = $bstatus = $istatus = $tstatus = $sstatus = $dstatus = $tostatus =
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
	my $err = util::FileLoad("$file.err");

	sub span_status($)
	{
		my $st = shift;
		if ($st == 0) {
			return span({-class=>"status passed"}, "ok");
		} else {
			return span({-class=>"status failed"}, $st);
		}
	}

	if ($log =~ /ACTION FAILED: test/) {
		$tstatus = span_status(255);
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

	if ($err =~ /No space left on device.*/ ) {
		$dstatus = "/".span({-class=>"status failed"}, "disk full");
	} elsif ($log =~ /No space left on device.*/ ) {
		$dstatus = "/".span({-class=>"status failed"}, "disk full");
	} else {
		$dstatus = "";
	}

	if ($log =~ /maximum runtime exceeded.*/ ) {
		$tostatus = "/".span({-class=>"status failed"}, "timeout");    
	} else {
		$tostatus = "";
	}

	if ($log =~ /CC_CHECKER STATUS: (.*)/ && $1 > 0) {
		$sstatus .= "/".span({-class=>"status checker"}, $1);
	}

	my $ret = "$cstatus/$bstatus/$istatus/$tstatus$sstatus$dstatus$tostatus";

	util::FileSave("$cachefile", $ret) unless $self->{readonly};

	return $ret;
}

##############################################
# get status of build
sub lcov_status($$)
{
	my ($self, $tree) = @_;
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
	} else {
		$ret = "";
	}
	util::FileSave("$cachefile", $ret) unless $self->{readonly};
	return $ret;
}

##############################################
# get status of build
sub err_count($$$$$)
{
	my ($self, $host, $tree, $compiler, $rev) = @_;
	my $file = $self->build_fname($tree, $host, $compiler, $rev);
	my $cachef = $self->cache_fname($tree, $host, $compiler, $rev);
	my $err;

	my $st1 = stat("$file.err");
	if ($st1) {
		return 0;
	}
	my $st2 = stat("$cachef.errcount");

	if ($st1 && $st2 && $st1->ctime <= $st2->mtime) {
		return util::FileLoad("$cachef.errcount");
	}

	$err = util::FileLoad("$file.err") or return 0;

	my $ret = util::count_lines($err);

	util::FileSave("$cachef.errcount", "$ret") unless $self->{readonly};

	return $ret;
}

##############################################
# read full log file
sub read_log($$$$$)
{
	my ($self, $tree, $host, $compiler, $rev) = @_;

	return util::FileLoad($self->build_fname($tree, $host, $compiler, $rev).".log");
}

##############################################
# read full err file
sub read_err($$$$$)
{
	my ($self, $tree, $host, $compiler, $rev) = @_;

	return util::FileLoad($self->build_fname($tree, $host, $compiler, $rev).".err");
}

###########################################
# get a list of old builds and their status
sub get_old_revs($$$$)
{
	my ($self, $tree, $host, $compiler) = @_;
	my @list = split('\n', `ls $self->{path}/oldrevs/build.$tree.$host.$compiler-*.log`);
	my %ret;
	for my $l (@list) {
		if ($l =~ /-(\d+).log$/) {
			my $rev = $1;
			$ret{$rev} = $self->build_status($host, $tree, $compiler, $rev);
		}
	}

	return %ret;
}

sub has_host($$)
{
	my ($self, $host) = @_;

	my $ls = `ls $self->{path}/*.log`;

	return 1 if ($ls =~ /$host/);
	return 0;
}

1;
