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

require Exporter;
@ISA = qw(Exporter);
@EXPORT_OK = qw();

use strict;
use warnings;

sub new($;$) {
	my ($this, $basedir, $readonly) = @_;

	return undef if not (-d $basedir);
	$readonly = 0 unless defined($readonly);

	my $webdir = "$basedir/web";
	return undef if not (-d $webdir);

	my $datadir = "$basedir/data";
	return undef if not (-d $datadir);

	my $cachedir = "$basedir/cache";
	return undef if not (-d $cachedir);

	my $lcovdir = "$basedir/lcov/data";
	return undef if not (-d $lcovdir);

	my $lcovhost = "magni";

	my @compilers = util::load_list("$webdir/compilers.list");
	my (%hosts) = util::load_hash("$webdir/hosts.list");
	my @hosts = sort { $hosts{$a} cmp $hosts{$b} } keys %hosts;

	my (%trees) = (
		'distcc' => {
			'scm' => 'cvs',
			'repo' => 'distcc',
			'branch' => 'HEAD',
			'subdir' => '',
			'srcdir' => ''
		},
		'ccache' => {
			'scm' => 'cvs',
			'repo' => 'ccache',
			'branch' => 'HEAD',
			'subdir' => '',
			'srcdir' => ''
		},
		'ppp' => {
			'scm' => 'cvs',
			'repo' => 'ppp',
			'branch' => 'HEAD',
			'subdir' => '',
			'srcdir' => ''
		},
		'build_farm' => {
			'scm' => 'svn',
			'repo' => 'build-farm',
			'branch' => 'trunk',
			'subdir' => '',
			'srcdir' => ''
		},
		'samba-web' => {
			'scm' => 'svn',
			'repo' => 'samba-web',
			'branch' => 'trunk',
			'subdir' => '',
			'srcdir' => ''
		},
		'samba-docs' => {
			'scm' => 'svn',
			'repo' => 'samba-docs',
			'branch' => 'trunk',
			'subdir' => '',
			'srcdir' => ''
		},
		'lorikeet' => {
			'scm' => 'svn',
			'repo' => 'lorikeeet',
			'branch' => 'trunk',
			'subdir' => '',
			'srcdir' => ''
		},
		'samba_3_current' => {
			'scm' => 'git',
			'repo' => 'samba.git',
			'branch' => 'v3-3-test',
			'subdir' => '',
			'srcdir' => 'source'
		},
		'samba_3_next' => {
			'scm' => 'git',
			'repo' => 'samba.git',
			'branch' => 'v3-4-test',
			'subdir' => '',
			'srcdir' => 'source'
		},
		'samba_3_master' => {
			'scm' => 'git',
			'repo' => 'samba.git',
			'branch' => 'master',
			'subdir' => '',
			'srcdir' => 'source'
		},
		'samba_4_0_test' => {
			'scm' => 'git',
			'repo' => 'samba.git',
			'branch' => 'master',
			'subdir' => '',
			'srcdir' => 'source'
		},
		'libreplace' => {
			'scm' => 'git',
			'repo' => 'samba.git',
			'branch' => 'master',
			'subdir' => 'lib/replace/',
			'srcdir' => ''
		},
		'talloc' => {
			'scm' => 'git',
			'repo' => 'samba.git',
			'branch' => 'master',
			'subdir' => 'lib/talloc/',
			'srcdir' => ''
		},
		'tdb' => {
			'scm' => 'git',
			'repo' => 'samba.git',
			'branch' => 'master',
			'subdir' => 'lib/tdb/',
			'srcdir' => ''
		},
		'ldb' => {
			'scm' => 'git',
			'repo' => 'samba.git',
			'branch' => 'master',
			'subdir' => 'lib/ldb/',
			'srcdir' => ''
		},
		'pidl' => {
			'scm' => 'git',
			'repo' => 'samba.git',
			'branch' => 'master',
			'subdir' => 'pidl/',
			'srcdir' => ''
		},
		'rsync' => {
			'scm' => 'git',
			'repo' => 'rsync.git',
			'branch' => 'HEAD',
			'subdir' => '',
			'srcdir' => ''
		}
	);

	my $self = {
		basedir		=> $basedir,
		webdir		=> $webdir,
		datadir		=> $datadir,
		cachedir	=> $cachedir,
		lcovdir		=> $lcovdir,
		lcovhost	=> $lcovhost,

		readonly	=> $readonly,

		compilers	=> \@compilers,
		hosts_hash	=> \%hosts,
		hosts_list	=> \@hosts,
		trees		=> \%trees,
		OLDAGE		=> 60*60*4,
		DEADAGE 	=> 60*60*24*4
	};

	bless $self;
	return $self;
}

sub cache_fname($$$$$)
{
	my ($self, $tree, $host, $compiler, $rev) = @_;
	if ($rev) {
		return "$self->{cachedir}/oldrevs/build.$tree.$host.$compiler-$rev";
	}
	return "$self->{cachedir}/build.$tree.$host.$compiler";
}

################################
# get the name of the build file
sub build_fname($$$$$)
{
	my ($self, $tree, $host, $compiler, $rev) = @_;
	if ($rev) {
		return "$self->{datadir}/oldrevs/build.$tree.$host.$compiler-$rev";
	}
	return "$self->{datadir}/build.$tree.$host.$compiler";
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
	if ($rev) {
		my %trees = %{$self->{trees}};
		my $t = $trees{$tree};
		return $rev unless defined($t);
		return $rev unless $t->{scm} eq "git";
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
	$err = "" unless defined($err);

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
	} elsif ($log =~ /ACTION (PASSED|FAILED): test/) {
		my $test_failures = 0;
		$test_failures++ while $log =~ m/testsuite-(failure|error): /g;
		$tstatus = span_status($test_failures);
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
	my $cachefile="$self->{cachedir}/lcov.$self->{lcovhost}.$tree.status";
	my $file = "$self->{lcovdir}/$self->{lcovhost}/$tree/index.html";
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
		$ret = '<a href="/lcov/data/'."$self->{lcovhost}/$tree\">$1 %</a>";
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
	my @list = split('\n', `ls $self->{datadir}/oldrevs/build.$tree.$host.$compiler-*.log`);
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

	my $ls = `ls $self->{datadir}/*.log`;

	return 1 if ($ls =~ /$host/);
	return 0;
}

1;
