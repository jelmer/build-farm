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

from buildfarm.tests import BuildFarmTestCase
from buildfarm.tests.test_buildfarm import BuildFarmTestBase
from buildfarm.filecache import (
    CachingBuildFarm,
    CachingBuildResultStore,
    CachingUploadBuildResultStore,
    )
from buildfarm.tests.test_data import (
    BuildResultStoreTestBase,
    UploadBuildResultStoreTestBase,
    )
import os


class CachingBuildFarmTests(BuildFarmTestBase, BuildFarmTestCase):

    def setUp(self):
        BuildFarmTestCase.setUp(self)
        BuildFarmTestBase.setUp(self)
        self.x = CachingBuildFarm(self.path)


class CachingUploadBuildResultStoreTests(UploadBuildResultStoreTestBase,BuildFarmTestCase):

    def setUp(self):
        super(CachingUploadBuildResultStoreTests, self).setUp()

        self.x = CachingUploadBuildResultStore(
            os.path.join(self.path, "data", "upload"),
            os.path.join(self.path, "cache"))

    def test_cache_fname(self):
        self.assertEquals(
            self.x.cache_fname("mytree", "myhost", "cc"),
            "%s/cache/build.mytree.myhost.cc" % self.path)


class CachingBuildResultStoreTests(BuildFarmTestCase,BuildResultStoreTestBase):

    def setUp(self):
        super(CachingBuildResultStoreTests, self).setUp()

        self.x = CachingBuildResultStore(
            os.path.join(self.path, "data", "oldrevs"),
            os.path.join(self.path, "cache"))

    def test_cache_fname(self):
        self.assertEquals(
            self.x.cache_fname("mytree", "myhost", "cc", 123),
            "%s/cache/build.mytree.myhost.cc-123" % self.path)



