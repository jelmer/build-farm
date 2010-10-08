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
		'ccache' => {
			'scm' => 'git',
			'repo' => 'ccache',
			'branch' => 'master',
			'subdir' => '',
			'srcdir' => ''
		},
		'ccache-maint' => {
			'scm' => 'git',
			'repo' => 'ccache',
			'branch' => 'maint',
			'subdir' => '',
			'srcdir' => ''
		},
		'ppp' => {
			'scm' => 'git',
			'repo' => 'ppp',
			'branch' => 'master',
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
			'branch' => 'v3-5-test',
			'subdir' => '',
			'srcdir' => 'source'
		},
		'samba_3_next' => {
			'scm' => 'git',
			'repo' => 'samba.git',
			'branch' => 'v3-6-test',
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
			'srcdir' => 'source4'
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
		return "$self->{cachedir}/build.$tree.$host.$compiler-$rev";
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
	return "$self->{datadir}/upload/build.$tree.$host.$compiler";
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
sub build_status_from_logs($$)
{
        my ($self, $log, $err) = @_;
	my ($cstatus, $bstatus, $istatus, $tstatus, $sstatus, $dstatus, $tostatus);
	$cstatus = $bstatus = $istatus = $tstatus = $sstatus = $dstatus = $tostatus =
		span({-class=>"status unknown"}, "?");


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
		my $test_successes = 0;
		$test_successes++ while $log =~ m/testsuite-success: /g;
		if ($test_successes > 0) {
			$tstatus = span_status($test_failures);
		} else {
			$tstatus = span_status(255);			
		}
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

	return "$cstatus/$bstatus/$istatus/$tstatus$sstatus$dstatus$tostatus";
}

##############################################
# get status of build
sub build_status($$$$$)
{
	my ($self, $host, $tree, $compiler, $rev) = @_;
	my $file = $self->build_fname($tree, $host, $compiler, $rev);
	my $cachefile = $self->cache_fname($tree, $host, $compiler, $rev).".status";
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

	my $ret = $self->build_status_from_logs($log, $err);

	util::FileSave("$cachefile", $ret) unless $self->{readonly};

	return $ret;
}

#####################################t#
# find the build status as an perl object
# the 'value' gets one point for passing each stage
sub build_status_info_from_string($$$)
{
	my ($self, $rev_seq, $rev, $status_raw) = @_;
	my @status_split = split("/", $status_raw);
	my $status_str = "";
	my @status_arr = ();
	my $status_val = 0;
	my $status = undef;

	foreach my $r (@status_split) {
		$r =~ s/^\s+//;
		$r =~ s/\s+$//;

		my $e;
		if ($r eq "ok") {
			$e = 0;
		} elsif ($r =~ /(\d+)/) {
			$e = $1;
			$e = 1 unless defined($e);
			$e = 1 unless $e > 0;
		} else {
			$e = 1;
		}

		$status_str .= "/" unless $status_str eq "";
		$status_str .= $r;

		$status_val += $e;

		push(@status_arr, $e);
	}

	$status->{rev}		= $rev;
	$status->{rev_seq}	= $rev_seq;
	$status->{array}	= \@status_arr;
	$status->{string}	= $status_str;
	$status->{value}	= $status_val;

	return $status;
}

#####################################t#
# find the build status as an perl object
# the 'value' gets one point for passing each stage
sub build_status_info_from_html($$$)
{
	my ($self, $rev_seq, $rev, $status_html) = @_;
	my $status_raw = util::strip_html($status_html);
	return $self->build_status_info_from_string($rev_seq, $rev, $status_raw);
}

#####################################t#
# find the build status as an perl object
# the 'value' gets one point for passing each stage
sub build_status_info($$$$)
{
	my ($self, $host, $tree, $compiler, $rev_seq) = @_;
	my $rev = $self->build_revision($host, $tree, $compiler, $rev_seq);
	my $status_html = $self->build_status($host, $tree, $compiler, $rev_seq);
	return $self->build_status_info_from_html($rev_seq, $rev, $status_html)
}

sub status_info_cmp($$$)
{
	my ($self, $s1, $s2) = @_;
	my @a1 = @{$s1->{array}};
	my @a2 = @{$s2->{array}};
	my $c1 = 0;
	my $c2 = 0;

	for (my $i = 0; ; $i++) {
		$c1++ if defined($a1[$i]);
		$c2++ if defined($a2[$i]);
		last unless defined($a1[$i]);
		last unless defined($a2[$i]);

		return $c2 - $c1 if ($c1 != $c2);

		return $a2[$i] - $a1[$i] if ($a1[$i] != $a2[$i]);
	}

	return $s2->{value} - $s1->{value};
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

	my $directory = $self->{datadir}."/oldrevs";
	opendir(DIR, $directory) || die "can't opendir $directory: $!";
	my @list = (grep { /^build\.$tree\.$host\.$compiler-.*\.log$/ } readdir(DIR));
	closedir DIR;
	my @ret;
	for my $l (@list) {
		if ($l =~ /-([0-9A-Fa-f]+).log$/) {
			my $rev = $1;
			my $r;
			my $stat = stat($directory . "/" . $l);
			# skip the current build
			$stat->nlink == 2 && next;
			$r->{STATUS} = $self->build_status($host, $tree, $compiler, $rev);
			$r->{REVISION} = $rev;
			$r->{TIMESTAMP} = $stat->ctime;
			push(@ret, $r);			
		}
	}

	@ret = sort { return $b->{TIMESTAMP} - $a->{TIMESTAMP} } @ret;

	return @ret;
}

sub has_host($$)
{
	my ($self, $host) = @_;
	my $directory = $self->{datadir}."/upload";
	opendir(DIR, $directory) || die "can't opendir $directory: $!";
	if (grep { /$host/ } readdir(DIR)) {
		return 1;
	} else {
		return 0;
	}
}

1;
