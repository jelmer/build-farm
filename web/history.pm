# Copyright (C) Andrew Tridgell <tridge@samba.org>     2001
# Copyright (C) Martin Pool <mbp@samba.org>            2003
# script to show recent checkins in cvs / bzr / svn

package history;

my $BASEDIR = "/home/build/master";
my $HISTORYDIR = "/home/build/master/cache";
my $TIMEZONE = "PST";
my $TIMEOFFSET = 0;

use strict qw{vars};
use util;
use POSIX;
use Data::Dumper;
use CGI qw/:standard/;
use File::stat;

my $req = new CGI;

my $CVSWEB_BASE = "http://pserver.samba.org/cgi-bin/cvsweb";
my $VIEWCVS_BASE = "http://websvn.samba.org/cgi-bin/viewcvs.cgi";
my $UNPACKED_BASE = "http://svn.samba.org/ftp/unpacked";
my $GITWEB_BASE = "http://gitweb.samba.org/";

# a map of names to web svn log locations
my (%svn_trees) = ('samba' => " <a href=\"$VIEWCVS_BASE/trunk/%s?root=samba\">%s</a>",
		   'samba_3_0' =>" <a href=\"$VIEWCVS_BASE/branches/SAMBA_3_0/%s?root=samba\">%s</a>",
		   'samba_3_2' =>" <a href=\"$VIEWCVS_BASE/branches/SAMBA_3_2/%s?root=samba\">%s</a>",
		   'samba_3_0_release' =>" <a href=\"$VIEWCVS_BASE/branches/SAMBA_3_0_RELEASE/%s?root=samba\">%s</a>",
		   'samba_2_2' =>" <a href=\"$VIEWCVS_BASE/branches/SAMBA_2_2/%s?root=samba\">%s</a>",
		   'samba_2_2_release' =>" <a href=\"$VIEWCVS_BASE/branches/SAMBA_2_2_RELEASE/%s?root=samba\">%s</a>",
		   'samba-docs' => " <a href=\"$VIEWCVS_BASE/trunk/%s?root=samba-docs\">%s</a>",
		   'samba4' => " <a href=\"$VIEWCVS_BASE/branches/SAMBA_4_0/%s?root=samba\">%s</a>",
		   'libreplace' => " <a href=\"$VIEWCVS_BASE/branches/SAMBA_4_0/source/lib/replace/%s?root=samba\">%s</a>",
		   'build_farm' => " <a href=\"$VIEWCVS_BASE/trunk?root=build-farm\">%s</a>",
		   'tdb' => " <a href=\"$VIEWCVS_BASE/branches/SAMBA_4_0/source/lib/tdb/%s?root=samba\">%s</a>",
		   'ldb' => " <a href=\"$VIEWCVS_BASE/branches/SAMBA_4_0/source/lib/ldb/%s?root=samba\">%s</a>",
		   'pidl' => " <a href=\"$VIEWCVS_BASE/branches/SAMBA_4_0/source/pidl/%s?root=samba\">%s</a>",
		   'samba-web' => " <a href=\"$VIEWCVS_BASE/trunk/%s?root=samba-web\">%s</a>",
		   'lorikeet' => " <a href=\"$VIEWCVS_BASE/trunk/%s?root=lorikeet\">%s</a>",
		   'SOC' => " <a href=\"$VIEWCVS_BASE/branches/SOC/%s?root=samba\">%s</a>");

# a map of names to cvs modules
my (%cvs_trees) = ('distcc' => " <a href=\"$CVSWEB_BASE/distcc/%s\">%s</a>",
		   'ccache' => " <a href=\"$CVSWEB_BASE/ccache/%s\">%s</a>",
		   'ppp' => " <a href=\"$CVSWEB_BASE/ppp/%s\">%s</a>");

# a map of names to bzr paths
my (%bzr_trees) = ('ctdb' => " <a href=\"$UNPACKED_BASE/ctdb/%s\">%s</a>",
                   'python' => " <a href=\"$UNPACKED_BASE/python/%s\">%s</a>",
                   'samba-gtk' => " <a href=\"http://people.samba.org/bzr/jelmer/samba-gtk/trunk/%s\">%s</a>");

my (%git_trees) = ('samba_3_2_test' =>" <a href=\"$GITWEB_BASE/?p=samba.git;a=history;f=%s;h=v3-2-test;hb=v3-2-test\">%s</a>",
		   'samba_4_0_test' =>" <a href=\"$GITWEB_BASE/?p=samba.git;a=history;f=%s;h=v4-0-test;hb=v4-0-test\">%s</a>",
		   'talloc' =>" <a href=\"$GITWEB_BASE/?p=samba.git;a=history;f=source/lib/talloc/%s;h=v4-0-test;hb=v4-0-test\">%s</a>",
		   'rsync' =>" <a href=\"$GITWEB_BASE/?p=rsync.git;a=history;f=%s;h=HEAD;hb=HEAD\">%s</a>");

my $unpacked_dir = "/home/ftp/pub/unpacked";

###############################################
# work out a URL so I can refer to myself in links
my $myself = $req->url();

################################################
# print an error on fatal errors
sub fatal($) {
    my $msg=shift;
    print "ERROR: $msg<br />\n";
    cgi_footers();
    exit(0);
}

################################################
# get a param from the request, after sanitizing it
sub get_param($) {
    my $param = shift;
    my $result;

    if (!defined $req->param($param)) {
	return undef;
    }

    $result = $req->param($param);
    $result =~ s/ /_/g; # fn_name ha

    if ($result =~ m/[^a-zA-Z0-9\-]/) {
	fatal("Parameter $param is invalid");
	return undef;
    }
    else {
	return $result;
    }
}


###############################################
# pretty up a cvs diff -u
sub diff_pretty($)
{
    my $diff = shift;
    my $ret = "";
    my @lines = split(/$/m, $diff);

    my %line_types = (
		    '^diff.*' => 'diff_diff',
		    '^=.*' => 'diff_separator',
		    '^Index:.*' => 'diff_index',
		    '^index.*' => 'diff_index',
		    '^\-.*' => 'diff_removed',
		    '^\+.*' => 'diff_added',
		    '^@@.*' => 'diff_fragment_header'
		    );

    foreach my $line (@lines) {
	for my $r (keys %line_types) {
	    if ($line =~ /$r/m) {
		$line = "<span class=\"$line_types{$r}\">$line</span>";
		last;
	    }
	}
	$ret .= $line;
    }
    return $ret;
}

###############################################
# change the given source paths into links
sub web_paths($$)
{
    my ($tree, $paths) = @_;
    my $ret = "";

    if (grep {/$tree/} keys %cvs_trees) {
      while ($paths =~ /\s*([^\s]+)(.*)/) {
	$ret .= sprintf($cvs_trees{$tree}, $1, $1);
	$paths = $2;
      }
    } elsif (grep {/$tree/} keys %svn_trees) {
	    while ($paths =~ /\s*([^\s]+)(.*)/) {
	    
		    $ret .= sprintf($svn_trees{$tree}, $1, $1);
		    $paths = $2;
	    }
    } elsif (grep {/$tree/} keys %bzr_trees) {
	    while ($paths =~ /\s*([^\s]+)(.*)/) {
		    $ret .= sprintf($bzr_trees{$tree}, $1, $1);
		    $paths = $2;
	    }
    } elsif(grep {/$tree/} keys %git_trees) {
	    while ($paths =~ /\s*([^\s]+)(.*)/) {
		    $ret .= sprintf($git_trees{$tree}, $1, $1);
		    $paths = $2;
	    }
    } else {
	    $ret .= $paths;
    }

    return $ret;
}

#############################################
# show one row of history table
sub history_row($$)
{
    my ($entry, $tree) = @_;
    my $msg = escapeHTML($entry->{MESSAGE});
    my $t = POSIX::asctime(POSIX::gmtime($entry->{DATE}));
    my $age = util::dhm_time(time()-$entry->{DATE});

    $t =~ s/\ /&nbsp;/g;

    print "
<div class=\"history_row\">
    <div class=\"datetime\">
        <span class=\"date\">$t</span><br />
        <span class=\"age\">$age ago</span>";

    my $revision_url = "";
    if ($entry->{REVISION}) {
	    print " - <span class=\"revision\">$entry->{REVISION}</span><br />";
	    $revision_url = ";revision=$entry->{REVISION}";
    }

    print "    </div>
    <div class=\"diff\">
        <span class=\"html\"><a href=\"$myself?function=diff;tree=$tree;date=$entry->{DATE};author=$entry->{AUTHOR}$revision_url\">show diffs</a></span>
    <br />
        <span class=\"text\"><a href=\"$myself?function=text_diff;tree=$tree;date=$entry->{DATE};author=$entry->{AUTHOR}$revision_url\">download diffs</a></span>
        <br />
        <div class=\"history_log_message\">
            <pre>$msg</pre>
        </div>
    </div>
    <div class=\"author\">
    <span class=\"label\">Author: </span>$entry->{AUTHOR}
    </div>";

    if ($entry->{FILES}) {
	print "<div class=\"files\"><span class=\"label\">Modified: </span>";
	print web_paths($tree, $entry->{FILES});
	print "</div>\n";
    }

    if ($entry->{ADDED}) {
	print "<div class=\"files\"><span class=\"label\">Added: </span>";
	print web_paths($tree, $entry->{ADDED});
	print "</div>\n";
    }

    if ($entry->{REMOVED}) {
	print "<div class=\"files\"><span class=\"label\">Removed: </span>";
	print web_paths($tree, $entry->{REMOVED});
	print "</div>\n";
    }

    print "</div>\n";
}


#############################################
# show one row of history table
sub history_row_text($$)
{
    my ($entry, $tree) = @_;
    my $msg = escapeHTML($entry->{MESSAGE});
    my $t = POSIX::asctime(POSIX::gmtime($entry->{DATE}));
    my $age = util::dhm_time(time()-$entry->{DATE});

    print "Author: $entry->{AUTHOR}\n";
    if ($entry->{REVISION}) {
	    print "Revision: $entry->{REVISION}\n";
    }
    print "Modified: $entry->{FILES}\n";
    print "Added: $entry->{ADDED}\n";
    print "Removed: $entry->{REMOVED}\n";
    print "\n\n$msg\n\n\n";
}

###############################################
# get recent cvs/svn entries
sub diff($$$$$)
{
    my ($author, $date, $tree, $revision, $text_html) = @_;

    # validate the tree
    util::InArray($tree, [keys %cvs_trees, keys %svn_trees, keys %bzr_trees, keys %git_trees]) || fatal("unknown tree");

    chdir("$unpacked_dir/$tree") || fatal("no tree $unpacked_dir/$tree available");

    if (grep {/$tree/} keys %cvs_trees) {
		cvs_diff($author, $date, $tree, $text_html);
    } elsif (grep {/$tree/} keys %bzr_trees) {
		bzr_diff($revision, $tree, $text_html);
    } elsif (grep {/$tree/} keys %svn_trees) {
		svn_diff($revision, $tree, $text_html);
    } elsif (grep {/$tree/} keys %git_trees) {
		git_diff($revision, $tree, $text_html);
    }
}

###############################################
# show recent svn entries
sub svn_diff($$$)
{
    my ($revision, $tree, $text_html) = @_;

    # ensure the user-specified tree is a valid tree
    util::InArray($tree, [keys %svn_trees]) || fatal("unknown svn tree");

    chdir("$unpacked_dir/$tree") || fatal("no tree $unpacked_dir/$tree available");

    # determine the most recent version known to this database
    my ($current_revision) = grep {/^Revision/} `svn info`;
    chomp $current_revision;
    $current_revision =~ s/.*?(\d+)$/$1/;

    fatal("unknown revision") if ($revision !~ /^\d+$/ or $revision < 0 or
		                          $revision > $current_revision);

    my $log = util::LoadStructure("$HISTORYDIR/history.$tree");
    my $entry;

    # backwards? why? well, usually our users are looking for the newest
    # stuff, so it's most likely to be found sooner
    my $i = $#{$log};
    for (; $i >= 0; $i--) {
	    if ($log->[$i]->{REVISION} eq $revision) {
		    $entry = $log->[$i];
	    }
    }

    # get information about the current diff
    if ($text_html eq "html") {
	print "<h2>SVN Diff in $tree for revision r$revision</h2>\n";
	print "<div class=\"history row\">\n";

	if (!defined($entry->{REVISION})) {
	    print "Unable to locate commit information.\n";
	} else {
	    history_row($entry, $tree);
	}

	print "</div>\n";
    }
    else {
	if (!defined($entry->{REVISION})) {
	    print "Unable to locate commit information.\n";
	} else {
	    history_row_text($entry, $tree);
	}
    }


    my $old_revision = $revision - 1;
    my $cmd = "svn diff -r $old_revision:$revision";

    my $diff = `$cmd 2> /dev/null`;

    if ($text_html eq "html") {
	print "<!-- $cmd -->\n";
	$diff = escapeHTML($diff);
	$diff = diff_pretty($diff);
	print "<pre>$diff</pre>\n";
    }
    else {
	print "$diff\n";
    }
}

###############################################
# show recent cvs entries
sub cvs_diff($$$$)
{
    my ($author, $date, $tree, $text_html) = @_;
    my $module;

    my $log = util::LoadStructure("$HISTORYDIR/history.$tree");

    # ensure the user-specified tree is a valid tree
    util::InArray($tree, [keys %cvs_trees]) || fatal("unknown cvs tree");

    # for paranoia, check that the date string is a valid date
    if ($date =~ /[^\d]/) {
	    fatal("unknown date");
    }

    $module = $cvs_trees{$tree};

    for (my $i=0; $i <= $#{$log}; $i++) {
	my $entry = $log->[$i];
	if ($author eq $entry->{AUTHOR} &&
	    $date == $entry->{DATE}) {
	    my $t1;
	    my $t2;

	    chomp($t1 = POSIX::ctime($date-60+($TIMEOFFSET*60*60)));
	    chomp($t2 = POSIX::ctime($date+60+($TIMEOFFSET*60*60)));

	    if ($text_html eq "html") {
		print "<h2>CVS Diff in $tree for $t1</h2>\n";
		
		history_row($entry, $tree);
	    } else {
		history_row_text($entry, $tree);
	    }

	    if (! ($entry->{TAG} eq "") && !$entry->{REVISIONS}) {
		print '
<br />
<b>sorry, cvs diff on branches not currently possible due to a limitation 
in cvs</b>
<br />';
	    }

	    $ENV{'CVS_PASSFILE'} = "$BASEDIR/.cvspass";

	    if ($entry->{REVISIONS}) {
		    for my $f (keys %{$entry->{REVISIONS}}) {
			my $cmd;
			my $diff;
			my $fix_diff = 0;
			if ($entry->{REVISIONS}->{$f}->{REV1} eq "NONE") {
			    $cmd = "cvs rdiff -u -r 0 -r $entry->{REVISIONS}->{$f}->{REV2} $module/$f";
			    $fix_diff = 1;
			} elsif ($entry->{REVISIONS}->{$f}->{REV2} eq "NONE") {
			    $cmd = "cvs rdiff -u -r $entry->{REVISIONS}->{$f}->{REV1} -r 0 $module/$f";
			    $fix_diff = 1;
			} elsif ($text_html eq "html") {
			    $cmd = "cvs diff -b -u -r $entry->{REVISIONS}->{$f}->{REV1} -r $entry->{REVISIONS}->{$f}->{REV2} $f";
			} else {
			    $cmd = "cvs diff -u -r $entry->{REVISIONS}->{$f}->{REV1} -r $entry->{REVISIONS}->{$f}->{REV2} $f";
			}

			$diff = `$cmd 2> /dev/null`;
			if ($fix_diff) {
			    $diff =~ s/^--- $module\//--- /mg;
			    $diff =~ s/^\+\+\+ $module\//\+\+\+ /mg;
			}
			
			if ($text_html eq "html") { 
			    print "<!-- $cmd -->\n";
			    $diff = escapeHTML($diff);
			    $diff = diff_pretty($diff);
			    print "<pre>$diff</pre>\n";
			} else {
			    print "$diff\n";
			}
		    }
	    } else {
		    my $cmd;
		    if ($text_html eq "html") { 
			$cmd = "cvs diff -b -u -D \"$t1 $TIMEZONE\" -D \"$t2 $TIMEZONE\" $entry->{FILES}";
		    } else {
			$cmd = "cvs diff -u -D \"$t1 $TIMEZONE\" -D \"$t2 $TIMEZONE\" $entry->{FILES}";
		    }

		    my $diff = `$cmd 2> /dev/null`;

		    if ($text_html eq "html") { 
			print "<!-- $cmd -->\n";
			$diff = escapeHTML($diff);
			$diff = diff_pretty($diff);
			print "<pre>$diff</pre>\n";
		    }
		    else {
			print "$diff\n";
		    }

	    }

	    return;
	}
    }
}


###############################################
# show recent bzr entries
sub bzr_diff($$$)
{
    my ($revision, $tree, $text_html) = @_;

    # ensure the user-specified tree is a valid tree
    util::InArray($tree, [keys %bzr_trees]) || fatal("unknown bzr tree $tree");

    chdir("$unpacked_dir/$tree") || fatal("no tree $unpacked_dir/$tree available");

    my $log = util::LoadStructure("$HISTORYDIR/history.$tree");
    my $entry;

    # backwards? why? well, usually our users are looking for the newest
    # stuff, so it's most likely to be found sooner
    my $i = $#{$log};
    for (; $i >= 0; $i--) {
	    if ($log->[$i]->{REVISION} eq $revision) {
		    $entry = $log->[$i];
	    }
    }

    # get information about the current diff
    if ($text_html eq "html") {
	print "<h2>bzr Diff in $tree for revision r$revision</h2>\n";
	print "<div class=\"history row\">\n";

	if (!defined($entry->{REVISION})) {
	    print "Unable to locate commit information.\n";
	} else {
	    history_row($entry, $tree);
	}

	print "</div>\n";
    }
    else {
	if (!defined($entry->{REVISION})) {
	    print "Unable to locate commit information.\n";
	} else {
	    history_row_text($entry, $tree);
	}
    }


    my $old_revision = $revision - 1;
    my $cmd = "bzr diff -r $old_revision..$revision";

    my $diff = `$cmd 2> /dev/null`;

    if ($text_html eq "html") {
	print "<!-- $cmd -->\n";
	$diff = escapeHTML($diff);
	$diff = diff_pretty($diff);
	print "<pre>$diff</pre>\n";
    } else {
	print "$diff\n";
    }
}

###############################################
# show recent git entries
sub git_diff($$$)
{
    my ($revision, $tree, $text_html) = @_;

    # ensure the user-specified tree is a valid tree
    util::InArray($tree, [keys %git_trees]) || fatal("unknown git tree");

    chdir("$unpacked_dir/$tree") || fatal("no tree $unpacked_dir/$tree available");

#    my $checkrev = `git log -1 --pretty=format:%H $revision`;
#    fatal("unknown revision") if ($revision ne $checkrev);

    my $log = util::LoadStructure("$HISTORYDIR/history.$tree");
    my $entry;

    # backwards? why? well, usually our users are looking for the newest
    # stuff, so it's most likely to be found sooner
    for (my $i = $#{$log}; $i >= 0; $i--) {
	    if ($log->[$i]->{REVISION} eq $revision) {
		    $entry = $log->[$i];
	    }
    }

    # get information about the current diff
    if ($text_html eq "html") {
	print "<h2>GIT Diff in $tree for revision $revision</h2>\n";
	print "<div class=\"history row\">\n";

	if (!defined($entry->{REVISION})) {
	    print "Unable to locate commit information.\n";
	} else {
	    history_row($entry, $tree);
	}

	print "</div>\n";
    }
    else {
	if (!defined($entry->{REVISION})) {
	    print "Unable to locate commit information.\n";
	} else {
	    history_row_text($entry, $tree);
	}
    }

    my $cmd = "git diff $revision^ $revision ./";

    my $diff = `$cmd 2> /dev/null`;

    if ($text_html eq "html") {
	print "<!-- $cmd -->\n";
	$diff = escapeHTML($diff);
	$diff = diff_pretty($diff);
	print "<pre>$diff</pre>\n";
    }
    else {
	print "$diff\n";
    }
}

###############################################
# get commit history for the given tree
sub history($)
{
    my $tree = shift;
    my (%authors) = ('ALL' => 1);
    my $author;

    # ensure that the tree is a valid tree
##    util::InArray($tree, [keys %svn_trees, keys %cvs_trees, keys %bzr_trees]) ||
    util::InArray($tree, [keys %svn_trees, keys %cvs_trees, keys %bzr_trees, keys %git_trees]) ||
	      fatal("unknown tree");

    my $log = util::LoadStructure("$HISTORYDIR/history.$tree");

    for (my $i=$#{$log}; $i >= 0; $i--) {
	$authors{$log->[$i]->{AUTHOR}} = 1;
    }

    print "<h2>Recent checkins for $tree</h2>\n";
    print $req->startform("GET");
    print "Select Author: ";
    print $req->popup_menu("author", [sort keys %authors]);
    print $req->submit('sub_function', 'Refresh');
    print $req->hidden('tree', $tree);
    print $req->hidden('function', 'Recent Checkins');
    print $req->endform();

    
    print "
";

    $author = get_param("author");

    # what? backwards? why is that? oh... I know... we want the newest first
    for (my $i=$#{$log}; $i >= 0; $i--) {
	my $entry = $log->[$i];
	if (! $author ||
	    ($author eq "ALL") ||
	    ($author eq $entry->{AUTHOR})) {
	    history_row($entry, $tree);
	}
    }
    print '
';

}

#cvs_diff(get_param('author'), get_param('date'), get_param('tree'));
#cvs_history("trinity");

1;
