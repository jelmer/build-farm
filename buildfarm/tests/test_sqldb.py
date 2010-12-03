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

from buildfarm.build import (
    Build,
    NoSuchBuildError,
    )
from buildfarm.tests import BuildFarmTestCase
from buildfarm.tests.test_buildfarm import BuildFarmTestBase
from buildfarm.tests.test_build import BuildResultStoreTestBase
from buildfarm.tests.test_hostdb import HostDatabaseTests
from buildfarm.sqldb import (
    StormHostDatabase,
    StormCachingBuildFarm,
    )

import testtools


class StormCachingBuildFarmTestCase(BuildFarmTestCase):

    def setUp(self):
        super(StormCachingBuildFarmTestCase, self).setUp()
        self.buildfarm = StormCachingBuildFarm(self.path)

    def write_hosts(self, hosts):
        for host in hosts:
            self.buildfarm.hostdb.createhost(host)


class StormHostDatabaseTests(testtools.TestCase, HostDatabaseTests):

    def setUp(self):
        super(StormHostDatabaseTests, self).setUp()
        self.db = StormHostDatabase()


class StormCachingBuildResultStoreTests(StormCachingBuildFarmTestCase,BuildResultStoreTestBase):

    def setUp(self):
        StormCachingBuildFarmTestCase.setUp(self)
        BuildResultStoreTestBase.setUp(self)
        self.x = self.buildfarm.builds

    def test_get_previous_revision_result(self):
        path = self.create_mock_logfile("tdb", "charis", "cc", contents="""
BUILD COMMIT REVISION: myrev
""")
        self.x.upload_build(Build(path[:-4], "tdb", "charis", "cc"))
        path = self.create_mock_logfile("tdb", "charis", "cc", contents="""
BUILD COMMIT REVISION: myotherrev
""")
        self.x.upload_build(Build(path[:-4], "tdb", "charis", "cc"))
        self.assertRaises(NoSuchBuildError, self.x.get_previous_revision, "tdb", "charis", "cc", "unknown")
        self.assertRaises(NoSuchBuildError, self.x.get_previous_revision, "tdb", "charis", "cc", "myrev")
        self.assertEquals("myrev", self.x.get_previous_revision("tdb", "charis", "cc", "myotherrev"))

    def test_get_latest_revision(self):
        path = self.create_mock_logfile("tdb", "charis", "cc", "22", contents="""
BUILD COMMIT REVISION: myrev
""")
        self.x.upload_build(Build(path[:-4], "tdb", "charis", "cc"))
        self.assertEquals("myrev", self.x.get_latest_revision("tdb", "charis", "cc"))



class StormCachingBuildFarmTests(BuildFarmTestBase, StormCachingBuildFarmTestCase):

    def setUp(self):
        StormCachingBuildFarmTestCase.setUp(self)
        BuildFarmTestBase.setUp(self)
        self.x = self.buildfarm
