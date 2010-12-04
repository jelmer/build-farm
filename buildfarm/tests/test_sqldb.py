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

from buildfarm import BuildFarm
from buildfarm.build import (
    Build,
    NoSuchBuildError,
    )
from buildfarm.tests import BuildFarmTestCase
from buildfarm.tests.test_hostdb import HostDatabaseTests
from buildfarm.sqldb import (
    StormHostDatabase,
    )

import testtools


class StormHostDatabaseTests(testtools.TestCase, HostDatabaseTests):

    def setUp(self):
        super(StormHostDatabaseTests, self).setUp()
        self.db = StormHostDatabase()



