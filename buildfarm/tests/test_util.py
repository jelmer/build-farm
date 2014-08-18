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

class SambaWebFileLoadTest(testtools.TestCase):

    def test_simple(self):
        fd, name = tempfile.mkstemp()
        self.addCleanup(os.remove, name)
        f = os.fdopen(fd, 'w')
        f.write('href="/samba/index.html"')
        f.close()
        l = util.SambaWebFileLoad(os.getcwd(),name)
        self.assertEquals('href="http://www.samba.org/samba/index.html"', l)
        fd1, name1 = tempfile.mkstemp()
        self.addCleanup(os.remove, name1)
        f1 = os.fdopen(fd1, 'w')
        f1.write('<!--#include virtual="/samba/name2" -->')
        f1.close()
        l1 = util.SambaWebFileLoad(os.path.dirname(os.path.realpath("name1")),name1)
        self.assertEquals('', l1)

