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

from cStringIO import StringIO
import os
import testtools
import unittest

from buildfarm.build import (
    Build,
    BuildResultStore,
    BuildStatus,
    NoSuchBuildError,
    UploadBuildResultStore,
    build_status_from_logs,
    )

from buildfarm import BuildFarm
from buildfarm.tests import BuildFarmTestCase


class BuildResultStoreTests(BuildFarmTestCase):

    def setUp(self):
        super(BuildResultStoreTests, self).setUp()
        self.buildfarm = BuildFarm(self.path)
        self.write_compilers(["cc", "gcc"])
        self.write_hosts({"charis": "Some machine",
                          "myhost": "Another host"})
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

    def test_build_fname(self):
        self.assertEquals(
            self.x.build_fname("mytree", "myhost", "cc", 123),
            "%s/data/oldrevs/build.mytree.myhost.cc-123" % self.path)

    def test_build_remove(self):
        path = self.upload_mock_logfile(self.x, "tdb", "charis", "cc", 
                "BUILD COMMIT REVISION: 12\n")
        build = self.x.get_build("tdb", "charis", "cc", "12")
        logname = build.basename + ".log"
        build.remove()
        self.assertFalse(os.path.exists(logname))
        self.assertRaises(NoSuchBuildError, self.x.get_build, "tdb", "charis", "cc", "12")

    def test_build_repr(self):
        path = self.upload_mock_logfile(self.x, "tdb", "charis", "cc", 
            "BUILD COMMIT REVISION: 12\n")
        build = self.x.get_build("tdb", "charis", "cc", "12")
        self.assertEquals("<%s: revision 12 of tdb on charis using cc>" % build.__class__.__name__, repr(build))

    def test_get_build_nonexistant(self):
        self.assertRaises(NoSuchBuildError, self.x.get_build, "tdb",
            "charis", "cc", "12")

    def test_build_upload_time(self):
        path = self.upload_mock_logfile(self.x, "tdb", "charis", "cc", 
                "BUILD COMMIT REVISION: 12\n", mtime=5)
        build = self.x.get_build("tdb", "charis", "cc", "12")
        self.assertEquals(5, build.upload_time)

    def test_read_log(self):
        path = self.upload_mock_logfile(self.x, "tdb", "charis", "cc", 
            stdout_contents="This is what a log file looks like.\n"
            "BUILD COMMIT REVISION: 12\n")
        build = self.x.get_build("tdb", "charis", "cc", "12")
        self.assertEquals("This is what a log file looks like.\n"
                          "BUILD COMMIT REVISION: 12\n",
                          build.read_log().read())

    def test_read_err(self):
        self.upload_mock_logfile(self.x, "tdb", "charis", "cc",
            stdout_contents="BUILD COMMIT REVISION: 12\n",
            stderr_contents="This is what an stderr file looks like.")
        build = self.x.get_build("tdb", "charis", "cc", "12")
        self.assertEquals("This is what an stderr file looks like.",
                build.read_err().read())

    def test_read_err_nofile(self):
        self.upload_mock_logfile(self.x, "tdb", "charis", "cc",
                stdout_contents="BUILD COMMIT REVISION: 12\n")
        build = self.x.get_build("tdb", "charis", "cc", "12")
        self.assertEquals("", build.read_err().read())

    def test_revision_details(self):
        self.upload_mock_logfile(self.x, "tdb", "charis", "cc", stdout_contents="""
BUILD COMMIT REVISION: 43
bla
BUILD COMMIT TIME: 3 August 2010
""")
        build = self.x.get_build("tdb", "charis", "cc", "43")
        rev = build.revision_details()
        self.assertIsInstance(rev, str)
        self.assertEquals("43", rev)

    def test_revision_details_no_timestamp(self):
        self.upload_mock_logfile(self.x, "tdb", "charis", "cc", stdout_contents="""
BUILD COMMIT REVISION: 43
BUILD REVISION: 42
BLA
""")
        build = self.x.get_build("tdb", "charis", "cc", "43")
        self.assertEquals("43", build.revision_details())

    def test_err_count(self):
        self.upload_mock_logfile(self.x, "tdb", "charis", "cc",
            stdout_contents="BUILD COMMIT REVISION: 12\n",
            stderr_contents="""error1
error2
error3""")
        build = self.x.get_build("tdb", "charis", "cc", "12")
        self.assertEquals(3, build.err_count())

    def test_upload_build(self):
        path = self.create_mock_logfile("tdb", "charis", "cc", contents="""
BUILD COMMIT REVISION: myrev
""")
        build = Build(path[:-4], "tdb", "charis", "cc")
        self.x.upload_build(build)
        uploaded_build = self.x.get_build("tdb", "charis", "cc", "myrev")
        self.assertEquals(uploaded_build.log_checksum(), build.log_checksum())

    def test_upload_build_no_rev(self):
        path = self.create_mock_logfile("tdb", "charis", "cc", contents="""
""")
        build = Build(path[:-4], "tdb", "charis", "cc")
        self.assertRaises(Exception, self.x.upload_build, build)

    def test_get_previous_revision(self):
        self.assertRaises(NoSuchBuildError, self.x.get_previous_revision, "tdb", "charis", "cc", "12")

    def test_get_latest_revision_none(self):
        self.assertRaises(NoSuchBuildError, self.x.get_latest_revision, "tdb", "charis", "cc")

    def test_get_old_builds_none(self):
        self.assertEquals([],
            list(self.x.get_old_builds("tdb", "charis", "gcc")))

    def test_get_old_builds(self):
        path = self.create_mock_logfile("tdb", "charis", "cc",
            contents="""
BUILD COMMIT REVISION: 12
""")
        build = Build(path[:-4], "tdb", "charis", "cc")
        b1 = self.x.upload_build(build)
        path = self.create_mock_logfile("tdb", "charis", "cc",
            contents="""
BUILD COMMIT REVISION: 15
""")
        build = Build(path[:-4], "tdb", "charis", "cc")
        b2 = self.x.upload_build(build)
        path = self.create_mock_logfile("tdb", "charis", "cc",
            contents="""
BUILD COMMIT REVISION: 15
""")
        self.assertEquals([b1, b2],
            list(self.x.get_old_builds("tdb", "charis", "cc")))


class BuildStatusFromLogs(testtools.TestCase):

    def parse_logs(self, log, err):
        return build_status_from_logs(StringIO(log), StringIO(err))

    def test_nothing(self):
        s = self.parse_logs("", "")
        self.assertEquals([], s.stages)
        self.assertEquals(set(), s.other_failures)

    def test_disk_full(self):
        self.assertEquals(set(["disk full"]),
            self.parse_logs("foo\nbar\nNo space left on device\nla\n",
                "").other_failures)
        self.assertEquals(set(["disk full"]),
            self.parse_logs(
                "", "foo\nbar\nNo space left on device\nla\n").other_failures)

    def test_timeout(self):
        self.assertEquals(set(["timeout"]),
            self.parse_logs("foo\nbar\nmaximum runtime exceeded\nla\n",
                "").other_failures)

    def test_failed_test(self):
        log = """
TEST STATUS:1
"""
        res = self.parse_logs(log, "")
        self.assertEquals(res.stages, [
            ("TEST", 1)])

    def test_failed_test_whitespace(self):
        log = """
TEST STATUS:  1
"""
        res = self.parse_logs(log, "")
        self.assertEquals(res.stages,
            [("TEST", 1)])

    def test_failed_test_noise(self):
        log = """
CONFIGURE STATUS: 2
TEST STATUS:  1
CC_CHECKER STATUS:	2
"""
        res = self.parse_logs(log, "")
        self.assertEquals(res.stages,
            [("CONFIGURE", 2), ("TEST", 1), ("CC_CHECKER", 2)])

    def test_no_test_output(self):
        log = """
CONFIGURE STATUS: 2
TEST STATUS: 0
CC_CHECKER STATUS:	2
"""
        res = self.parse_logs(log, "")
        self.assertEquals(res.stages,
            [("CONFIGURE", 2), ("TEST", 0), ("CC_CHECKER", 2)])

    def test_granular_test(self):
        log = """
CONFIGURE STATUS: 2
testsuite-success: toto
testsuite-failure: foo
testsuite-failure: bar
testsuite-failure: biz
TEST STATUS: 1
CC_CHECKER STATUS:	2
"""
        res = self.parse_logs(log, "")
        self.assertEquals(res.stages,
            [("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 2)])


class BuildStatusTest(testtools.TestCase):

    def test_cmp_equal(self):
        a = BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 2)])
        b = BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 2)])

        self.assertEquals(cmp(a, b), 0)

    def test_cmp_empty(self):
        self.assertEquals(cmp(BuildStatus(), BuildStatus()), 0)

    def test_cmp_other_failures(self):
        self.assertEquals(cmp(
            BuildStatus((), set(["foo"])), BuildStatus((), set(["foo"]))),
            0)

    def test_cmp_intermediate_errors(self):
        a = BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 3)])
        b = BuildStatus([("CONFIGURE", 2), ("TEST", 7), ("CC_CHECKER", 3)])
        self.assertEquals(cmp(a, b), 1)

    def test_cmp_bigger(self):
        a = BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 3)])
        b = BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 2)])
        c = BuildStatus([("CONFIGURE", 2), ("TEST", 3)])
        d = BuildStatus([], set(["super error"]))
        e = BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 1)], set(["super error"]))

        # less stage means smaller, more error/higher error code means smaller as well
        self.assertEquals(cmp(b, a), 1)

        self.assertEquals(cmp(a, c), 1)

        self.assertEquals(cmp(a, d), 1)

        self.assertEquals(cmp(b, e), 1)

    def test_cmp_smaller(self):
        a = BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 2)])
        b = BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 1)])
        c = BuildStatus([("CONFIGURE", 2), ("TEST", 3)])
        d = BuildStatus([], set(["super error"]))
        e = BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 1)], set(["super error"]))

        # less stage means smaller, more error/higher error code means smaller as well
        self.assertEquals(cmp(a, b), -1)

        self.assertEquals(cmp(c, b), -1)

        self.assertEquals(cmp(d, c), -1)

        self.assertEquals(cmp(e, c), -1)

    def test_cmp_with_other_failures(self):
        d = BuildStatus([], set(["super error"]))
        e = BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 1)], set(["super error"]))
        self.assertEquals(cmp(d, e), -1)

    def test_str(self):
        a = BuildStatus([("CONFIGURE", 3), ("BUILD", 2)])
        self.assertEquals("3/2", str(a))

    def test_str_other_failures(self):
        a = BuildStatus([("CONFIGURE", 3), ("BUILD", 2)], set(["panic"]))
        self.assertEquals("panic", str(a))


class BuildStatusRegressedSinceTests(testtools.TestCase):

    def assertRegressedSince(self, expected, old_status, new_status):
        (stages1, other_failures1) = old_status
        (stages2, other_failures2) = new_status
        a = BuildStatus(stages1, set(other_failures1))
        b = BuildStatus(stages2, set(other_failures2))
        self.assertEquals(expected, b.regressed_since(a))

    def test_same(self):
        self.assertRegressedSince(
            False,
            ([("CONFIGURE", 2)], []),
            ([("CONFIGURE", 2)], []))

    def test_same_panic(self):
        self.assertRegressedSince(
            False,
            ([("CONFIGURE", 2)], ["panic"]),
            ([("CONFIGURE", 2)], ["panic"]))

    def test_other_failures_gone(self):
        self.assertRegressedSince(
            True,
            ([("CONFIGURE", 0)], ["panic"]),
            ([("CONFIGURE", 2)], ["panic"]))

    def test_more_stages_completed(self):
        self.assertRegressedSince(
            False,
            ([("CONFIGURE", 0)], []),
            ([("CONFIGURE", 0), ("BUILD", 0)], []))

    def test_less_errors(self):
        self.assertRegressedSince(
            False,
            ([("CONFIGURE", 0), ("BUILD", 0), ("TEST", 0), ("INSTALL", 1)], []),
            ([("CONFIGURE", 0), ("BUILD", 0), ("TEST", 0), ("INSTALL", 0)], []))

    def test_no_longer_inconsistent(self):
        self.assertRegressedSince(
            False,
            ([("CONFIGURE", 0)], ["inconsistent test result"]),
            ([("CONFIGURE", 0)], []))


class UploadBuildResultStoreTestBase(object):

    def test_build_fname(self):
        self.assertEquals(
            self.x.build_fname("mytree", "myhost", "cc"),
            "%s/data/upload/build.mytree.myhost.cc" % self.path)

    def test_get_all_builds(self):
        self.assertEquals([], list(self.x.get_all_builds()))
        path = self.create_mock_logfile("tdb", "charis", "cc")
        new_builds = list(self.x.get_all_builds())
        self.assertEquals(1, len(new_builds))
        self.assertEquals("tdb", new_builds[0].tree)
        self.assertEquals("charis", new_builds[0].host)
        self.assertEquals("cc", new_builds[0].compiler)


class UploadBuildResultStoreTests(UploadBuildResultStoreTestBase,BuildFarmTestCase):

    def setUp(self):
        super(UploadBuildResultStoreTests, self).setUp()

        self.x = UploadBuildResultStore(
            os.path.join(self.path, "data", "upload"))
