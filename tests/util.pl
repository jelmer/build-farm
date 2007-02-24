#!/usr/bin/perl

use FindBin qw($RealBin);

use lib "$RealBin/..";
use lib "$RealBin/../web";

use Test::More tests => 22;
use CGI qw/:standard/;
use strict;

use util;

is(2, util::count_lines("foo\nbar"));
is(1, util::count_lines("bar"));
is(1, util::count_lines(""));

is("foo.bar", util::ChangeExtension("foo.old", "bar"));
is("foo.png", util::ChangeExtension("foo.png", "png"));
is("foobar.png", util::ChangeExtension("foobar", "png"));

is("0s", util::dhm_time(0));
is("1m", util::dhm_time(61));
is("-", util::dhm_time(-20));
is("1d 3h 1m", util::dhm_time(97265));
is("3h 1m", util::dhm_time(10865));

is_deeply([1, 2, 3], util::FlattenArray([[1, 2], [3]]));
is_deeply([1, [2], 3], util::FlattenArray([[1, [2]], [3]]));

is_deeply({a => 1, b => "a" },
		 util::FlattenHash([{a => 1}, {b => "a"}]));

ok(util::InArray("a", ["a", "b", "c"]));
ok(not util::InArray("a", ["b", "c"]));
ok(util::InArray("a", ["b", "c", "a"]));

is("", util::strip_html("<!--foo-->"));
is("bar ", util::strip_html("<!--foo-->bar <!--bloe-->"));
is("bar <bloe>", util::strip_html("<bar>bar <bloe></bar>"));
is("", util::strip_html("<bar><bloe></bloe></bar>"));

is("bla", util::strip_html("<a href=\"foo\">bla</a>"));

1;
