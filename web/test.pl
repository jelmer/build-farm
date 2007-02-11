#!/usr/bin/perl

print "Content-Type: text/html\n\n";

use DBI;

use FindBin qw($RealBin);
use DBI;
use strict;
use warnings;
use util;
use CGI;
use URI::Escape;

my $dbh = DBI->connect( "dbi:SQLite:$RealBin/../data.dbl" ) || die "Cannot connect: $DBI::errstr";

my $cgi = new CGI;

sub show_summary($)
{
	my $tree = shift;

	print $cgi->start_table();
	print "<thead><tr><td>Test</td><td>Breakages</td><td>Hosts</td></tr></thead>\n";
	print "<tbody>\n";

	my $failed = {};
	my $success = {};

	my $resultref = $dbh->selectall_arrayref("SELECT test_run.test AS test, build.host AS host, build.compiler AS compiler, test_run.result AS testresult, build.revision AS revision, build.checksum AS checksum FROM build, test_run WHERE build.tree = ? AND test_run.build = build.id GROUP BY test, host, compiler ORDER BY revision DESC", undef, $tree);
	foreach (@$resultref) {
		unless (defined($failed->{$_->[0]})) { $failed->{$_->[0]} = []; }
		unless (defined($success->{$_->[0]})) { $success->{$_->[0]} = 0; }
		if ($_->[3] eq "FAILED") { push(@{$failed->{$_->[0]}}, $_); }
		elsif ($_->[3] eq "PASSED") { $success->{$_->[0]}++; }
		elsif ($_->[3] eq "SKIPPED") {}
		else {
			print "Unknown test result $_->[3]<br>";
		}
	}

	foreach (keys %$failed) {
		next if ($#{$failed->{$_}} == -1);
		
		my $numfails = $#{$failed->{$_}}+1;
		
		print "<tr>" . $cgi->td($cgi->a({-href=>"/test.pl?test=".uri_escape($_)}, $_));

		printf "<td>$numfails (%.2f%%)</td><td>", ($numfails / ($numfails+$success->{$_}) * 100.0);

		foreach (@{$failed->{$_}}) {
			print $cgi->a({-href=>"/test.pl?build=".uri_escape($_->[5]).";test=".uri_escape($_->[0])}, "$_->[1]/$_->[2]($_->[4])"). " ";
		}

		print "</td></tr>\n";
	}

	print "</tbody>\n";
	print $cgi->end_table;
}

sub show_test_host($$)
{
	my ($test, $build) = @_;

	my @resultref = $dbh->selectrow_array("SELECT test_run.output FROM test_run, build WHERE test_run.build = build.id AND build.checksum = ? AND test_run.test = ? ORDER BY build.revision LIMIT 1", undef, $build, $test);
	print $cgi->pre($resultref[0]);
}

sub show_test($)
{
	my ($test) = @_;
	my $resultref = $dbh->selectall_arrayref("SELECT build.host, build.compiler, build.revision, test_run.output FROM test_run, build WHERE build.id = test_run.build AND test_run.test = ? ORDER BY test_run.result", undef, $test);
	foreach (@$resultref) {
		print $cgi->h2($_->[0]);
		print $cgi->pre($_->[3]);
	}
}

if (defined($cgi->param('test')) and defined($cgi->param('build'))) {
	show_test_host($cgi->param('test'), $cgi->param('build'));
} elsif (defined($cgi->param('test'))) {
	show_test($cgi->param('test'));
} else {
	show_summary("samba4");
}

1;
