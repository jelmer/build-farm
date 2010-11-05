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

import unittest

from buildfarm import hostdb


class HostTests(unittest.TestCase):

    def test_create_simple(self):
        host = hostdb.Host(name="foo")
        self.assertEquals(None, host.owner)
        self.assertEquals("foo", host.name)

    def test_create_with_owner(self):
        host = hostdb.Host(name="foo", owner="Jelmer", owner_email="jelmer@samba.org")
        self.assertEquals(("Jelmer", "jelmer@samba.org"), host.owner)
        self.assertEquals("foo", host.name)



class DatabaseTests(unittest.TestCase):

    def setUp(self):
        super(DatabaseTests, self).setUp()
        self.db = hostdb.HostDatabase()

    def test_createhost(self):
        self.db.createhost("charis", "linux", "Jelmer", "jelmer@samba.org", "bla", "Pemrission?")
        hosts = list(self.db.hosts())
        self.assertEquals(1, len(hosts))
        self.assertEquals("charis", hosts[0].name)
