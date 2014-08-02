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

from buildfarm import (
    BuildFarm,
    read_trees_from_conf,
    )
from buildfarm.build import NoSuchBuildError
from buildfarm.tests import BuildFarmTestCase

import os
from testtools import TestCase
import tempfile


class ReadTreesFromConfTests(TestCase):

    def create_file(self, contents):
        (fd, path) = tempfile.mkstemp()
        f = os.fdopen(fd, 'w')
        self.addCleanup(os.remove, path)
        try:
            f.write(contents)
        finally:
            f.close()
        return path

    def test_read_trees_from_conf_ko(self):
        name = self.create_file("""
[foo]
param1 = fooval1
param2 = fooval2
param3 = fooval3

[bar]
param1 = barval1
param2 = barval2
param3 = barval3
""")
        self.assertRaises(
            Exception, read_trees_from_conf, name, None)

    def test_read_trees_from_conf(self):
        name = self.create_file("""
[pidl]
scm = git
repo = samba.git
branch = master
subdir = pidl/

[rsync]
scm = git
repo = rsync.git
branch = HEAD
""")
        t = read_trees_from_conf(name)
        self.assertEquals(t["pidl"].scm, "git")


class BuildFarmTests(BuildFarmTestCase):

    def setUp(self):
        super(BuildFarmTests, self).setUp()
        self.buildfarm = BuildFarm(self.path)
        self.write_compilers(["cc"])
        self.write_hosts({"myhost": "Fedora",
                          "charis": "Debian"})
        self.write_trees({"trivial": {"scm": "git", "repo": "git://foo", "branch": "master"},
                          "other": {"scm": "git", "repo": "other.git", "branch": "HEAD"}})
        self.buildfarm.commit()
        self.x = BuildFarm(self.path)

    def test_get_new_builds_empty(self):
        self.assertEquals([], list(self.x.get_new_builds()))

    def test_get_last_builds_empty(self):
        self.assertEquals([], list(self.x.get_last_builds()))

    def test_get_tree_builds_empty(self):
        self.assertEquals([], list(self.x.get_tree_builds("trival")))

    def test_get_tree_builds(self):
        path = self.upload_mock_logfile(self.x.builds, "tdb", "myhost", "gcc",
            stdout_contents="BUILD COMMIT REVISION: 12\n", mtime=1200)
        path = self.upload_mock_logfile(self.x.builds, "tdb", "myhost", "cc",
            stdout_contents="BUILD COMMIT REVISION: 13\n", mtime=1300)
        path = self.upload_mock_logfile(self.x.builds, "tdb", "myhost", "cc",
            stdout_contents="BUILD COMMIT REVISION: 42\n", mtime=4200)
        builds = list(self.x.get_tree_builds("tdb"))
        self.assertEquals(["42", "12"], [x.revision for x in builds])

    def test_get_last_builds(self):
        path = self.upload_mock_logfile(self.x.builds, "other", "myhost", "cc",
            "BUILD COMMIT REVISION: 12\n", mtime=1200)
        path = self.upload_mock_logfile(self.x.builds, "trivial", "myhost", "cc",
            "BUILD COMMIT REVISION: 13\n", mtime=1300)
        path = self.upload_mock_logfile(self.x.builds, "trivial", "myhost", "cc",
            "BUILD COMMIT REVISION: 42\n", mtime=4200)
        builds = list(self.x.get_last_builds())
        self.assertEquals(2, len(builds))
        self.assertEquals(4200, builds[0].upload_time)
        self.assertEquals("42", builds[0].revision_details())
        self.assertEquals("trivial", builds[0].tree)
        self.assertEquals(1200, builds[1].upload_time)
        self.assertEquals("12", builds[1].revision_details())
        self.assertEquals("other", builds[1].tree)

    def test_get_summary_builds_empty(self):
        self.assertEquals([], list(self.x.get_summary_builds()))

    def test_get_summary_builds(self):
        path = self.upload_mock_logfile(self.x.builds, "other", "myhost", "cc",
            "BUILD COMMIT REVISION: 12\n", mtime=1200)
        path = self.upload_mock_logfile(self.x.builds, "trivial", "myhost", "cc",
            "BUILD COMMIT REVISION: 13\n", mtime=1300)
        path = self.upload_mock_logfile(self.x.builds, "trivial", "myhost", "cc",
            "BUILD COMMIT REVISION: 42\n", mtime=4200)
        builds = list(self.x.get_summary_builds())
        self.assertEquals(2, len(builds))
        self.assertEquals(4200, builds[0].upload_time)
        self.assertEquals("42", builds[0].revision_details())
        self.assertEquals("trivial", builds[0].tree)
        self.assertEquals(1200, builds[1].upload_time)
        self.assertEquals("12", builds[1].revision_details())
        self.assertEquals("other", builds[1].tree)

    def test_get_host_builds_empty(self):
        self.assertEquals([], list(self.x.get_host_builds("myhost")))

    def test_lcov_status_none(self):
        self.assertRaises(NoSuchBuildError, self.x.lcov_status, "trivial")

    def test_tree(self):
        self.assertEquals("trivial", self.x.trees["trivial"].name)
        tree = self.x.trees["trivial"]
        self.assertEquals("git", tree.scm)
        self.assertEquals("git://foo", tree.repo)
        self.assertEquals("master", tree.branch)

    def test_get_build_rev(self):
        path = self.upload_mock_logfile(self.x.builds, "tdb", "charis", "cc",
            stdout_contents="tHIS is what a log file looks like.\n"
            "BUILD COMMIT REVISION: 12\n")
        build = self.x.get_build("tdb", "charis", "cc", "12")
        self.assertEquals("tdb", build.tree)
        self.assertEquals("charis", build.host)
        self.assertEquals("cc", build.compiler)
        self.assertEquals("12", build.revision)

    def test_get_build_no_rev(self):
        path = self.create_mock_logfile("tdb", "charis", "cc",
            contents="This is what a log file looks like.")
        build = self.x.get_build("tdb", "charis", "cc")
        self.assertEquals("tdb", build.tree)
        self.assertEquals("charis", build.host)
        self.assertEquals("cc", build.compiler)
        self.assertIs(None, build.revision)

