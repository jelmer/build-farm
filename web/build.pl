#!/usr/bin/perl -w
# This CGI script presents the results of the build_farm build
#
# Copyright (C) Andrew Tridgell <tridge@samba.org>     2001
# Copyright (C) Andrew Bartlett <abartlet@samba.org>   2001
# Copyright (C) Vance Lankhaar  <vance@samba.org>      2002-2004
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


my $BASEDIR = "/home/build/master";
my $CACHEDIR = "/home/build/master/cache";

use strict qw{vars};
use lib "$BASEDIR/web";
use util;
use history;
use POSIX;
use Data::Dumper;
use CGI::Form;
use File::stat;

my $req = new CGI::Form;

my $HEADCOLOR = "#a0a0e0";
my $OLDAGE = 60*60*4;
my $DEADAGE = 60*60*24*4;

##############################################
# this defines what it is possible to build 
# and what boxes. Should be in a config file
my $compilers = ['cc', 'gcc', 'gcc3', 'gcc-3.4', 'insure'];

my (%hosts) = ('sun1' => "Solaris 8 UltraSparc", 
	       'Isis' => "Solaris 8 i386",
	       'gc20' => "Solaris 2.6 Sparc",
#	       'sco1' => "SysV 3.2 i386", 
#	       'sco2' => "UnixWare 7.1.0 i386", 

	       'aix1' => "AIX 4.3 PPC",
	       'mungera' => "AIX 5.2 IBM POWER4+",

	       'us4'  => "IRIX 6.5 MIPS", 
	       'au2'  => "IRIX 6.4 MIPS",

	       'smbo2000' => "IRIX 6.5 MIPS",

	       'wayne' => "RedHat 6.1 Sparc 10 (Kernel 2.2.18)",
	       'yowiee' => "RedHat 9.0 i386",
#	       'insure' => "RedHat 6.2 vmware (insure)",
	       'svamp' => "RedHat 7.0 i386",

	       'rhonwyn'  => "Debian Linux unstable i686",
	       'boiccu'  => "Debian Linux testing/unstable IA64",
	       'yurok' => "Debian Linux 3.0 stable i386",
	       'samba-s390' => "Debian Linux 3.0 stable s390",

	       'fusberta' => "Debian Linux 3.0 Alpha",

	       'sparc-woody' => "Debian Linux 3.0 (woody) Sparc64",
	       'sparc-sarge' => "Debian Linux sarge/testing Sparc64",
	       'sparc-sid' => "Debian Linux sid/unstable Sparc64",

	       'tux' => "Debian Linux sid/unstable HP PA-RISC",

	       'flame'  => "OpenBSD 3.0 Sparc",
	       'pandemonium' => "OpenBSD-current Sparc64",

	       'kimchi'  => "NetBSD 1.5 i386",

	       'gc8'  => "FreeBSD 3.3-RELEASE i386",
	       'gc4'  => "FreeBSD 4.3-STABLE i386",
		   'gwalcmai' => "FreeBSD 5.2-RELEASE i586",

	       'manhattan' => "FreeBSD 4.8-RELEASE i386",

	       'sbf' => "FreeBSD 5.2.1 i386",
	       'smartserv1' => 'FreeBSD 5.2-CURRENT i386',

	       'woko'  => "Cray SV1 UNICOS 10.0.0.8",

	       'hpntc9I' => "HP-UX 11.11",
	       'gwen' => "HP-UX 11.11",

	       'g6usr30' => "RedHat 7.2 IBM s390 (Kernel 2.4.9)",

	       'belle' => "RedHat 8.0 i686",
	       'manjra' => "RedHat 8.0 i686",

	       'suse71ppc' => "SuSE 7.1 ppc gcc2.95.2",
	       'metze01' => "SuSE 8.2 i386 (athlon)",
	       'metze02' => "SuSE 7.3 i386 (PIII)",

	       'l390vme1' => "SuSE SLES 8 (S/390)",

	       'PCS1' => "SuSE Linux 9.1  Professional (i586)",

	       'cyberone' => "Cygwin i686 (MS WinXP Pro)",

	       'trip' => "Mandrake 9.2 i386 GCC 3.3.1",

	       'm30' => "Stratus VOS HP PA-RISC",
	       
#		   'sprinkhaan' => "FreeBSD 4.7-STABLE i386",
#		   'vlo' => "FreeBSD 5.0-RELEASE i386 #0",

		   'jarret' => "Solaris 8 UltraSparc",
		   'previn' => "Solaris 8 UltraSparc",
		   'mundroo' => "Solaris 8 i386",
		   'cat' => "Solaris 9 i386",

#		   'paros' => "Solaris 9 UltraSparc",

	       'superego' => "Debian PPC/64 (Power3)",
	       'quango' => "Debian PPC/32 (Power3)",

#Compaq Test Drive systems (discontinued, for now)
#	       'spe140' => "Debian Linux 2.2R6 i386",
#	       'spe141' => "RedHat Linux 7.3 i386",
#	       'spe148' => "RedHat Linux 7.1 Alpha (ev6)",
#	       'spe149' => "FreeBSD 4.6-RELEASE Alpha",
#	       'spe150' => "SUSE Linux 8.0 i386",
#	       'spe151' => "FreeBSD 4.6-RELEASE i386",
#	       'spe158' => "SuSE Linux 7.1 Alpha",
#	       'spe160' => "Slackware Linux 8.0 i386",
#	       'spe161' => "Debian Linux 2.2R6 Alpha",
#	       'spe188' => "Mandrake ProSuite 8.2 i386",
#	       'spe190' => "RedHat Linux 7.2 ia64",
#	       'spe223' => "Red Hat Linux Advanced Server 2.1AS i386",

	       'packetstorm' => "Slackware Linux 9.0 i386",

	       'tardis' => "Gentoo i686"
	       );


my @hosts = sort { $hosts{$a} cmp $hosts{$b} } keys %hosts;

my (%trees) = (
#'samba' => "",
	       'samba' => "",
	       'samba4' => "",
	       'samba-docs' => "",
	       'samba_3_0' => "SAMBA_3_0",
	       'samba_2_2' => "SAMBA_2_2",
	       'rsync' => "",
	       'distcc' => "",
	       'ccache' => "");

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

$myself = "http://build.samba.org/";

################################################
# start CGI headers
sub cgi_headers() {
    print "Content-type: text/html\r\n";

    util::cgi_gzip();

    print '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd"> 
<html>
<head>
<link rel="shortcut icon" href="/favicon.ico">
<style type="text/css">  
.entry {
        background-color: #f0f0ff;
        width: 80%;
        text-align: left;
        margin: 15px 0px 15px 0px;
        border: 1px solid gray;
}
.entry TABLE {
        width: 100%;
}
.entry TABLE TD {
        vertical-align: top;
	text-align: left;
}
.entry TABLE TH {
        vertical-align: top;
        width: 5em;
        text-align: left;
}

TABLE.header {
        border: 1px solid black;
}
TABLE.header TH {
        font-weight: normal;
        width: 12em;
        text-align: left;
}
TABLE.header TD {
}
#log .name,.status {
        display: inline;
        font-weight: bold;
        font-family: sans-serif;
}
#log .status.failed {
        color: rgb(153, 0, 0);;
}
#log .status.passed {
        color: rgb(0, 153, 0);
}
#log .output {
        color: rgb(0, 0, 0);
        font-family: monospace;
}
#log div.unit {
        margin: 5px;
        padding: 10px;
        border: 2px solid black;
}
#log div.unit.passed {
        background-color: rgb(180, 255, 180);
}
#log div.unit.failed {
        background-color: rgb(255, 180, 180);
}
#log .unit.failed .output {
        display: block;
}
#log .unit.passed .output {
        display: none;
}
#log div.output#output-stderr-0 {
        display: none;
}

#log img {
        border: none;
}
#log a {
        text-decoration: none;
}
#log a:hover,a:active {
        text-decoration: underline;
}
</style>
<script type="text/javascript">
<!-- begin hiding from browsers


function handle(name)
{
  action = document.getElementById("output-" + name);
  img = document.getElementById("img-" + name);
  old_src = img.getAttribute("src");

  current_display = action.style.display;

  // try to handle the case where the display is not explicitly set
  if (current_display == "") {
    if (action.currentStyle) { // ack, IE
      current_display = action.currentStyle.display;
    }
    else if (document.defaultView.getComputedStyle) { // oooh, DOM
      var style_list = document.defaultView.getComputedStyle(action, "");

      // konqueor has getComputedStyle, but it does not work
      if (style_list != null) {
	current_display = style_list.getPropertyValue("display");
      }
    }
    // in the case than neither works, we will do nothing. it just
    // means the user will have to click twice to do the initial closing
  }

  if (current_display == "block") {
    action.style.display = "none";
    img.setAttribute("src", old_src.replace("hide", "unhide"));
  }
  else {
    action.style.display = "block";
    img.setAttribute("src", old_src.replace("unhide", "hide"));
  }
}
// -- end hiding from browsers -->
</script>
<title>samba.org build farm</title></head>
<body bgcolor="white" text="#000000" link="#0000EE" vlink="#551A8B" alink="#FF0000">
<table border=0>
<tr>
<td><img alt="Samba Banner" border=0 align="left" src="http://www.samba.org/samba/images/samba_banner.gif"></td>
<td>
<ul>
<li><a href="about.html">About the build farm</a>
<li><a href="instructions.html">Adding a new machine</a>
<li><a href="http://pserver.samba.org/">Samba CVS repository</a>
<li><a href="http://www.samba.org/">Samba Web pages</a>
</ul>
</td>
</tr>
</table>
';

}

################################################
# start CGI headers for diffs
sub cgi_headers_diff() {
    print "Content-type: application/x-diff\r\n";
    print "\n";
}

################################################
# end CGI
sub cgi_footers() {
    print "</body>";
    print "</html>\n";
}

################################################
# print an error on fatal errors
sub fatal($) {
    my $msg=shift;
    print "ERROR: $msg<br>\n";
    cgi_footers();
    exit(0);
}

##############################################
# get the age of build from ctime
sub build_age($$$)
{
    my $host=shift;
    my $tree=shift;
    my $compiler=shift;
    my $file="build.$tree.$host.$compiler";
    my $age = -1;
    my $st;

    if ($st = stat("$file.log")) {
	$age = time() - $st->ctime;
    }

    return $age;
}

##############################################
# get the svn revision of build
sub build_revision($$$)
{
    my $host=shift;
    my $tree=shift;
    my $compiler=shift;
    my $file="build.$tree.$host.$compiler";
    my $log;
    my $rev = "unknown";

    my $st1 = stat("$file.log");
    my $st2 = stat("$CACHEDIR/$file.revision");

    if ($st1 && $st2 && $st1->ctime <= $st2->ctime) {
	    return util::FileLoad("$CACHEDIR/$file.revision");
    }

    $log = util::FileLoad("$file.log");

    if (! $log) { return 0; }

    if ($log =~ /BUILD REVISION:(.*)/) {
	$rev = $1;
    }

    util::FileSave("$CACHEDIR/$file.revision", "$rev");

    return $rev;
}

#############################################
# get the overall age of a host 
sub host_age($)
{
	my $host = shift;
	my $ret = -1;
	for my $compiler (@{$compilers}) {
		for my $tree (sort keys %trees) {
			my $age = build_age($host, $tree, $compiler);
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
		return sprintf("<font color=\"#b00000\">%s</font>",  util::dhm_time($age));
	}
	return util::dhm_time($age);
}


##############################################
# get status of build
sub build_status($$$)
{
    my $host=shift;
    my $tree=shift;
    my $compiler=shift;
    my $file="build.$tree.$host.$compiler";
    my $cachefile="$CACHEDIR/build.$tree.$host.$compiler";
    my $cstatus = "?";
    my $bstatus = "?";
    my $istatus = "?";
    my $tstatus = "?";
    my $sstatus = "/?";

    my $log;
    my $ret;

    my $st1 = stat("$file.log");
    my $st2 = stat("$cachefile.status");
    
    if ($st1 && $st2 && $st1->ctime <= $st2->ctime) {
	return util::FileLoad("$cachefile.status");
    }

    $log = util::FileLoad("$file.log");

    unlink("$CACHEDIR/FAILED.test.$tree.$host.$compiler");
    if ($log =~ /TEST STATUS:(.*)/) {
	if ($1 == 0) {
	    $tstatus = "<font color=green>ok</font>";
	} else {
	    $tstatus = "<font color=red>$1</font>";
	    system("touch $CACHEDIR/FAILED.test.$tree.$host.$compiler");
	}
    }
    
    unlink("$CACHEDIR/FAILED.install.$tree.$host.$compiler");
    if ($log =~ /INSTALL STATUS:(.*)/) {
	if ($1 == 0) {
	    $istatus = "<font color=green>ok</font>";
	} else {
	    $istatus = "<font color=red>$1</font>";
	    system("touch $CACHEDIR/FAILED.install.$tree.$host.$compiler");
	}
    }
    
    unlink("$CACHEDIR/FAILED.build.$tree.$host.$compiler");
    if ($log =~ /BUILD STATUS:(.*)/) {
	if ($1 == 0) {
	    $bstatus = "<font color=green>ok</font>";
	} else {
	    $bstatus = "<font color=red>$1</font>";
	    system("touch $CACHEDIR/FAILED.build.$tree.$host.$compiler");
	}
    }

    unlink("$CACHEDIR/FAILED.configure.$tree.$host.$compiler");
    if ($log =~ /CONFIGURE STATUS:(.*)/) {
	if ($1 == 0) {
	    $cstatus = "<font color=green>ok</font>";
	} else {
	    $cstatus = "<font color=red>$1</font>";
	    system("touch $CACHEDIR/FAILED.configure.$tree.$host.$compiler");
	}
    }
    
    unlink("$CACHEDIR/FAILED.internalerror.$tree.$host.$compiler");
    if ($log =~ /INTERNAL ERROR:(.*)/ || $log =~ /PANIC:(.*)/) {
	$sstatus = "/<font color=red><b>PANIC</b></font>";
	system("touch $CACHEDIR/FAILED.internalerror.$tree.$host.$compiler");
    } else {
	$sstatus = "";
    }
    
    $ret = "<a href=\"$myself?function=View+Build&host=$host&tree=$tree&compiler=$compiler\">$cstatus/$bstatus/$istatus/$tstatus$sstatus</a>";


    util::FileSave("$CACHEDIR/$file.status", $ret);

    return $ret;
}


##############################################
# get status of build
sub err_count($$$)
{
    my $host=shift;
    my $tree=shift;
    my $compiler=shift;
    my $file="build.$tree.$host.$compiler";
    my $err;

    my $st1 = stat("$file.err");
    my $st2 = stat("$CACHEDIR/$file.errcount");

    if ($st1 && $st2 && $st1->ctime <= $st2->ctime) {
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
sub view_summary() {
    my $i = 0;
    my $list = `ls`;

    my $cols = 2;

    my $broken = 0;

    # set up counters
    my %broken_count;
    my %panic_count;
    my %host_count;

    # zero broken and panic counters
    for my $tree (sort keys %trees) {
	$broken_count{$tree} = 0;
	$panic_count{$tree} = 0;
	$host_count{$tree} = 0;
    }

    #set up a variable to store the broken builds table's code, so we can output when we want
    my $broken_table;

    my $host_os;
    my $last_host = "";

    for my $host (@hosts) {
	for my $compiler (@{$compilers}) {
	    for my $tree (sort keys %trees) {
		my $status = build_status($host, $tree, $compiler);
		my $age = build_age($host, $tree, $compiler);
		if ($age != -1 && $age < $DEADAGE) {
		    $host_count{$tree}++;
		}
		if ($age < $DEADAGE && $status =~ /color=red/) {
		    if (!$broken) {
			$broken_table .= sprintf "<b>Currently broken builds:</b><p>\n";
			$broken_table .= sprintf "<table border=2><tr
      bgcolor=\"$HEADCOLOR\"><th colspan=3>Target</th><th>Build&nbsp;Age</th><th>Status<br>config/build/install/test</th><th>warnings</th></tr>\n";
			$broken = 1;
		    }
		    $broken_count{$tree}++;
		    if ($status =~ /PANIC/) {
			$panic_count{$tree}++;
		    }
		    my $warnings = err_count($host, $tree, $compiler);
		    
		    $broken_table .= sprintf "<tr>";
		    
		    $host_os = $hosts{$host};
		    if ($host eq $last_host) {
			$broken_table .= sprintf "<td colspan=2></td>";
		    } else {
			$broken_table .= sprintf "<td>$host_os</td><td><a href=\"#$host\">$host</a></td>";
		    }
		    $broken_table .= sprintf "<td><b>$tree</b>/$compiler</td><td align=right>" . red_age($age) . "</td><td align=center>$status</td><td align=center>$warnings</td></tr>\n";
		    
		    $last_host = $host;
		    
		}
	    }
	}
    }
    
    if ($broken) {
	$broken_table .= sprintf("</table><p>\n");
    }

    print "<b>Build counts:</b><p>";
    print "<table border=2 width=250><tr bgcolor=\"$HEADCOLOR\"><th>Tree</th><th>Total</th><th>Broken</th><th>Panic</th></tr>\n";
    for my $tree (sort keys %trees) {
	print "<tr><td>$tree</td><td align=center>$host_count{$tree}</td><td align=center>$broken_count{$tree}</td><td align=center>";
	if ($panic_count{$tree}) {
	    print "<font color=red><b>$panic_count{$tree}</b></font>";
	} else {
	    print "0";
	}
	print "</td></tr>\n";
    }
    print "</table><p>\n";


    print $broken_table;

    print "<b>Build summary:</b>\n\n";
    
    print '<table border=0><tr>';
    for my $host (@hosts) {
	# make sure we have some data from it
	if (! ($list =~ /$host/)) { print "\n<!-- skipping $host --!>\n"; next; }
	
	if ($i == $cols) {
	    $i = 0;
	    print "</tr><tr>";
	}

	my $row = 0;
	
	for my $compiler (@{$compilers}) {
	    for my $tree (sort keys %trees) {
		my $age = build_age($host, $tree, $compiler);
		my $warnings = err_count($host, $tree, $compiler);
		if ($age != -1 && $age < $DEADAGE) {
		    my $status = build_status($host, $tree, $compiler);
		    if ($row == 0) {
			print "<td valign=top><br><b><a name=\"$host\">$host</a> - $hosts{$host}</b><br><table border=2>
<tr bgcolor=\"$HEADCOLOR\"><th>Target</th><th>Build&nbsp;Age</th><th>Status<br>config/build<br>install/test</th><th>warnings</th></tr>
";
		    }
		    print "<tr align=center><td align=left><b>$tree</b>/$compiler</td><td align=right>" . red_age($age) . "</td><td>$status</td><td>$warnings</td></tr>\n";
		    $row++;
		}
	    }
	}
	if ($row != 0) {
	    print "</table></td>\n";
	    $i++;
	} else {
	    push(@deadhosts, $host);
	}
    }
    print '</tr></table>';

    draw_dead_hosts(@deadhosts);
}

##############################################
# Draw the "recent builds" view

sub view_recent_builds() {
    my $i = 0;
    my $list = `ls`;

    my $cols = 2;

    my $broken = 0;

    my $host_os;
    my $last_host = "";
    my @all_builds = ();
    my $tree=$req->param("tree");

    # Convert from the DataDumper tree form to an array that 
    # can be sorted by time.

    for my $host (@hosts) {
      for my $compiler (@{$compilers}) {
	  my $status = build_status($host, $tree, $compiler);
	  my $age = build_age($host, $tree, $compiler);
	  my $revision = build_revision($host, $tree, $compiler);
	  push @all_builds, [$age, $hosts{$host}, "<a href=\"$myself?function=Summary&host=$host&tree=$tree&compiler=$compiler#$host\">$host</a>", $compiler, $tree, $status, $revision]
	  	unless $age == -1 or $age >= $DEADAGE;
      }
  }

  @all_builds = sort {$$a[0] <=> $$b[0]} @all_builds;
  

    print "<h2>Recent builds of $tree</h2>";
    print '<table border=2>';
    print "<tr bgcolor=\"$HEADCOLOR\">";
    print "<th>Age</th>";
    print "<th>Revision</th>";
    print "<th colspan=4>Target</th>";
    print "<th>Status</th>";
    print "</tr>\n";

    for my $build (@all_builds) {
	my $age = $$build[0];
	my $rev = $$build[6];
	printf "<tr>";
	print "<td>" .
	util::dhm_time($age)."<td>";		# goes straight to stdout
	print $rev."<td>";
	print join "<td>", @$build[4, 1, 2, 3, 5];
	print "</tr>\n";
    }
    print "</table>\n";
}


##############################################
# Draw the "dead hosts" table
sub draw_dead_hosts() {
    my @deadhosts = @_;
    print "<br><b>Dead Hosts:</b><br>\n";
    print '<table border=2><tr>';
    print "<tr bgcolor=\"$HEADCOLOR\"><th>Host</th><th>OS</th><th>Min Age</th></tr>
";
    for my $host (@deadhosts) {
	my $age = host_age($host);
	printf("<tr><td>$host</td><td>$hosts{$host}</td><td align=right>%s</td>\n", util::dhm_time($age));
    }    
    print "</table>\n";
}


##############################################
# view one build in detail
sub view_build() {
    my $host=$req->param("host");
    my $tree=$req->param("tree");
    my $compiler=$req->param("compiler");
    my $file="build.$tree.$host.$compiler";
    my $log;
    my $err;
    my $uname="";
    my $cflags="";
    my $config="";
    my $age = build_age($host, $tree, $compiler);
    my $rev = build_revision($host, $tree, $compiler);
    my $status = build_status($host, $tree, $compiler);

    util::InArray($host, [keys %hosts]) || fatal("unknown host");
    util::InArray($compiler, $compilers) || fatal("unknown compiler");
    util::InArray($tree, [sort keys %trees]) || fatal("unknown tree");

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

    print util::FileLoad("../web/$host.html");

    print "
<table>
<tr><td>Host:</td><td><a href=\"$myself?function=Summary&host=$host&tree=$tree&compiler=$compiler#$host\">$host</a> - $hosts{$host}</td></tr>
<tr><td>Uname:</td><td>$uname</td></tr>
<tr><td>Tree:</td><td>$tree</td></tr>
<tr><td>Build Revision:</td><td>" . $rev . "</td></tr>
<tr><td>Build age:</td><td>" . red_age($age) . "</td></tr>
<tr><td>Status:</td><td>$status</td></tr>
<tr><td>Compiler:</td><td>$compiler</td></tr>
<tr><td>CFLAGS:</td><td>$cflags</td></tr>
<tr><td>configure options:  </td><td>$config</td></tr>
</table>
";

    # check the head of the output for our magic string 
    my $prettyPrintableLogs = ((substr $log, 0, 500) =~ /\*build_farm transition magic\*/);

    if ($prettyPrintableLogs) {

    print "<div id=\"log\">\n";
    print "<div id=\"actionList\">\n";
    # These can be pretty wide -- perhaps we need to 
    # allow them to wrap in some way?
    if ($err eq "") {
	print "<b>No error log available</b><br>\n";
    } else {
	print "<h2>Error log:</h2>\n";
	print make_action_html("stderr", $err, "stderr-0");;
    }

    if ($log eq "") {
	print "<b>No build log available</b><br>\n";
    } else {
	print "<h2>Build log:</h2>\n";
	print_log_pretty($log);
    }

    print "<p><small>Some of the above icons derived from the <a href=\"http://www.gnome.org\">Gnome Project</a>'s stock icons.</p>";
    print "</div>\n";
    print "</div>\n";
    }
    else {
    if ($err eq "") {
	print "<b>No error log available</b><br>\n";
    } else {
	print "<h2>Error log:</h2>\n";
	print "<tt><pre>" . join('', $err) . "</pre></tt>\n";
    }
    if ($log eq "") {
	print "<b>No build log available</b><br>\n";
    }
    else {
	print "<h2>Build log:</h2>\n";
	print "<tt><pre>" . join('', $log) . "</pre></tt><p>\n";
      }
    }
    print "</body>\n";
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
	      Running\ test\ ([\w-]+)\ \(level\ (\d+)\ (\w+)\).*?
	      --==--==--==--==--==--==--==--==--==--==--
              (.*?)
	      ==========================================.*?
	      TEST\ (FAILED|PASSED):(\ \(status\ (\d+)\))?.*?
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
                 "<img id=\"img-$id\" src=\"";
  if (defined $status && $status eq "PASSED") {
    $return .= "icon_unhide_16.png";
  }
  else {
    $return .= "icon_hide_16.png";
  }
  $return .= "\"> " .
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
sub make_action_html {

  my $name = shift;
  my $output = shift;
  my $id = shift;
  my $status = shift;
  my $return = "<div class=\"action unit \L$status\E\" id=\"action-$id\">" .
                "<a href=\"javascript:handle('$id');\">" .
                 "<img id=\"img-$id\" src=\"";

  if (defined $status && ($status =~ /failed/i)) {
    $return .= 'icon_hide_24.png';
  }
  else {
    $return .= 'icon_unhide_24.png';
  }

  $return .= "\"> " .
                  "<div class=\"action name\">$name</div>" .
                "</a> ";

  if (defined $status) {
    $return .= "<div class=\"action status \L$status\E\">$status</div>";
  }

  $return .= "<div class=\"action output\" id=\"output-$id\">" .
                 "<pre>Running action $name$output ACTION $status: $name</pre>" .
                "</div>".
               "</div>";

  return $return
}

##############################################
# main page
sub main_menu() {
    print $req->startform("GET");
    print $req->popup_menu(-name=>'host',
			   -values=>\@hosts,
			   -labels=>\%hosts);
    print $req->popup_menu("tree", [sort keys %trees]);
    print $req->popup_menu("compiler", $compilers);
    
    print $req->submit('function', 'View Build');
    print "&nbsp;&nbsp;" . $req->submit('function', 'Recent Checkins');
    print "&nbsp;&nbsp;" . $req->submit('function', 'Summary');
    print "&nbsp;&nbsp;" . $req->submit('function', 'Recent Builds');

    print $req->endform();
}

###############################################
# display top of page
sub page_top() {
    cgi_headers();
    chdir("$BASEDIR/data") || fatal("can't change to data directory");
    main_menu();
}
###############################################
# main program

if (defined $req->param("function")) {
    my $fn_name = $req->param("function");
    if ($fn_name eq "View Build") {
	page_top();
	view_build();
	cgi_footers();
    } elsif ($fn_name eq "Recent Builds") {
	page_top();
	view_recent_builds();
	cgi_footers();
    } elsif ($fn_name eq "Recent Checkins") {
	page_top();
	history::cvs_history($req->param('tree'));
	cgi_footers();
    } elsif ($fn_name eq "diff") {
	page_top();
	history::cvs_diff($req->param('author'), $req->param('date'), $req->param('tree'), "html");
	cgi_footers();
    } elsif ($fn_name eq "text_diff") {
	cgi_headers_diff();
	chdir("$BASEDIR/data") || fatal("can't change to data directory");	
	history::cvs_diff($req->param('author'), $req->param('date'), $req->param('tree'), "text");	
    } else {
	page_top();
	view_summary();
	cgi_footers();
    }
} else {
    page_top();
    view_summary();
    cgi_footers();
}

