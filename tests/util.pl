#!/usr/bin/perl

use lib "..";
use lib "../web";

use Test::More tests => 23;
use strict;

use util;

is(2, util::count_lines("foo\nbar"));
is(1, util::count_lines("bar"));
is(1, util::count_lines(""));

is("&amp;", util::cgi_escape("&"));
is("1 &amp;&amp; 2", util::cgi_escape("1 && 2"));
is("&lt;&gt;", util::cgi_escape("<>"));
is("&amp;amp;", util::cgi_escape("&amp;"));
is("&quot;", util::cgi_escape("\""));
is("nothing", util::cgi_escape("nothing"));

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

1;
