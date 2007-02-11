#!/usr/bin/perl -w
# This CGI script presents the results of the build_farm build
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

# TODO: Allow filtering of the "Recent builds" list to show
# e.g. only broken builds or only builds that you care about.


use strict qw{vars};
use FindBin qw($RealBin);

use lib "$RealBin";
use util;
use history;
use POSIX;
use Data::Dumper;
use CGI qw/:standard/;
use File::stat;

my $WEBDIR = "$RealBin";
my $BASEDIR = "$WEBDIR/..";
my $CACHEDIR = "$WEBDIR/../cache";

my $req = new CGI;

my $OLDAGE = 60*60*4;
my $DEADAGE = 60*60*24*4;

##############################################
# this defines what it is possible to build 
# and what boxes. Should be in a config file
my @compilers = util::load_list("$WEBDIR/compilers.list");
my (%hosts) = util::load_hash("$WEBDIR/hosts.list");
my @hosts = sort { $hosts{$a} cmp $hosts{$b} } keys %hosts;
my (%trees) = util::load_hash("$WEBDIR/trees.list");
# these aren't really trees... they're just things we want in the menu.
# (for recent checkins)
my @pseudo_trees = util::load_list("$WEBDIR/pseudo.list");

# this is automatically filled in
my (@deadhosts) = ();

###############################################
# URL so I can refer to myself in links
my $myself = $req->url();

################################################
# start CGI headers
sub cgi_headers() {
	print header;
	print start_html(-title => 'samba.org build farm',
		    -script => {-language=> 'JAVASCRIPT', -src=>"/build_farm.js" },
			-meta => {
				-keywords => "Samba SMB CIFS Build Farm",
				-description => "Home of the Samba Build Farm, the automated testing facility.",
				-robots => "noindex"
			},
			-lang => "en-us",
			-head => [
				Link({-rel => "stylesheet",
					  -href => "build_farm.css",
					  -type => "text/css",
					  -media => "all"}),
			    Link({-rel => "stylesheet",
					  -href => "http://master.samba.org/samba/style/common.css",
					  -type => "text/css",
					  -media => "all"}),
			    Link({-rel=>"shortcut icon",
					  -href=>"http://www.samba.org/samba/images/favicon.ico"})
			  ]
		);

    print util::FileLoad("$BASEDIR/web/header2.html");
    main_menu();
    print util::FileLoad("$BASEDIR/web/header3.html");
}

################################################
# end CGI
sub cgi_footers() {
	print util::FileLoad("$BASEDIR/web/footer.html");
	print $req->end_html;
}

################################################
# print an error on fatal errors
sub fatal($) {
    my $msg = shift;

    cgi_headers();
    print $req->h1("ERROR: $msg");
    cgi_footers();
    exit(0);
}

################################################
# get a param from the request, after sanitizing it
sub get_param($) {
    my $param = shift;

    if (!defined $req->param($param)) {
		return wantarray ? () : undef;
    }

    my @result = ();
    if (wantarray) {
	    @result = $req->param($param);
    } else {
	    $result[0] = $req->param($param);
    }

    for (my $i = 0; $i <= $#result; $i++) {
	    $result[$i] =~ s/ /_/g;
    }

    foreach (@result) {
	    if ($_ =~ m/[^a-zA-Z0-9\-\_\.]/) {
		    fatal("Parameter $param is invalid");
		    return wantarray ? () : undef;
	    }
    }

    return wantarray ? @result : $result[0];
}

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

    util::FileSave("$CACHEDIR/$file.revision", "$ret");

    return $ret;
}

#############################################
# get the overall age of a host
sub host_age($)
{
	my $host = shift;
	my $ret = -1;
	for my $compiler (@compilers) {
		for my $tree (keys %trees) {
			my $age = build_age_mtime($host, $tree, $compiler, "");
			if ($age != -1 && ($age < $ret || $ret == -1)) {
				$ret = $age;
			}
		}
	}
	return $ret;
}

#############################################
# show an age as a string
sub red_age($)
{
	my $age = shift;

	if ($age > $OLDAGE) {
		return sprintf("<span class=\"old\">%s</span>",  util::dhm_time($age));
	}
	return util::dhm_time($age);
}

##############################################
# get status of build
sub build_status($$$$)
{
	my ($host, $tree, $compiler, $rev) = @_;
    my $file = build_fname($tree, $host, $compiler, $rev);
    my $cachefile="$CACHEDIR/" . $file . ".status";
    my ($cstatus, $bstatus, $istatus, $tstatus, $sstatus, $dstatus);
    $cstatus = $bstatus = $istatus = $tstatus = $sstatus = $dstatus = 
      "<span class=\"status unknown\">?</span>";

    my $log;
    my $ret;

    my $st1 = stat("$file.log");
    if (!$st1) {
	    return "Unknown Build";
    }
    my $st2 = stat("$cachefile");

    if ($st1 && $st2 && $st1->ctime <= $st2->mtime) {
		return util::FileLoad($cachefile);
    }

    $log = util::FileLoad("$file.log");

    if ($log =~ /TEST STATUS:([0-9]+)/) {
	if ($1 == 0) {
	    $tstatus = "<span class=\"status passed\">ok</span>";
	} else {
	    $tstatus = "<span class=\"status failed\">$1</span>";
	}
    }
    
    if ($log =~ /INSTALL STATUS:(.*)/) {
	if ($1 == 0) {
	    $istatus = "<span class=\"status passed\">ok</span>";
	} else {
	    $istatus = "<span class=\"status failed\">$1</span>";
	}
    }
    
    if ($log =~ /BUILD STATUS:(.*)/) {
	if ($1 == 0) {
	    $bstatus = "<span class=\"status passed\">ok</span>";
	} else {
	    $bstatus = "<span class=\"status failed\">$1</span>";
	}
    }

    if ($log =~ /CONFIGURE STATUS:(.*)/) {
	if ($1 == 0) {
	    $cstatus = "<span class=\"status passed\">ok</span>";
	} else {
	    $cstatus = "<span class=\"status failed\">$1</span>";
	}
    }
    
    if ($log =~ /(PANIC|INTERNAL ERROR):.*/ ) {
	$sstatus = "/<span class=\"status panic\">PANIC</span>";
    } else {
	$sstatus = "";
    }

    if ($log =~ /No space left on device.*/ ) {
	$dstatus = "/<span class=\"status failed\">disk full</span>";
    } else {
	$dstatus = "";
    }

    if ($log =~ /CC_CHECKER STATUS: (.*)/ && $1 > 0) {
	$sstatus .= "/<span class=\"status checker\">$1</span>";
    }

    $ret = "<a href=\"$myself?function=View+Build;host=$host;tree=$tree;compiler=$compiler";
    if ($rev) {
	    $ret .= ";revision=$rev";
    }
    $ret .= "\">$cstatus/$bstatus/$istatus/$tstatus$sstatus$dstatus</a>";

    util::FileSave("$CACHEDIR/$file.status", $ret);

    return $ret;
}

##############################################
# translate a status into a set of int representing status
sub build_status_vals($) {
    my $status = util::strip_html(shift);

    $status =~ s/ok/0/g;
    $status =~ s/\?/0/g;
    $status =~ s/PANIC/1/g;

    return split m%/%, $status;
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
# view build summary
sub view_summary($) {
    my $i = 0;
    my $list = `ls *.log`;
    my $cols = 2;
    my $broken = 0;

    # either "text" or anything else.
    my $output_type = shift;

    # set up counters
    my %broken_count;
    my %panic_count;
    my %host_count;

    # zero broken and panic counters
    for my $tree (keys %trees) {
		$broken_count{$tree} = 0;
		$panic_count{$tree} = 0;
		$host_count{$tree} = 0;
    }

    # set up a variable to store the broken builds table's code, so we can output when we want
    my $broken_table = "";
    my $host_os;
    my $last_host = "";

    # for the text report, include the current time
    if ($output_type eq 'text') {
	    my $time = gmtime();
	    print "Build status as of $time\n\n";
    }

    for my $host (@hosts) {
	    for my $compiler (@compilers) {
		    for my $tree (keys %trees) {
			    my $status = build_status($host, $tree, $compiler, "");
			    next if $status =~ /^Unknown Build/;
			    my $age_mtime = build_age_mtime($host, $tree, $compiler, "");
			    
			    if ($age_mtime != -1 && $age_mtime < $DEADAGE) {
				    $host_count{$tree}++;
			    }

			    if ($age_mtime < $DEADAGE && $status =~ /status failed/) {
				    $broken_count{$tree}++;
				    if ($status =~ /PANIC/) {
					    $panic_count{$tree}++;
				    }
			    }
		    }
	    }
    }

    if ($output_type eq 'text') {
	    print "Build counts:\n";
	    printf "%-12s %-6s %-6s %-6s\n", "Tree", "Total", "Broken", "Panic";
    }
    else {
	    print $req->start_div(-id=>"build-counts", -class=>"build-section");
		print $req->h2('Build counts:');
		print $req->start_table({-class => "real"}),
			  $req->thead(
				  $req->Tr($req->th("Tree"), $req->th("Total"), 
					       $req->th("Broken"), $req->th("Panic"))),
		      $req->start_tbody;
    }

    for my $tree (sort keys %trees) {
	    if ($output_type eq 'text') {
		    printf "%-12s %-6s %-6s %-6s\n", $tree, $host_count{$tree},
			    $broken_count{$tree}, $panic_count{$tree};
	    } else {
			print $req->start_Tr;
			print $req->td($req->a({-href=>"$myself?function=Recent+Builds;tree=$tree",
					       -title=>"View recent builds for $tree"}, $tree));
			print $req->td($host_count{$tree});
			print $req->td($broken_count{$tree});
		    my $panic = "";
		    if ($panic_count{$tree}) {
			    $panic = " class=\"panic\"";
		    }
		    print "<td$panic>$panic_count{$tree}</td>";
			print $req->end_Tr;
	    }
    }

    if ($output_type eq 'text') {
	    print "\n";
    } else {
		print $req->end_tbody, $req->end_table;
		print $req->end_div;
    }
}

##############################################
# Draw the "recent builds" view
sub view_recent_builds() {
    my $i = 0;
    my $cols = 2;
    my $broken = 0;
    my $host_os;
    my $last_host = "";
    my @all_builds = ();

    my $sort = { revision => sub { $$b[6] <=> $$a[6] },
		 age =>      sub { $$a[0] <=> $$b[0] },
		 host =>     sub { $$a[2] cmp $$b[2] },
		 platform => sub { $$a[1] cmp $$b[1] },
		 compiler => sub { $$a[3] cmp $$b[3] },
		 status =>   sub {
			 my (@bstat) = build_status_vals($$b[5]);
			 my (@astat) = build_status_vals($$a[5]);

			 # handle panic
			 if (defined $bstat[4] && !defined $astat[4]) {
				 return 1;
			 } elsif (!defined $bstat[4] && defined $astat[4]) {
				 return -1;
			 }
			 return ($bstat[0] <=> $astat[0] || # configure
				 $bstat[1] <=> $astat[1] || # compile
				 $bstat[2] <=> $astat[2] || # install
				 $bstat[3] <=> $astat[3]    # test
				);
			}
	};

    my $tree = get_param("tree");
    my $sort_by = get_param("sortby") || "revision"; # default to revision

    util::InArray($tree, [keys %trees]) || fatal("not a build tree");
    util::InArray($sort_by, [keys %$sort]) || fatal("not a valid sort");

    for my $host (@hosts) {
      for my $compiler (@compilers) {
	  my $status = build_status($host, $tree, $compiler, "");
	  my $age_mtime = build_age_mtime($host, $tree, $compiler, "");
	  my $age_ctime = build_age_ctime($host, $tree, $compiler, "");
	  my $revision = build_revision($host, $tree, $compiler, "");
	  push @all_builds, [$age_ctime, $hosts{$host}, $req->a({-href=>"$myself?function=View+Host;host=$host;tree=$tree;compiler=$compiler#$host"}, $host), $compiler, $tree, $status, $revision]
	  	unless $age_mtime == -1 or $age_mtime >= $DEADAGE;
      }
    }

    @all_builds = sort { $sort->{$sort_by}() || $sort->{age}() } @all_builds;

    my $sorturl = "$myself?tree=$tree;function=Recent+Builds";

	print $req->start_div(-id=>"recent-builds", -class=>"build-section"),
		  $req->h2("Recent builds of $tree");

	print $req->start_table({-class => "real"}),
	      $req->thead(
			  $req->Tr(
				  $req->th($req->a({-href => "$sorturl;sortby=age",
							        -title => "Sort by build age"}, "Age")),
				  $req->th($req->a({-href => "$sorturl;sortby=revision",
							        -title => "Sort by build revision"},
								    "Revision")),
				  $req->th("Tree"),
				  $req->th($req->a({-href => "$sorturl;sortby=platform",
						           -title => "Sort by platform"}, "Platform")),
				  $req->th($req->a({-href => "$sorturl;sortby=host",
						           -title => "Sort by host"}, "Host")),
				  $req->th($req->a({-href=>"$sorturl;sortby=compiler",
							        -title=>"Sort by compiler"}, "Compiler")),
				  $req->th($req->a({-href=>"$sorturl;sortby=status",
							        -title=>"Sort by build status"}, "Status"))
					)
				),
			$req->start_tbody;

    for my $build (@all_builds) {
	my $age_mtime = $$build[0];
	my $rev = $$build[6];
	print $req->Tr(map($req->td, util::dhm_time($age_mtime),
	       $rev, @$build[4, 1, 2, 3, 5]));
    }
    print $req->end_tbody, $req->end_table;
	print $req->end_div;
}

##############################################
# Draw the "dead hosts" table
sub draw_dead_hosts {
    my $output_type = shift;
    my @deadhosts = @_;

    # don't output anything if there are no dead hosts
    return if ($#deadhosts < 0);

    # don't include in text report
	return if ($output_type eq 'text');

	print $req->start_div(-class => "build-section", -id=>"dead-hosts"),
		  $req->h2('Dead Hosts:');
	print <<EOHEADER;
<table class="real">
<thead>
<tr><th>Host</th><th>OS</th><th>Min Age</th></tr>
</thead>
<tbody>
EOHEADER

    for my $host (@deadhosts) {
	my $age_ctime = host_age($host);
	print "    <tr><td>$host</td><td>$hosts{$host}</td><td>", util::dhm_time($age_ctime), "</td></tr>";
    }

    print "  </tbody>\n</table>\n";
	print $req->end_div;
}

##############################################
# show the available old revisions, if any
sub show_oldrevs($$$)
{
    my ($tree, $host, $compiler) = @_;
    my %revs = get_old_revs($tree, $host, $compiler);
    my @revs = sort { $revs{$b} cmp $revs{$a} } keys %revs;

    return if ($#revs < 1);

    print $req->h2("Older builds:");

    print "
<table class=\"real\">
<tr><th>Revision</th><th>Status</th></tr>
";

    my $lastrev = "";

    for my $rev (@revs) {
	    my $s = $revs{$rev};
	    $s =~ s/$rev/0/;
	    next if ($s eq $lastrev);
	    $lastrev = $s;
	    print "<tr><td>$rev</td><td>$revs{$rev}</td></tr>\n";
    }
    print "</table>\n";
}

##############################################
# view one build in detail
sub view_build() {
    my $tree=get_param("tree");
    my $host=get_param("host");
    my $compiler=get_param("compiler");
    my $rev=get_param('revision');

    # ensure the params are valid before using them
    util::InArray($host, [keys %hosts]) || fatal("unknown host");
    util::InArray($compiler, \@compilers) || fatal("unknown compiler");
    util::InArray($tree, [keys %trees]) || fatal("not a build tree");

    my $file=build_fname($tree, $host, $compiler, $rev);
    my $log;
    my $err;
    my $uname="";
    my $cflags="";
    my $config="";
    my $age_mtime = build_age_mtime($host, $tree, $compiler, $rev);
    my $revision = build_revision($host, $tree, $compiler, $rev);
    my $status = build_status($host, $tree, $compiler, $rev);

    $rev = int($rev) if $rev;

    $log = util::FileLoad("$file.log");
    $err = util::FileLoad("$file.err");
    
    if ($log) {
		$log = escapeHTML($log);

		if ($log =~ /(.*)/) { $uname=$1; }
		if ($log =~ /CFLAGS=(.*)/) { $cflags=$1; }
		if ($log =~ /configure options: (.*)/) { $config=$1; }
    }

    if ($err) {
		$err = escapeHTML($err);
    }

    print $req->h2('Host information:');

    print util::FileLoad("../web/$host.html");

    print "
<table class=\"real\">
<tr><td>Host:</td><td><a href=\"$myself?function=View+Host;host=$host;tree=$tree;compiler=$compiler#$host\">$host</a> - $hosts{$host}</td></tr>
<tr><td>Uname:</td><td>$uname</td></tr>
<tr><td>Tree:</td><td>$tree</td></tr>
<tr><td>Build Revision:</td><td>" . $revision . "</td></tr>
<tr><td>Build age:</td><td class=\"age\">" . red_age($age_mtime) . "</td></tr>
<tr><td>Status:</td><td>$status</td></tr>
<tr><td>Compiler:</td><td>$compiler</td></tr>
<tr><td>CFLAGS:</td><td>$cflags</td></tr>
<tr><td>configure options:  </td><td>$config</td></tr>
</table>
";

    show_oldrevs($tree, $host, $compiler);


    # check the head of the output for our magic string
    my $plain_logs = (defined get_param("plain") &&
		      get_param("plain") =~ /^(yes|1|on|true|y)$/i);
    my $rev_var = "";
    if ($rev) {
	    $rev_var = ";revision=$rev";
    }

    print $req->start_div(-id=>"log");

    if (!$plain_logs) {

	    print $req->p("Switch to the ".$req->a({-href => "$myself?function=View+Build;host=$host;tree=$tree;compiler=$compiler$rev_var;plain=true", -title=> "Switch to bland, non-javascript, unstyled view"}, "Plain View"));

	    print $req->start_div(-id=>"actionList");
	    # These can be pretty wide -- perhaps we need to 
	    # allow them to wrap in some way?
	    if ($err eq "") {
		    print $req->h2("No error log available");
	    } else {
		    print $req->h2("Error log:");
		    print make_collapsible_html('action', "Error Output", "\n$err", "stderr-0");
	    }

	    if ($log eq "") {
		    print $req->h2("No build log available");
	    } else {
		    print $req->h2("Build log:");
		    print_log_pretty($log);
	    }

	    print $req->p("<small>Some of the above icons derived from the <a href=\"http://www.gnome.org\">Gnome Project</a>'s stock icons.");
		print $req->end_div;
    } else {
	    print "<p>Switch to the <a href=\"$myself?function=View+Build;host=$host;tree=$tree;compiler=$compiler$rev_var\" title=\"Switch to colourful, javascript-enabled, styled view \">Enhanced View</a></p>";
	    if ($err eq "") {
		    print $req->h2("No error log available");
	    } else {
		    print $req->h2('Error log:');
		    print $req->div({-id=>"errorLog"}, $req->pre(join('', $err)));
	    }
	    if ($log eq "") {
		    print $req->h2('No build log available');
	    }
	    else {
		    print $req->h2('Build log:');
		    print $req->div({-id=>"buildLog"}, $req->pre(join('', $log)));
	    }
    }

	print $req->end_div;
}

##################################################
# print the host's table of information
sub view_host() {

	my $output_type = "html";

	if ($output_type eq 'text') {
		print "Host summary:\n";
	} else {
		print $req->start_div({-class=>"build-section", -id=>"build-summary"});
		print $req->h2('Host summary:');
	}

	my $list = `ls *.log`;

	my (@requested_hosts) = get_param('host');

	foreach (@requested_hosts) {
		util::InArray($_, [keys %hosts]) || fatal("unknown host");
	}

	for my $host (@requested_hosts) {
		# make sure we have some data from it
		if (! ($list =~ /$host/)) {
			if ($output_type ne 'text') {
				print "<!-- skipping $host -->\n";
			}
			next;
		}

		my $row = 0;

		for my $compiler (@compilers) {
			for my $tree (sort keys %trees) {
				my $revision = build_revision($host, $tree, $compiler, "");
				my $age_mtime = build_age_mtime($host, $tree, $compiler, "");
				my $age_ctime = build_age_ctime($host, $tree, $compiler, "");
				my $warnings = err_count($host, $tree, $compiler, "");
				if ($age_ctime != -1 && $age_ctime < $DEADAGE) {
					my $status = build_status($host, $tree, $compiler, "");
					if ($row == 0) {
						if ($output_type eq 'text') {
							printf "%-12s %-10s %-10s %-10s %-10s\n",
								"Tree", "Compiler", "Build Age", "Status", "Warnings";
                                    
						} else {
							print <<EOHEADER;
<div class="host summary">
  <a id="$host" name="$host" />
  <h3>$host - $hosts{$host}</h3>
  <table class="real">
    <thead>
      <tr>
        <th>Target</th><th>Build<br />Revision</th><th>Build<br />Age</th><th>Status<br />config/build<br />install/test</th><th>Warnings</th>
      </tr>
    </thead>
    <tbody>
EOHEADER
						}
					}

					if ($output_type eq 'text') {
						printf "%-12s %-10s %-10s %-10s %-10s\n",
							$tree, $compiler, util::dhm_time($age_mtime), 
								util::strip_html($status), $warnings;
					} else {
						print "    <tr><td><span class=\"tree\">$tree</span>/$compiler</td><td>$revision</td><td class=\"age\">" . red_age($age_mtime) . "</td><td class=\"status\">$status</td><td>$warnings</td></tr>\n";
					}
					$row++;
				}
			}
		}
		if ($row != 0) {
			if ($output_type eq 'text') {
				print "\n";
			} else {
				print "  </tbody>\n</table>\n";
				print $req->end_div;
			}
		} else {
			push(@deadhosts, $host);
		}
	}

	if ($output_type ne 'text') {
		print $req->end_div;
	}

	draw_dead_hosts($output_type, @deadhosts);
}

##############################################
# prints the log in a visually appealing manner
sub print_log_pretty() {
  my $log = shift;

  # do some pretty printing for the actions
  my $id = 1;
  $log =~ s{ (
             Running\ action\s+([\w\-]+)
	     .*?
	     ACTION\ (PASSED|FAILED):\ ([\w\-]+)
             )
	    }{ my $output = $1;
	       my $actionName = $2;
	       my $status = $3;

	       # handle pretty-printing of static-analysis tools
	       if ($actionName eq 'cc_checker') {
		 $output = print_log_cc_checker($output);
	       }

	       make_collapsible_html('action', $actionName, $output, $id++, 
				     $status)
       }exgs;

  # $log is already CGI-escaped, so handle '>' in test name by handling &gt;
  $log =~ s{
	      --==--==--==--==--==--==--==--==--==--==--.*?
	      Running\ test\ ([\w\-=,_:\ /.&;]+).*?
	      --==--==--==--==--==--==--==--==--==--==--
              (.*?)
	      ==========================================.*?
	      TEST\ (FAILED|PASSED|SKIPPED):.*?
	      ==========================================\s+
	     }{make_collapsible_html('test', $1, $2, $id++, $3)}exgs;

  print $req->tt($req->pre(join('', $log)))."<p>\n";
}

##############################################
# generate pretty-printed html for static analysis tools
sub print_log_cc_checker($) {
  my $input = shift;
  my $output = "";

  # for now, we only handle the IBM Checker's output style
  if ($input !~ m/^BEAM_VERSION/ms) {
    return "here";
    return $input;
  }

  my $content = "";
  my $inEntry = 0;

  my ($entry, $title, $status, $id);

  foreach (split /\n/, $input) {

    # for each line, check if the line is a new entry,
    # otherwise, store the line under the current entry.

    if (m/^-- /) {
      # got a new entry
      if ($inEntry) {
	$output .= make_collapsible_html('cc_checker', $title, $content,
					 $id, $status);
      } else {
	$output .= $content;
      }

      # clear maintenance vars
      ($inEntry, $content) = (1, "");

      # parse the line
      m/^-- ((ERROR|WARNING|MISTAKE).*?)\s+&gt;&gt;&gt;([a-zA-Z0-9]+_(\w+)_[a-zA-Z0-9]+)/;

      # then store the result
      ($title, $status, $id) = ("$1 $4", $2, $3);
    } elsif (m/^CC_CHECKER STATUS/) {
	if ($inEntry) {
	  $output .= make_collapsible_html('cc_checker', $title, $content,
					   $id, $status);
	}

	$inEntry = 0;
	$content = "";
    }

    # not a new entry, so part of the current entry's output
    $content .= "$_\n";
  }
  $output .= $content;

  # This function does approximately the same as the following, following
  # commented-out regular expression except that the regex doesn't quite
  # handle IBM Checker's newlines quite right.
  #   $output =~ s{
  #                 --\ ((ERROR|WARNING|MISTAKE).*?)\s+
  #                        &gt;&gt;&gt;
  #                 (.*?)
  #                 \n{3,}
  #               }{make_collapsible_html('cc_checker', "$1 $4", $5, $3, $2)}exgs;
  return $output;
}

##############################################
# generate html for a collapsible section
sub make_collapsible_html($$$$)
{
  my ($type, # the logical type of it. e.g. "test" or "action"
      $title, # the title to be displayed 
      $output, $id) = @_;
  my $status = (shift or "");

  my $icon = (defined $status && ($status =~ /failed/i)) ? 'icon_hide_16.png' : 'icon_unhide_16.png';

  # trim leading and trailing whitespace
  $output =~ s/^\s+//s;
  $output =~ s/\s+$//s;

  # note that we may be inside a <pre>, so we don't put any extra whitespace in this html
  my $return = $req->div({-class=>"$type unit \L$status\E",
		                  -id=>"$type-$id"},
					  $req->a({-href=>"javascript:handle('$id');"},
						  $req->img(-id=>"img-$id",
							        -name=>"img-$id",
									-src=>$icon),
						  $req->div({-class => "$type title"}, $title),
					  ) . 
					  div({-class=>"$type status \L$status\E"}, $status) .
					  div({-class => "$type output", -id=>"output-$id"},
					  pre($output)));

  return $return
}

##############################################
# main page
sub main_menu() {
    print $req->startform("GET");
	print $req->start_div(-id=>"build-menu");
    print $req->popup_menu(-name=>'host',
			   -values=>\@hosts,
			   -labels=>\%hosts) . "\n";
    print $req->popup_menu("tree", [sort (keys %trees, @pseudo_trees)]) . "\n";
    print $req->popup_menu("compiler", \@compilers) . "\n";
    print $req->br();
    print $req->submit('function', 'View Build') . "\n";
    print $req->submit('function', 'View Host') . "\n";
    print $req->submit('function', 'Recent Checkins') . "\n";
    print $req->submit('function', 'Summary') . "\n";
    print $req->submit('function', 'Recent Builds') . "\n";
	print $req->end_div;
    print $req->endform() . "\n";
}

###############################################
# display top of page
sub page_top() {
    cgi_headers();
    chdir("$BASEDIR/data") || fatal("can't change to data directory");
}

###############################################
# main program

my $fn_name = get_param('function') || '';

if ($fn_name eq 'text_diff') {
  print header('application/x-diff');
  chdir("$BASEDIR/data") || fatal("can't change to data directory");
  history::diff(get_param('author'),
		get_param('date'),
		get_param('tree'),
		get_param('revision'),
		"text");
} elsif ($fn_name eq 'Text_Summary') {
	print header('text/plain');
	chdir("$BASEDIR/data") || fatal("can't change to data directory");
	view_summary('text');
} else {
  page_top();

  if ($fn_name eq "View_Build") {
    view_build();
  } elsif ($fn_name eq "View_Host") {
    view_host();
  } elsif ($fn_name eq "Recent_Builds") {
    view_recent_builds();
  } elsif ($fn_name eq "Recent_Checkins") {
    history::history(get_param('tree'));
  } elsif ($fn_name eq "diff") {
    history::diff(get_param('author'),
		  get_param('date'),
		  get_param('tree'),
		  get_param('revision'),
		  "html");
  } else {
    view_summary('html');
  }
  cgi_footers();
}
