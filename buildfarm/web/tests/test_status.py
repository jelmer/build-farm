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

from buildfarm.data import BuildStatus
from buildfarm.web import html_build_status

import testtools

class BuildStatusHtmlTests(testtools.TestCase):

    def test_empty(self):
        status = BuildStatus()
        self.assertEquals("?", html_build_status(status))

    def test_failed_build(self):
        status = BuildStatus([("CONFIGURE", 0), ("BUILD", 4)])
        self.assertEquals(
            '<span class="status passed">ok</span>/<span class="status failed">4</span>',
            html_build_status(status))

    def test_disk_full(self):
        status = BuildStatus([("CONFIGURE", 0), ("BUILD", 4)], set(["timeout"]))
        self.assertEquals(
            '<span class="status passed">ok</span>/<span class="status failed">4</span>'
            '(<span class="status failed">timeout</span>)', html_build_status(status))
