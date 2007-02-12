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


use strict;
use warnings;
use FindBin qw($RealBin);

use lib "$RealBin";
use data qw(@compilers %hosts @hosts %trees @pseudo_trees $OLDAGE $DEADAGE
            build_age_mtime build_age_ctime build_revision get_old_revs
	    build_status err_count read_log read_err);
use util;
use history;
use POSIX;
use Data::Dumper;
use CGI qw/:standard/;
use File::stat;

my $WEBDIR = "$RealBin";
my $BASEDIR = "$WEBDIR/..";

my $req = new CGI;

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
					  -href => "/build_farm.css",
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

    print util::FileLoad("$WEBDIR/header2.html");
    print main_menu();
    print util::FileLoad("$WEBDIR/header3.html");
}

################################################
# end CGI
sub cgi_footers() {
	print util::FileLoad("$WEBDIR/footer.html");
	print $req->end_html;
}

################################################
# print an error on fatal errors
sub fatal($) {
    my $msg = shift;

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

sub build_status($$$$)
{
	my ($host, $tree, $compiler, $rev) = @_;

	return a({-href=>"$myself?function=View+Build;host=$host;tree=$tree;compiler=$compiler" . ($rev?";revision=$rev":"")}, data::build_status($host, $tree, $compiler, $rev));
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
		return $req->span({-class=>"old"}, util::dhm_time($age));
	}
	return util::dhm_time($age);
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
# view build summary
sub view_summary($) 
{
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
    } else {
	    print $req->start_div({-id=>"build-counts", -class=>"build-section"});
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
			print $req->td(tree_link($tree));
			print $req->td($host_count{$tree});
			print $req->td($broken_count{$tree});
		    if ($panic_count{$tree}) {
				print $req->start_td({-class => "panic"});
		    } else {
				print $req->start_td;
			}
			print $panic_count{$tree} . $req->end_td;
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
# return a link to a particular revision
sub revision_link($$)
{
	my ($revision, $tree) = @_;

	$revision =~ s/^\s+//g;
	return "0" if ($revision eq "0");

	return $req->a({
			-href=>"$myself?function=diff;tree=$tree;revision=$revision",
			-title=>"View Diff for $revision"
		}, $revision);
}

###############################################
# return a link to a particular tree
sub tree_link($)
{
	my ($tree) = @_;

	return $req->a({-href=>"$myself?function=Recent+Builds;tree=$tree",
					-title=>"View recent builds for $tree"}, $tree);
}

##############################################
# Draw the "recent builds" view
sub view_recent_builds($$) {
	my ($tree, $sort_by) = @_;
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

    util::InArray($tree, [keys %trees]) || fatal("not a build tree");
    util::InArray($sort_by, [keys %$sort]) || fatal("not a valid sort");

    for my $host (@hosts) {
      for my $compiler (@compilers) {
	  my $status = build_status($host, $tree, $compiler, "");
	  my $age_mtime = build_age_mtime($host, $tree, $compiler, "");
	  my $age_ctime = build_age_ctime($host, $tree, $compiler, "");
	  my $revision = build_revision($host, $tree, $compiler, "");
	  push @all_builds, [$age_ctime, $hosts{$host}, $req->a({-href=>"$myself?function=View+Host;host=$host;tree=$tree;compiler=$compiler#$host"}, $host), $compiler, $tree, $status, revision_link($revision, $tree)]
	  	unless $age_mtime == -1 or $age_mtime >= $DEADAGE;
      }
    }

    @all_builds = sort { $sort->{$sort_by}() || $sort->{age}() } @all_builds;

    my $sorturl = "$myself?tree=$tree;function=Recent+Builds";

	print $req->start_div({-id=>"recent-builds", -class=>"build-section"}),
		  $req->h2("Recent builds of $tree"),
		  $req->start_table({-class => "real"}),
	      $req->thead(
			  $req->Tr(
				  $req->th([
					  $req->a({-href => "$sorturl;sortby=age",
							   -title => "Sort by build age"}, "Age"),
				  	  $req->a({-href => "$sorturl;sortby=revision",
							        -title => "Sort by build revision"},
								    "Revision"),
					  "Tree",
					  $req->a({-href => "$sorturl;sortby=platform",
						           -title => "Sort by platform"}, "Platform"),
					  $req->a({-href => "$sorturl;sortby=host",
						           -title => "Sort by host"}, "Host"),
					  $req->a({-href=>"$sorturl;sortby=compiler",
							        -title=>"Sort by compiler"}, "Compiler"),
					  $req->a({-href=>"$sorturl;sortby=status",
							        -title=>"Sort by build status"}, "Status")]
					)
				)),
			$req->start_tbody;

    for my $build (@all_builds) {
		print $req->Tr(
			  $req->td([util::dhm_time($$build[0]), $$build[6], $$build[4], 
				        $$build[1], $$build[2], $$build[3], $$build[5]]));
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

	print $req->start_div({-class => "build-section", -id=>"dead-hosts"}),
		  $req->h2('Dead Hosts:'),
		  $req->start_table({-class => "real"}),
		  $req->thead($req->Tr($req->th(["Host", "OS", "Min Age"]))),
		  $req->start_tbody;

    for my $host (@deadhosts) {
	my $age_ctime = host_age($host);
	print $req->tr($req->td([$host, $hosts{$host}, util::dhm_time($age_ctime)]));
    }

	print $req->end_tbody, $req->end_table;
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

    my $ret = $req->h2("Older builds:");

    $ret .= $req->start_table({-class => "real"}),
	      $req->thead($req->Tr($req->th(["Revision", "Status"]))),
	      $req->start_tbody;

    my $lastrev = "";

    for my $rev (@revs) {
	    my $s = $revs{$rev};
	    $s =~ s/$rev/0/;
	    next if ($s eq $lastrev);
	    $lastrev = $s;
	    $ret.=$req->Tr($req->td([revision_link($rev, $tree), $revs{$rev}]));
    }
    if ($lastrev ne "") {
		# Only print table if there was any actual data
    	print $ret . $req->end_tbody, $req->end_table;
   }
}

##############################################
# view one build in detail
sub view_build($$$$) {
	my ($tree, $host, $compiler, $rev) = @_;
    # ensure the params are valid before using them
    util::InArray($host, [keys %hosts]) || fatal("unknown host");
    util::InArray($compiler, \@compilers) || fatal("unknown compiler");
    util::InArray($tree, [keys %trees]) || fatal("not a build tree");

    my $uname="";
    my $cflags="";
    my $config="";
    my $age_mtime = build_age_mtime($host, $tree, $compiler, $rev);
    my $revision = build_revision($host, $tree, $compiler, $rev);
    my $status = build_status($host, $tree, $compiler, $rev);

    $rev = int($rev) if $rev;

    my $log = read_log($tree, $host, $compiler, $rev);
    my $err = read_err($tree, $host, $compiler, $rev);
    
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

    print $req->table({-class=>"real"},
		$req->Tr([
			$req->td(["Host:", $req->a({-href=>"$myself?function=View+Host;host=$host;tree=$tree;compiler=$compiler#$host"}, $host)." - $hosts{$host}"]),
			$req->td(["Uname:", $uname]),
			$req->td(["Tree:", tree_link($tree)]),
			$req->td(["Build Revision:", revision_link($revision, $tree)]),
			$req->td(["Build age:", $req->div({-class=>"age"}, red_age($age_mtime))]),
			$req->td(["Status:", $status]),
			$req->td(["Compiler:", $compiler]),
			$req->td(["CFLAGS:", $cflags]),
			$req->td(["configure options:", $config])]));

    show_oldrevs($tree, $host, $compiler);

    # check the head of the output for our magic string
    my $plain_logs = (defined get_param("plain") &&
		      get_param("plain") =~ /^(yes|1|on|true|y)$/i);
    my $rev_var = "";
    if ($rev) {
	    $rev_var = ";revision=$rev";
    }

    print $req->start_div({-id=>"log"});

    if (!$plain_logs) {
	    print $req->p("Switch to the ".$req->a({-href => "$myself?function=View+Build;host=$host;tree=$tree;compiler=$compiler$rev_var;plain=true", -title=> "Switch to bland, non-javascript, unstyled view"}, "Plain View"));

	    print $req->start_div({-id=>"actionList"});
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

	    print $req->p($req->small("Some of the above icons derived from the ".$req->a({-href=>"http://www.gnome.org"}, "Gnome Project")."'s stock icons."));
		print $req->end_div;
    } else {
	    print $req->p("Switch to the ".$req->a({-href=>"$myself?function=View+Build;host=$host;tree=$tree;compiler=$compiler$rev_var", -title=>"Switch to colourful, javascript-enabled, styled view"}, "Enhanced View"));
	    if ($err eq "") {
		    print $req->h2("No error log available");
	    } else {
		    print $req->h2('Error log:');
		    print $req->div({-id=>"errorLog"}, $req->pre($err));
	    }
	    if ($log eq "") {
		    print $req->h2('No build log available');
	    }
	    else {
		    print $req->h2('Build log:');
		    print $req->div({-id=>"buildLog"}, $req->pre($log));
	    }
    }

	print $req->end_div;
}

##################################################
# print the host's table of information
sub view_host {
	my (@requested_hosts) = @_;

	my $output_type = "html";

	if ($output_type eq 'text') {
		print "Host summary:\n";
	} else {
		print $req->start_div({-class=>"build-section", -id=>"build-summary"});
		print $req->h2('Host summary:');
	}

	my $list = `ls *.log`;

	foreach (@requested_hosts) {
		util::InArray($_, [keys %hosts]) || fatal("unknown host");
	}

	for my $host (@requested_hosts) {
		# make sure we have some data from it
		if (! ($list =~ /$host/)) {
			if ($output_type ne 'text') {
				print $req->comment("skipping $host");
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
							print $req->start_div({-class=>"host summary"}),
							      $req->a({-id=>$host, -name=>$host}), 
								  $req->h3("$host - $hosts{$host}"),
								  $req->start_table({-class=>"real"}),
							      $req->thead($req->Tr(
								  $req->th(["Target", "Build<br/>Revision", "Build<br />Age", "Status<br />config/build<br />install/test", "Warnings"]))),
						  		  $req->start_tbody;
						}
					}

					if ($output_type eq 'text') {
						printf "%-12s %-10s %-10s %-10s %-10s\n",
							$tree, $compiler, util::dhm_time($age_mtime), 
								util::strip_html($status), $warnings;
					} else {
						print $req->Tr($req->td([$req->span({-class=>"tree"}, tree_link($tree))."/$compiler", revision_link($revision, $tree), $req->div({-class=>"age"}, red_age($age_mtime)), $req->div({-class=>"status"}, $status), $warnings]));
					}
					$row++;
				}
			}
		}
		if ($row != 0) {
			if ($output_type eq 'text') {
				print "\n";
			} else {
				print $req->end_tbody, $req->end_table;
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

  print $req->p($req->tt($req->pre($log)))."\n";
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
  return $req->div({-class=>"$type unit \L$status\E",
		                  -id=>"$type-$id"},
					  $req->a({-href=>"javascript:handle('$id');"},
						  $req->img({-id=>"img-$id", -name=>"img-$id",
								    -alt=>$status,
									-src=>$icon}),
						  $req->div({-class => "$type title"}, $title),
					  ) ." ". 
					  $req->div({-class=> "$type status \L$status\E"}, $status) .
					  $req->div({-class => "$type output", -id=>"output-$id"}, $req->pre($output)));
}

##############################################
# main page
sub main_menu() {
    return $req->startform("GET"), 
	   $req->start_div({-id=>"build-menu"}),
           $req->popup_menu(-name=>'host',
			   -values=>\@hosts,
			   -labels=>\%hosts),
          $req->popup_menu("tree", [sort (keys %trees, @pseudo_trees)]),
          $req->popup_menu("compiler", \@compilers),
          $req->br(),
          $req->submit('function', 'View Build'),
          $req->submit('function', 'View Host'),
          $req->submit('function', 'Recent Checkins'),
          $req->submit('function', 'Summary'),
          $req->submit('function', 'Recent Builds'),
          $req->end_div,
          $req->endform() . "\n";
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
    view_build(get_param("tree"), get_param("host"), get_param("compiler"),
		       get_param('revision'));
  } elsif ($fn_name eq "View_Host") {
    view_host(get_param('host'));
  } elsif ($fn_name eq "Recent_Builds") {
    view_recent_builds(get_param("tree"), get_param("sortby") || "revision");
  } elsif ($fn_name eq "Recent_Checkins") {
    history::history(get_param('tree'));
  } elsif ($fn_name eq "diff") {
    history::diff(get_param('author'),
		  get_param('date'),
		  get_param('tree'),
		  get_param('revision'),
		  "html");
  } elsif (path_info() ne "" and path_info() ne "/") {
	my @paths = split('/', path_info());
	if ($paths[1] eq "recent") {
		view_recent_builds($paths[2], get_param('sortby') || 'revision');
	} elsif ($paths[1] eq "host") {
		view_host($paths[2]);
	}
  } else {
    view_summary('html');
  }
  cgi_footers();
}
