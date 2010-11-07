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
import time
import unittest

from buildfarm import data

from buildfarm.tests import BuildFarmTestCase


class NonexistantTests(unittest.TestCase):

    def test_nonexistant(self):
        self.assertRaises(
            Exception, data.BuildResultStore, "somedirthatdoesn'texist", None)


class ReadTreesFromConfTests(testtools.TestCase):

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
            Exception, data.read_trees_from_conf, name, None)

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
        t = data.read_trees_from_conf(name)
        self.assertEquals(
            t["pidl"].scm,
            "git")


class BuildResultStoreTests(BuildFarmTestCase):

    def setUp(self):
        super(BuildResultStoreTests, self).setUp()

        self.write_compilers(["cc"])
        self.write_trees({"tdb": {"scm": "git", "repo": "tdb", "branch": "master"}})

        self.x = data.BuildResultStore(self.path)

    def test_build_fname(self):
        self.assertEquals(
            self.x.build_fname("mytree", "myhost", "cc"),
            "%s/data/upload/build.mytree.myhost.cc" % self.path)
        self.assertEquals(
            self.x.build_fname("mytree", "myhost", "cc", 123),
            "%s/data/oldrevs/build.mytree.myhost.cc-123" % self.path)

    def test_cache_fname(self):
        self.assertEquals(
            self.x.cache_fname("mytree", "myhost", "cc", 123),
            "%s/cache/build.mytree.myhost.cc-123" % self.path)
        self.assertEquals(
            self.x.cache_fname("mytree", "myhost", "cc"),
            "%s/cache/build.mytree.myhost.cc" % self.path)

    def test_build_age_mtime(self):
        path = self.create_mock_logfile("tdb", "charis", "cc")
        # Set mtime to something in the past
        os.utime(path, (time.time(), time.time() - 990))
        build = self.x.get_build("tdb", "charis", "cc")
        age = build.age_mtime()
        self.assertTrue(age >= 990 and age <= 1000, "age was %d" % age)

    def test_get_build_nonexistant(self):
        self.assertRaises(data.NoSuchBuildError, self.x.get_build, "tdb",
            "charis", "cc")

    def test_build_age_ctime(self):
        path = self.create_mock_logfile("tdb", "charis", "cc")
        # Set mtime to something in the past
        build = self.x.get_build("tdb", "charis", "cc")
        age = build.age_ctime()
        self.assertTrue(age >= 0 and age <= 10, "age was %d" % age)

    def test_read_log(self):
        path = self.create_mock_logfile("tdb", "charis", "cc",
            contents="This is what a log file looks like.")
        build = self.x.get_build("tdb", "charis", "cc")
        self.assertEquals("This is what a log file looks like.", build.read_log().read())

    def test_read_err(self):
        self.create_mock_logfile("tdb", "charis", "cc")
        path = self.create_mock_logfile("tdb", "charis", "cc",
            kind="stderr",
            contents="This is what an stderr file looks like.")
        build = self.x.get_build("tdb", "charis", "cc")
        self.assertEquals("This is what an stderr file looks like.", build.read_err().read())

    def test_revision_details(self):
        self.create_mock_logfile("tdb", "charis", "cc", contents="""
BUILD COMMIT REVISION: 43
bla
BUILD REVISION: 42
BUILD COMMIT TIME: 3 August 2010
""")
        build = self.x.get_build("tdb", "charis", "cc")
        self.assertEquals(("43", "3 August 2010"), build.revision_details())

    def test_revision_details_no_timestamp(self):
        self.create_mock_logfile("tdb", "charis", "cc", contents="""
BUILD COMMIT REVISION: 43
BUILD REVISION: 42
BLA
""")
        build = self.x.get_build("tdb", "charis", "cc")
        self.assertEquals(("43", None), build.revision_details())

    def test_err_count(self):
        self.create_mock_logfile("tdb", "charis", "cc")
        self.create_mock_logfile("tdb", "charis", "cc", kind="stderr", contents="""error1
error2
error3""")
        build = self.x.get_build("tdb", "charis", "cc")
        self.assertEquals(3, build.err_count())

    def test_has_host(self):
        self.assertFalse(self.x.has_host("charis"))
        self.create_mock_logfile("tdb", "charis", "cc")
        self.assertTrue(self.x.has_host("charis"))


class BuildStatusFromLogs(testtools.TestCase):

    def test_nothing(self):
        s = data.build_status_from_logs("", "")
        self.assertEquals((None, None, None, None), s.stages)
        self.assertEquals(set(), s.other_failures)

    def test_disk_full(self):
        self.assertEquals(set(["disk full"]),
            data.build_status_from_logs("foo\nbar\nNo space left on device\nla\n",
                "").other_failures)
        self.assertEquals(set(["disk full"]),
            data.build_status_from_logs(
                "", "foo\nbar\nNo space left on device\nla\n").other_failures)

    def test_timeout(self):
        self.assertEquals(set(["timeout"]),
            data.build_status_from_logs("foo\nbar\nmaximum runtime exceeded\nla\n",
                "").other_failures)

    def test_status(self):
        log = """
TEST STATUS:1
"""
        res = data.build_status_from_logs(log, "")
        self.assertEquals(res.stages[3], 1)
        log = """
TEST STATUS:  1
"""
        res = data.build_status_from_logs(log, "")
        self.assertEquals(res.stages[3], 1)
        log = """
CONFIGURE STATUS: 2
TEST STATUS:  1
CC_CHECKER STATUS:	2
"""
        res = data.build_status_from_logs(log, "")
        self.assertEquals(res.stages[4], 2)
        log = """
CONFIGURE STATUS: 2
ACTION PASSED: test
CC_CHECKER STATUS:	2
"""
        res = data.build_status_from_logs(log, "")
        self.assertEquals(res.stages[4], 2)
        self.assertEquals(res.stages[3], 255)
        log = """
CONFIGURE STATUS: 2
ACTION PASSED: test
testsuite-success: toto
testsuite-failure: foo
testsuite-failure: bar
testsuite-failure: biz
CC_CHECKER STATUS:	2
"""
        res = data.build_status_from_logs(log, "")
        self.assertEquals(res.stages[0], 2)
        self.assertEquals(res.stages[3], 3)


