#!/usr/bin/python
# Copyright (C) Jelmer Vernooij <jelmer@samba.org> 2010
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License, or
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

import os
import tempfile
import testtools
import unittest

from buildfarm import util

class CountLinesTests(unittest.TestCase):

    def test_simple(self):
        self.assertEquals(2, util.count_lines("foo\nbar"))
        self.assertEquals(1, util.count_lines("bar"))
        self.assertEquals(1, util.count_lines(""))


class ChangeExtensionTests(unittest.TestCase):

    def test_simple(self):
        self.assertEquals("foo.bar", util.ChangeExtension("foo.old", "bar"))
        self.assertEquals("foo.png", util.ChangeExtension("foo.png", "png"))
        self.assertEquals("foobar.png", util.ChangeExtension("foobar", "png"))


class DhmTimeTests(unittest.TestCase):

    def test_simple(self):
        self.assertEquals("0s", util.dhm_time(0))
        self.assertEquals("1m", util.dhm_time(61))
        self.assertEquals("-", util.dhm_time(-20))
        self.assertEquals("1d 3h 1m", util.dhm_time(97265))
        self.assertEquals("3h 1m", util.dhm_time(10865))


class LoadTests(testtools.TestCase):

    def test_simple(self):
        fd, name = tempfile.mkstemp()
        self.addCleanup(os.remove, name)
        f = os.fdopen(fd, 'w')
        f.write("""one
two
three

for
""")
        f.close()
        l = util.load_list(name)
        self.assertEquals(4, len(l))
        self.assertEquals("three", l[2])


class StripHtmlTests(unittest.TestCase):

    def test_simple(self):
        self.assertEquals("", util.strip_html("<!--foo-->"))
        self.assertEquals("bar ", util.strip_html("<!--foo-->bar <!--bloe-->"))
        self.assertEquals("bar <bloe>", util.strip_html("<bar>bar <bloe></bar>"))
        self.assertEquals("", util.strip_html("<bar><bloe></bloe></bar>"))

        self.assertEquals("bla", util.strip_html("<a href=\"foo\">bla</a>"))
