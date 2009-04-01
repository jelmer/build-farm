# Copyright (C) Andrew Tridgell <tridge@samba.org>     2001
# Copyright (C) Martin Pool <mbp@samba.org>            2003
# script to show recent checkins in cvs / svn / git

package history;

use util;
use POSIX;
use Data::Dumper;
use CGI qw/:standard/;
use File::stat;

require Exporter;
@ISA = qw(Exporter);
@EXPORT_OK = qw();

use strict;
use warnings;

my $BASEDIR = "/home/build/master";
my $HISTORYDIR = "/home/build/master/cache";
my $TIMEZONE = "PST";
my $TIMEOFFSET = 0;
my $unpacked_dir = "/home/ftp/pub/unpacked";

my $CVSWEB_BASE = "http://pserver.samba.org/cgi-bin/cvsweb";
my $VIEWCVS_BASE = "http://websvn.samba.org/cgi-bin/viewcvs.cgi";
my $UNPACKED_BASE = "http://svn.samba.org/ftp/unpacked";
my $GITWEB_BASE = "http://gitweb.samba.org";

sub new($$) {
	my ($this, $req, $db) = @_;

	my $self = {
		'req'	=> $req,
		'db'	=> $db,
		'url'	=> $req->url()
	};

	bless $self;
	return $self;
}

################################################
# print an error on fatal errors
sub fatal($$) {
	my ($self, $msg) = @_;
	print "ERROR: $msg<br />\n";
	cgi_footers();
	exit(0);
}

################################################
# get a param from the request, after sanitizing it
sub get_param($$) {
	my ($self, $param) = @_;
	my $result;

	my $req = $self->{req};

	$result = $req->param($param);
	return undef unless defined($result);

	$result =~ s/ /_/g; # fn_name ha

	if ($result =~ m/[^a-zA-Z0-9\-]/) {
		$self->fatal("Parameter $param is invalid");
		return undef;
	}

	return $result;
}


###############################################
# pretty up a cvs diff -u
sub diff_pretty($$)
{
	my ($self, $diff) = @_;;
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
sub web_paths($$$)
{
	my ($self, $tree, $paths) = @_;
	my $ret = "";

	my %trees = %{$self->{db}->{trees}};
	my $t = $trees{$tree};

	return $paths unless defined($t);

	my $fmt = undef;

	if ($t->{scm} eq "cvs") {
		$fmt = " <a href=\"$CVSWEB_BASE/$t->{repo}/%s\">%s</a>";
	} elsif ($t->{scm} eq "svn") {
		$fmt = " <a href=\"$VIEWCVS_BASE/$t->{branch}/%s?root=$t->{repo}\">%s</a>";
	} elsif ($t->{scm} eq "git") {
		my $r = $t->{repo};
		my $s = $t->{subdir};
		my $b = $t->{branch};
		$fmt = " <a href=\"$GITWEB_BASE/?p=$r;a=history;f=$s%s;h=$b;hb=$b\">%s</a>";
	} else {
		return $paths;
	}

	while ($paths =~ /\s*([^\s]+)(.*)/) {
		$ret .= sprintf($fmt, $1, $1);
		$paths = $2;
	}

	return $ret;
}

#############################################
# show one row of history table
sub history_row($$$)
{
	my ($self, $entry, $tree) = @_;
	my $msg = escapeHTML($entry->{MESSAGE});
	my $t = POSIX::asctime(POSIX::gmtime($entry->{DATE}));
	my $age = util::dhm_time(time()-$entry->{DATE});

	$t =~ s/\ /&nbsp;/g;

	print "
<div class=\"history_row\">
    <div class=\"datetime\">
        <span class=\"date\">$t</span><br />
        <span class=\"age\">$age ago</span>";
	my $revision_url;
	if ($entry->{REVISION}) {
		print " - <span class=\"revision\">$entry->{REVISION}</span><br />";
		$revision_url = "revision=$entry->{REVISION}";
	} else {
		$revision_url = "author=$entry->{AUTHOR}"
	}
	print "    </div>
    <div class=\"diff\">
        <span class=\"html\"><a href=\"$self->{url}?function=diff;tree=$tree;date=$entry->{DATE};$revision_url\">show diffs</a></span>
    <br />
        <span class=\"text\"><a href=\"$self->{url}?function=text_diff;tree=$tree;date=$entry->{DATE};$revision_url\">download diffs</a></span>
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
		print $self->web_paths($tree, $entry->{FILES});
		print "</div>\n";
	}

	if ($entry->{ADDED}) {
		print "<div class=\"files\"><span class=\"label\">Added: </span>";
		print $self->web_paths($tree, $entry->{ADDED});
		print "</div>\n";
	}

	if ($entry->{REMOVED}) {
		print "<div class=\"files\"><span class=\"label\">Removed: </span>";
		print $self->web_paths($tree, $entry->{REMOVED});
		print "</div>\n";
	}

	print "</div>\n";
}


#############################################
# show one row of history table
sub history_row_text($$$)
{
	my ($self, $entry, $tree) = @_;
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
sub diff($$$$$$)
{
	my ($self, $author, $date, $tree, $revision, $text_html) = @_;

	# validate the tree
	my %trees = %{$self->{db}->{trees}};
	my $t = $trees{$tree};
	$self->fatal("unknown tree[$tree]") unless defined($t);

	if ($t->{scm} eq "cvs") {
		$self->cvs_diff($t, $author, $date, $tree, $text_html);
	} elsif ($t->{scm} eq "svn") {
		$self->svn_diff($t, $revision, $tree, $text_html);
	} elsif ($t->{scm} eq "git") {
		$self->git_diff($t, $revision, $tree, $text_html);
	}
}

###############################################
# show recent svn entries
sub svn_diff($$$$$)
{
	my ($self, $t, $revision, $tree, $text_html) = @_;

	chdir("$unpacked_dir/$tree") or $self->fatal("no tree $unpacked_dir/$tree available");

	# determine the most recent version known to this database
	my ($current_revision) = grep {/^Revision/} `svn info`;
	chomp $current_revision;
	$current_revision =~ s/.*?(\d+)$/$1/;

	if ($revision !~ /^\d+$/ or $revision < 0 or $revision > $current_revision) {
		$self->fatal("unknown revision[$revision]");
	}

	my $log = util::LoadStructure("$HISTORYDIR/history.$tree");
	my $entry = undef;

	# backwards? why? well, usually our users are looking for the newest
	# stuff, so it's most likely to be found sooner
	my $i = $#{$log};
	for (; $i >= 0; $i--) {
		if ($log->[$i]->{REVISION} eq $revision) {
			$entry = $log->[$i];
			last;
		}
	}

	if (not defined($entry)) {
		print "Unable to locate commit information revision[$revision].\n";
		return;
	}

	# get information about the current diff
	if ($text_html eq "html") {
		print "<h2>SVN Diff in $tree:$t->{branch} for revision r$revision</h2>\n";
		print "<div class=\"history row\">\n";

		$self->history_row($entry, $tree);

		print "</div>\n";
	} else {
		$self->history_row_text($entry, $tree);
	}

	my $old_revision = $revision - 1;
	my $cmd = "svn diff -r $old_revision:$revision";

	my $diff = `$cmd 2> /dev/null`;

	if ($text_html eq "html") {
		print "<!-- $cmd -->\n";
		$diff = escapeHTML($diff);
		$diff = $self->diff_pretty($diff);
		print "<pre>$diff</pre>\n";
	} else {
		print "$diff\n";
	}
}

###############################################
# show recent cvs entries
sub cvs_diff($$$$$$)
{
	my ($self, $t, $author, $date, $tree, $text_html) = @_;

	chdir("$unpacked_dir/$tree") or $self->fatal("no tree $unpacked_dir/$tree available");

	my $log = util::LoadStructure("$HISTORYDIR/history.$tree");

	# for paranoia, check that the date string is a valid date
	if ($date =~ /[^\d]/) {
		$self->fatal("unknown date");
	}

	my $entry = undef;

	for (my $i=0; $i <= $#{$log}; $i++) {
		if ($author eq $entry->{AUTHOR} &&
		    $date == $entry->{DATE}) {
			$entry = $log->[$i];
			last;
		}
	}

	if (not defined($entry)) {
		print "Unable to locate commit information author[$author] data[$date].\n";
		return;
	}

	my $t1;
	my $t2;

	chomp($t1 = POSIX::ctime($date-60+($TIMEOFFSET*60*60)));
	chomp($t2 = POSIX::ctime($date+60+($TIMEOFFSET*60*60)));

	if ($text_html eq "html") {
		print "<h2>CVS Diff in $tree:$t->{branch} for $t1</h2>\n";
		$self->history_row($entry, $tree);
	} else {
		$self->history_row_text($entry, $tree);
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
			if ($entry->{REVISIONS}->{$f}->{REV1} eq "NONE") {
				$cmd = "cvs rdiff -u -r 0 -r $entry->{REVISIONS}->{$f}->{REV2} $f";
			} elsif ($entry->{REVISIONS}->{$f}->{REV2} eq "NONE") {
				$cmd = "cvs rdiff -u -r $entry->{REVISIONS}->{$f}->{REV1} -r 0 $f";
			} elsif ($text_html eq "html") {
				$cmd = "cvs diff -b -u -r $entry->{REVISIONS}->{$f}->{REV1} -r $entry->{REVISIONS}->{$f}->{REV2} $f";
			} else {
				$cmd = "cvs diff -u -r $entry->{REVISIONS}->{$f}->{REV1} -r $entry->{REVISIONS}->{$f}->{REV2} $f";
			}

			$diff = `$cmd 2> /dev/null`;
			if ($text_html eq "html") { 
				print "<!-- $cmd -->\n";
				$diff = escapeHTML($diff);
				$diff = $self->diff_pretty($diff);
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
			$diff = $self->diff_pretty($diff);
			print "<pre>$diff</pre>\n";
		} else {
			print "$diff\n";
		}
	}
}

###############################################
# show recent git entries
sub git_diff($$$$$)
{
	my ($self, $t, $revision, $tree, $text_html) = @_;

	chdir("$unpacked_dir/$tree") or $self->fatal("no tree $unpacked_dir/$tree available");

	my $log = util::LoadStructure("$HISTORYDIR/history.$tree");
	my $entry = undef;

	# backwards? why? well, usually our users are looking for the newest
	# stuff, so it's most likely to be found sooner
	for (my $i = $#{$log}; $i >= 0; $i--) {
		if ($log->[$i]->{REVISION} eq $revision) {
			$entry = $log->[$i];
			last;
		}
	}

	if (not defined($entry)) {
		print "Unable to locate commit information revision[$revision].\n";
		return;
	}

	# get information about the current diff
	if ($text_html eq "html") {
		print "<h2>GIT Diff in $tree:$t->{branch} for revision $revision</h2>\n";
		print "<div class=\"history row\">\n";

		$self->history_row($entry, $tree);

		print "</div>\n";
	} else {
		$self->history_row_text($entry, $tree);
	}

	my $cmd = "git diff $revision^ $revision ./";

	my $diff = `$cmd 2> /dev/null`;

	if ($text_html eq "html") {
		print "<!-- $cmd -->\n";
		$diff = escapeHTML($diff);
		$diff = $self->diff_pretty($diff);
		print "<pre>$diff</pre>\n";
	} else {
		print "$diff\n";
	}
}

###############################################
# get commit history for the given tree
sub history($$)
{
	my ($self, $tree) = @_;
	my (%authors) = ('ALL' => 1);
	my $author;

	# validate the tree
	my %trees = %{$self->{db}->{trees}};
	my $t = $trees{$tree};
	$self->fatal("unknown tree[$tree]") unless defined($t);

	my $log = util::LoadStructure("$HISTORYDIR/history.$tree");

	for (my $i=$#{$log}; $i >= 0; $i--) {
		$authors{$log->[$i]->{AUTHOR}} = 1;
	}

	my $req = $self->{req};

	print "<h2>Recent checkins for $tree ($t->{scm} branch $t->{branch})</h2>\n";
	print $req->startform("GET");
	print "Select Author: ";
	print $req->popup_menu("author", [sort keys %authors]);
	print $req->submit('sub_function', 'Refresh');
	print $req->hidden('tree', $tree);
	print $req->hidden('function', 'Recent Checkins');
	print $req->endform();
	print "\n";

	$author = $self->get_param("author");

	# what? backwards? why is that? oh... I know... we want the newest first
	for (my $i=$#{$log}; $i >= 0; $i--) {
		my $entry = $log->[$i];
		if (not defined($author) or
		    ($author eq "") or
		    ($author eq "ALL") or
		    ($author eq $entry->{AUTHOR})) {
			$self->history_row($entry, $tree);
		}
	}
	print "\n";
}

1;
