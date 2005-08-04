#!/usr/bin/perl -w
# This CGI script presents the results of the build_farm build
#
# Copyright (C) Andrew Tridgell <tridge@samba.org>     2001-2005
# Copyright (C) Andrew Bartlett <abartlet@samba.org>   2001
# Copyright (C) Vance Lankhaar  <vance@samba.org>      2002-2005
# Copyright (C) Martin Pool <mbp@samba.org>            2001
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
use CGI;
use File::stat;

my $WEBDIR = "$RealBin";
my $BASEDIR = "$WEBDIR/..";
my $CACHEDIR = "$WEBDIR/../cache";

my $req = new CGI;

my $HEADCOLOR = "#a0a0e0";
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
# work out a URL so I can refer to myself in links
my $myself = $req->self_url;
if ($myself =~ /(.*)[?].*/) {
    $myself = $1;
}
if ($myself =~ /http:\/\/.*\/(.*)/) {
    $myself = $1;
}

# for now, hard code the self url - need to sanitize self_url
$myself = "http://build.samba.org/";

my $cgi_headers_done = 0;

################################################
# start CGI headers
sub cgi_headers() {
    if ($cgi_headers_done) {
	return;
    }
    $cgi_headers_done = 1;

    print "Content-type: text/html\r\n";
    #print "Content-type: application/xhtml+xml\r\n";

    util::cgi_gzip();

    print util::FileLoad("$BASEDIR/web/header.html");
    print '<title>samba.org build farm</title>';
    print util::FileLoad("$BASEDIR/web/header2.html");
    main_menu();
    print util::FileLoad("$BASEDIR/web/header3.html");
}

################################################
# start CGI headers for diffs
sub cgi_headers_diff() {
    print "Content-type: application/x-diff\r\n";
    print "\n";
}

################################################
# start CGI headers for text output
sub cgi_headers_text() {
	print "Content-type: text/plain\r\n";
	print "\r\n";
}

################################################
# end CGI
sub cgi_footers() {
  print util::FileLoad("$BASEDIR/web/footer.html");
}

################################################
# print an error on fatal errors
sub fatal($) {
    my $msg=shift;

    cgi_headers();
    print "<h1>ERROR: $msg</h1>\n";
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
    }
    else {
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
    my $tree=shift;
    my $host=shift;
    my $compiler=shift;
    my $rev=shift;
    if ($rev) {
	    return "oldrevs/build.$tree.$host.$compiler-$rev";
    }
    return "build.$tree.$host.$compiler";
}

###########################################
# get a list of old builds and their status
sub get_old_revs($$$)
{
    my $tree=shift;
    my $host=shift;
    my $compiler=shift;
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

##############################################
# get the age of build from mtime
sub build_age($$$$)
{
    my $host=shift;
    my $tree=shift;
    my $compiler=shift;
    my $rev=shift;
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
# get the svn revision of build
sub build_revision($$$$)
{
    my $host=shift;
    my $tree=shift;
    my $compiler=shift;
    my $rev=shift;
    my $file=build_fname($tree, $host, $compiler, $rev);
    my $log;
    my $ret = 0;

    if ($rev) {
	    return $rev;
    }

    my $st1 = stat("$file.log");
    my $st2 = stat("$CACHEDIR/$file.revision");

    if ($st1 && $st2 && $st1->mtime <= $st2->mtime) {
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
			my $age = build_age($host, $tree, $compiler, "");
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
    my $host=shift;
    my $tree=shift;
    my $compiler=shift;
    my $rev=shift;
    my $file=build_fname($tree, $host, $compiler, $rev);
    my $cachefile="$CACHEDIR/" . $file . ".status";
    my ($cstatus, $bstatus, $istatus, $tstatus, $sstatus);
    $cstatus = $bstatus = $istatus = $tstatus = $sstatus =
      "<span class=\"status unknown\">?</span>";

    my $log;
    my $ret;

    my $st1 = stat("$file.log");
    my $st2 = stat("$cachefile");

    if ($st1 && $st2 && $st1->mtime <= $st2->mtime) {
	return util::FileLoad($cachefile);
    }

    $log = util::FileLoad("$file.log");

    if ($log =~ /TEST STATUS:(.*)/) {
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

    $ret = "<a href=\"$myself?function=View+Build;host=$host;tree=$tree;compiler=$compiler";
    if ($rev) {
	    $ret .= ";revision=$rev";
    }
    $ret .= "\">$cstatus/$bstatus/$istatus/$tstatus$sstatus</a>";

    util::FileSave("$CACHEDIR/$file.status", $ret);

    return $ret;
}

##############################################
# translate a status into a set of int representing status
sub build_status_vals($) {
    my $status = strip_html(shift);

    $status =~ s/ok/0/g;
    $status =~ s/\?/0/g;
    $status =~ s/PANIC/1/g;

    return split m%/%, $status;
}
##############################################
# get status of build
sub err_count($$$$)
{
    my $host=shift;
    my $tree=shift;
    my $compiler=shift;
    my $rev=shift;
    my $file=build_fname($tree, $host, $compiler, $rev);
    my $err;

    my $st1 = stat("$file.err");
    my $st2 = stat("$CACHEDIR/$file.errcount");

    if ($st1 && $st2 && $st1->mtime <= $st2->mtime) {
	    return util::FileLoad("$CACHEDIR/$file.errcount");
    }

    $err = util::FileLoad("$file.err");

    if (! $err) { return 0; }

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

    #set up a variable to store the broken builds table's code, so we can output when we want
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
			    my $age = build_age($host, $tree, $compiler, "");
			    
			    if ($age != -1 && $age < $DEADAGE) {
				    $host_count{$tree}++;
			    }

			    if ($age < $DEADAGE && $status =~ /status failed/) {
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
	    print <<EOHEADER;
<div id="build-counts" class="build-section">
<h2>Build counts:</h2>
<table class="real">
  <thead>
    <tr>
      <th>Tree</th><th>Total</th><th>Broken</th><th>Panic</th>
    </tr>
  </thead>
  <tbody>
EOHEADER
    }


    for my $tree (sort keys %trees) {
	    if ($output_type eq 'text') {
		    printf "%-12s %-6s %-6s %-6s\n", $tree, $host_count{$tree},
			    $broken_count{$tree}, $panic_count{$tree};
	    }
	    else {
		    print "    <tr><td><a href=\"$myself?function=Recent+Builds;tree=$tree\" title=\"View recent builds for $tree\">$tree</a></td><td>$host_count{$tree}</td><td>$broken_count{$tree}</td>";
		    my $panic = "";
		    if ($panic_count{$tree}) {
			    $panic = " class=\"panic\"";
		    }
		    print "<td$panic>$panic_count{$tree}</td></tr>\n";
	    }
    }

    if ($output_type eq 'text') {
	    print "\n";
    }
    else {
	    print "  </tbody>\n</table></div>\n";
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
			 }
			 elsif (!defined $bstat[4] && defined $astat[4]) {
				 return -1;
			 }
			 return ($bstat[0] <=> $astat[0] || # configure
				 $bstat[1] <=> $astat[1] || # compile
				 $bstat[2] <=> $astat[2] || # install
				 $bstat[3] <=> $astat[3]    # test
				);
		 }
	       };

    my $tree=get_param("tree");
    my $sort_by=get_param("sortby") || "revision"; # default to revision

    util::InArray($tree, [keys %trees]) || fatal("not a build tree");
    util::InArray($sort_by, [keys %$sort]) || fatal("not a valid sort");

    for my $host (@hosts) {
      for my $compiler (@compilers) {
	  my $status = build_status($host, $tree, $compiler, "");
	  my $age = build_age($host, $tree, $compiler, "");
	  my $revision = build_revision($host, $tree, $compiler, "");
	  push @all_builds, [$age, $hosts{$host}, "<a href=\"$myself?function=View+Host;host=$host;tree=$tree;compiler=$compiler#$host\">$host</a>", $compiler, $tree, $status, $revision]
	  	unless $age == -1 or $age >= $DEADAGE;
      }
    }

    @all_builds = sort { $sort->{$sort_by}() || $sort->{age}() } @all_builds;

    my $sorturl = "$myself?tree=$tree;function=Recent+Builds";

    print <<EOHEADER;

    <div id="recent-builds" class="build-section">
    <h2>Recent builds of $tree</h2>
      <table class="real">
	<thead>
	  <tr>
            <th><a href="$sorturl;sortby=age" title="Sort by build age">Age</a></th>
            <th><a href="$sorturl;sortby=revision" title="Sort by build revision">Revision</a></th>
            <th>Tree</th>
            <th><a href="$sorturl;sortby=platform" title="Sort by platform">Platform</a></th>
            <th><a href="$sorturl;sortby=host" title="Sort by host">Host</a></th>
            <th><a href="$sorturl;sortby=compiler" title="Sort by compiler">Compiler</a></th>
            <th><a href="$sorturl;sortby=status" title="Sort by build status">Status</a></th>

	  </tr>
	</thead>
        <tbody>
EOHEADER

    for my $build (@all_builds) {
	my $age = $$build[0];
	my $rev = $$build[6];
	print "    <tr><td>",
	  join("</td><td>" , util::dhm_time($age),
	       $rev, @$build[4, 1, 2, 3, 5]),
	  "</td></tr>\n";
    }
    print "  </tbody>\n</table>\n</div>\n";
}


##############################################
# Draw the "dead hosts" table
sub draw_dead_hosts {
    my $output_type = shift;
    my @deadhosts = @_;

    # don't output anything if there are no dead hosts
    if ($#deadhosts < 0) {
      return;
    }

    # don't include in text report
    if ($output_type eq 'text') {
	    return;
    }

	print <<EOHEADER;
<div class="build-section" id="dead-hosts">
<h2>Dead Hosts:</h2>
<table class="real">
<thead>
<tr><th>Host</th><th>OS</th><th>Min Age</th></tr>
</thead>
<tbody>
EOHEADER

    for my $host (@deadhosts) {
	my $age = host_age($host);
	print "    <tr><td>$host</td><td>$hosts{$host}</td><td>", util::dhm_time($age), "</td></tr>";
    }


    print "  </tbody>\n</table>\n</div>\n";
}

##############################################
# show the available old revisions, if any
sub show_oldrevs($$$)
{
    my $tree=shift;
    my $host=shift;
    my $compiler=shift;
    my %revs = get_old_revs($tree, $host, $compiler);
    my @revs = sort { $revs{$b} cmp $revs{$a} } keys %revs;

    return if ($#revs < 1);

    print "<h2>Older builds:</h2>\n";

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
    my $age = build_age($host, $tree, $compiler, $rev);
    my $revision = build_revision($host, $tree, $compiler, $rev);
    my $status = build_status($host, $tree, $compiler, $rev);

    $rev = int($rev);

    $log = util::FileLoad("$file.log");
    $err = util::FileLoad("$file.err");
    
    if ($log) {
	$log = util::cgi_escape($log);

	if ($log =~ /(.*)/) { $uname=$1; }
	if ($log =~ /CFLAGS=(.*)/) { $cflags=$1; }
	if ($log =~ /configure options: (.*)/) { $config=$1; }
    }

    if ($err) {
	$err = util::cgi_escape($err);
    }

    print "<h2>Host information:</h2>\n";

    print util::FileLoad("../web/$host.html");

    print "
<table class=\"real\">
<tr><td>Host:</td><td><a href=\"$myself?function=View+Host;host=$host;tree=$tree;compiler=$compiler#$host\">$host</a> - $hosts{$host}</td></tr>
<tr><td>Uname:</td><td>$uname</td></tr>
<tr><td>Tree:</td><td>$tree</td></tr>
<tr><td>Build Revision:</td><td>" . $revision . "</td></tr>
<tr><td>Build age:</td><td class=\"age\">" . red_age($age) . "</td></tr>
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

    print "<div id=\"log\">\n";

    if (!$plain_logs) {

	    print "<p>Switch to the <a href=\"$myself?function=View+Build;host=$host;tree=$tree;compiler=$compiler;plain=true\" title=\"Switch to bland, non-javascript, unstyled view\">Plain View</a></p>";

	    print "<div id=\"actionList\">\n";
	    # These can be pretty wide -- perhaps we need to 
	    # allow them to wrap in some way?
	    if ($err eq "") {
		    print "<h2>No error log available</h2>\n";
	    } else {
		    print "<h2>Error log:</h2>\n";
		    print make_action_html("Error Output", "\n$err", "stderr-0", 0);
	    }

	    if ($log eq "") {
		    print "<h2>No build log available</h2>\n";
	    } else {
		    print "<h2>Build log:</h2>\n";
		    print_log_pretty($log);
	    }

	    print "<p><small>Some of the above icons derived from the <a href=\"http://www.gnome.org\">Gnome Project</a>'s stock icons.</p>";
	    print "</div>\n";
    }
    else {
	    print "<p>Switch to the <a href=\"$myself?function=View+Build;host=$host;tree=$tree;compiler=$compiler\" title=\"Switch to colourful, javascript-enabled, styled view \">Enhanced View</a></p>";
	    if ($err eq "") {
		    print "<h2>No error log available</h2>\n";
	    } else {
		    print "<h2>Error log:</h2>\n";
		    print "<div id=\"errorLog\"><pre>" . join('', $err) . "</pre></div>\n";
	    }
	    if ($log eq "") {
		    print "<h2>No build log available</h2>n";
	    }
	    else {
		    print "<h2>Build log:</h2>\n";
		    print "<div id=\"buildLog\"><pre>" . join('', $log) . "</pre></div>\n";
	    }
    }

    print "</div>\n";
}

##################################################
# print the host's table of information
sub view_host() {

	my $output_type = "html";

	if ($output_type eq 'text') {
		print "Host summary:\n";
	}
	else {
		print "<div class=\"build-section\" id=\"build-summary\">\n";
		print "<h2>Host summary:</h2>\n";
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
				my $age = build_age($host, $tree, $compiler, "");
				my $warnings = err_count($host, $tree, $compiler, "");
				if ($age != -1 && $age < $DEADAGE) {
					my $status = build_status($host, $tree, $compiler, "");
					if ($row == 0) {
						if ($output_type eq 'text') {
							printf "%-12s %-10s %-10s %-10s %-10s\n",
								"Tree", "Compiler", "Build Age", "Status", "Warnings";
                                    
						}
						else {
							print <<EOHEADER;
<div class="host summary">
  <a id="$host" name="$host" />
  <h3>$host - $hosts{$host}</h3>
  <table class="real">
    <thead>
      <tr>
        <th>Target</th><th>Build&nbsp;Age</th><th>Status<br />config/build<br />install/test</th><th>Warnings</th>
      </tr>
    </thead>
    <tbody>
EOHEADER
						}
					}

					if ($output_type eq 'text') {
						printf "%-12s %-10s %-10s %-10s %-10s\n",
							$tree, $compiler, util::dhm_time($age), 
								strip_html($status), $warnings;
					}
					else {
						print "    <tr><td><span class=\"tree\">$tree</span>/$compiler</td><td class=\"age\">" . red_age($age) . "</td><td class=\"status\">$status</td><td>$warnings</td></tr>\n";
					}
					$row++;
				}
			}
		}
		if ($row != 0) {
			if ($output_type eq 'text') {
				print "\n";
			}
			else {
				print "  </tbody>\n</table></div>\n";
			}
		} else {
			push(@deadhosts, $host);
		}
	}


	if ($output_type ne 'text') {
		print "</div>\n\n";
	}

	draw_dead_hosts($output_type, @deadhosts);

}

##############################################
# prints the log in a visually appealing manner
sub print_log_pretty() {
  my $log = shift;


  # do some pretty printing for the actions
  my $id = 1;
  $log =~ s{   Running\ action\s+([\w\-]+)
	       (.*?)
	       ACTION\ (PASSED|FAILED):\ ([\w\-]+)
	     }{make_action_html($1, $2, $id++, $3)}exgs;
  
  $log =~ s{
	      --==--==--==--==--==--==--==--==--==--==--.*?
	      Running\ test\ ([\w\-=,_:\ ]+)\ \(level\ (\d+)\ (\w+)\).*?
	      --==--==--==--==--==--==--==--==--==--==--
              (.*?)
	      ==========================================.*?
	      TEST\ (FAILED|PASSED|SKIPPED):(\ \(status\ (\d+)\))?.*?
	      ==========================================\s+
	     }{make_test_html($1, $4, $id++, $5)}exgs;


	print "<tt><pre>" .join('', $log) . "</pre></tt><p>\n";
}

##############################################
# generate html for a test section
sub make_test_html {
  my $name = shift;
  my $output = shift;
  my $id = shift;
  my $status = shift;

  my $return =  "</pre>" . # don't want the pre openned by action affecting us
               "<div class=\"test unit \L$status\E\" id=\"test-$id\">" .
                "<a href=\"javascript:handle('$id');\">" .
                 "<img id=\"img-$id\" name=\"img-$id\" src=\"";
  if (defined $status && $status eq "PASSED") {
    $return .= "icon_unhide_16.png";
  }
  else {
    $return .= "icon_hide_16.png";
  }
  $return .= "\" /> " .
                 "<div class=\"test name\">$name</div> " .
                "</a> " .
               "<div class=\"test status \L$status\E\">$status</div>" .
               "<div class=\"test output\" id=\"output-$id\">" .
                "<pre>$output</pre>" .
               "</div>" .
              "</div>" .
              "<pre>";    # open the pre back up
              
  return $return;
}

##############################################
# generate html for an action section
sub make_action_html($$$$)
{

  my $name = shift;
  my $output = shift;
  my $id = shift;
  my $status = shift;
  my $return = "<div class=\"action unit \L$status\E\" id=\"action-$id\">" .
                "<a href=\"javascript:handle('$id');\">" .
                 "<img id=\"img-$id\" name=\"img-$id\" src=\"";

  if (defined $status && ($status =~ /failed/i)) {
    $return .= 'icon_hide_24.png';
  }
  else {
    $return .= 'icon_unhide_24.png';
  }

  $return .= "\" /> " .
                  "<div class=\"action name\">$name</div>" .
                "</a> ";

  if (defined $status) {
    $return .= "<div class=\"action status \L$status\E\">$status</div>";
  }

  my $x;
  $x = "$id";
  $x = "$name$output";
  $x = "$status";
  $x = "$name";

  $return .= "<div class=\"action output\" id=\"output-$id\">" .
                 "<pre>Running action $name$output ACTION $status: $name</pre>" .
                "</div>".
               "</div>";

  return $return
}

##############################################
# simple html markup stripper
sub strip_html($) {
	my $string = shift;

	# get rid of comments
	$string =~ s/<!\-\-(.*?)\-\->/$2/g;

	# and remove tags.
	while ($string =~ s&<(\w+).*?>(.*?)</\1>&$2&) {
		;
	}

	return $string;
}


##############################################
# main page
sub main_menu() {
    print $req->startform("GET");
    print "<div id=\"build-menu\">\n";
    print $req->popup_menu(-name=>'host',
			   -values=>\@hosts,
			   -labels=>\%hosts) . "\n";
    print $req->popup_menu("tree", [sort (keys %trees, @pseudo_trees)]) . "\n";
    print $req->popup_menu("compiler", \@compilers) . "\n";
    print "<br />\n";
    print $req->submit('function', 'View Build') . "\n";
    print $req->submit('function', 'View Host') . "\n";
    print $req->submit('function', 'Recent Checkins') . "\n";
    print $req->submit('function', 'Summary') . "\n"; 
    print $req->submit('function', 'Recent Builds') . "\n";
    print "</div>\n";
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
  cgi_headers_diff();
  chdir("$BASEDIR/data") || fatal("can't change to data directory");
  history::diff(get_param('author'),
		get_param('date'),
		get_param('tree'),
		get_param('revision'),
		"text");
}
elsif ($fn_name eq 'Text_Summary') {
	cgi_headers_text();
	chdir("$BASEDIR/data") || fatal("can't change to data directory");
	view_summary('text');
}
else {
  page_top();

  if    ($fn_name eq "View_Build") {
    view_build();
  }
  elsif ($fn_name eq "View_Host") {
    view_host();
  }
  elsif ($fn_name eq "Recent_Builds") {
    view_recent_builds();
  }
  elsif ($fn_name eq "Recent_Checkins") {
    history::history(get_param('tree'));
  }
  elsif ($fn_name eq "diff") {
    history::diff(get_param('author'),
		  get_param('date'),
		  get_param('tree'),
		  get_param('revision'),
		  "html");
  }
  else {
    view_summary('html');
  }
  cgi_footers();
}

