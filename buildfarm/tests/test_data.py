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
import time
import unittest

from buildfarm import data

from buildfarm.tests import BuildFarmTestCase


class NonexistantTests(unittest.TestCase):

    def test_nonexistant(self):
        self.assertRaises(
            Exception, data.BuildResultStore, "somedirthatdoesn'texist", None)


class BuildResultStoreTestBase(object):

    def test_build_fname(self):
        self.assertEquals(
            self.x.build_fname("mytree", "myhost", "cc", 123),
            "%s/data/oldrevs/build.mytree.myhost.cc-123" % self.path)

    def test_build_remove(self):
        path = self.create_mock_logfile("tdb", "charis", "cc", "12")
        build = self.x.get_build("tdb", "charis", "cc", "12")
        build.remove()
        self.assertFalse(os.path.exists(path))
        self.assertRaises(data.NoSuchBuildError, self.x.get_build, "tdb", "charis", "cc", "12")

    def test_build_repr(self):
        path = self.create_mock_logfile("tdb", "charis", "cc", "12")
        build = self.x.get_build("tdb", "charis", "cc", "12")
        self.assertEquals("<%s: revision 12 of tdb on charis using cc>" % build.__class__.__name__, repr(build))

    def test_get_build_nonexistant(self):
        self.assertRaises(data.NoSuchBuildError, self.x.get_build, "tdb",
            "charis", "cc", "12")

    def test_build_age_ctime(self):
        path = self.create_mock_logfile("tdb", "charis", "cc", "12")
        # Set mtime to something in the past
        build = self.x.get_build("tdb", "charis", "cc", "12")
        age = build.age
        self.assertTrue(age >= 0 and age <= 10, "age was %d" % age)

    def test_read_log(self):
        path = self.create_mock_logfile("tdb", "charis", "cc", "12",
            contents="This is what a log file looks like.")
        build = self.x.get_build("tdb", "charis", "cc", "12")
        self.assertEquals("This is what a log file looks like.", build.read_log().read())

    def test_read_err(self):
        self.create_mock_logfile("tdb", "charis", "cc", "12")
        path = self.create_mock_logfile("tdb", "charis", "cc", "12",
            kind="stderr",
            contents="This is what an stderr file looks like.")
        build = self.x.get_build("tdb", "charis", "cc", "12")
        self.assertEquals("This is what an stderr file looks like.", build.read_err().read())

    def test_read_err_nofile(self):
        self.create_mock_logfile("tdb", "charis", "cc", "12")
        build = self.x.get_build("tdb", "charis", "cc", "12")
        self.assertEquals("", build.read_err().read())

    def test_revision_details(self):
        self.create_mock_logfile("tdb", "charis", "cc", "12", contents="""
BUILD COMMIT REVISION: 43
bla
BUILD COMMIT TIME: 3 August 2010
""")
        build = self.x.get_build("tdb", "charis", "cc", "12")
        (rev, timestamp) = build.revision_details()
        self.assertIsInstance(rev, str)
        self.assertIsInstance(timestamp, str)
        self.assertEquals(("43", "3 August 2010"), (rev, timestamp))

    def test_revision_details_no_timestamp(self):
        self.create_mock_logfile("tdb", "charis", "cc", rev="12", contents="""
BUILD COMMIT REVISION: 43
BUILD REVISION: 42
BLA
""")
        build = self.x.get_build("tdb", "charis", "cc", "12")
        self.assertEquals(("43", None), build.revision_details())

    def test_err_count(self):
        self.create_mock_logfile("tdb", "charis", "cc", "12")
        self.create_mock_logfile("tdb", "charis", "cc", "12", kind="stderr", contents="""error1
error2
error3""")
        build = self.x.get_build("tdb", "charis", "cc", "12")
        self.assertEquals(3, build.err_count())

    def test_upload_build(self):
        path = self.create_mock_logfile("tdb", "charis", "cc", contents="""
BUILD COMMIT REVISION: myrev
""")
        build = data.Build(path[:-4], "tdb", "charis", "cc")
        self.x.upload_build(build)
        uploaded_build = self.x.get_build("tdb", "charis", "cc", "myrev")
        self.assertEquals(uploaded_build.log_checksum(), build.log_checksum())

    def test_upload_build_no_rev(self):
        path = self.create_mock_logfile("tdb", "charis", "cc", contents="""
""")
        build = data.Build(path[:-4], "tdb", "charis", "cc")
        self.assertRaises(Exception, self.x.upload_build, build)

    def test_get_previous_revision(self):
        self.assertRaises(data.NoSuchBuildError, self.x.get_previous_revision, "tdb", "charis", "cc", "12")

    def test_get_latest_revision_none(self):
        self.assertRaises(data.NoSuchBuildError, self.x.get_latest_revision, "tdb", "charis", "cc")

    def test_get_old_revs_none(self):
        self.assertEquals([],
            list(self.x.get_old_revs(u"tdb", u"charis", u"gcc")))

    def test_get_old_revs(self):
        path = self.create_mock_logfile("tdb", "charis", "cc",
            contents="""
BUILD COMMIT REVISION: 12
""")
        build = data.Build(path[:-4], "tdb", "charis", "cc")
        b1 = self.x.upload_build(build)
        path = self.create_mock_logfile("tdb", "charis", "cc",
            contents="""
BUILD COMMIT REVISION: 15
""")
        build = data.Build(path[:-4], "tdb", "charis", "cc")
        b2 = self.x.upload_build(build)
        path = self.create_mock_logfile("tdb", "charis", "cc",
            contents="""
BUILD COMMIT REVISION: 15
""")
        self.assertEquals([b1, b2],
            list(self.x.get_old_revs(u"tdb", u"charis", u"cc")))


class BuildResultStoreTests(BuildFarmTestCase,BuildResultStoreTestBase):

    def setUp(self):
        super(BuildResultStoreTests, self).setUp()

        self.x = data.BuildResultStore(
            os.path.join(self.path, "data", "oldrevs"))


class BuildStatusFromLogs(testtools.TestCase):

    def parse_logs(self, log, err):
        return data.build_status_from_logs(StringIO(log), StringIO(err))

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
        a = data.BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 2)])
        b = data.BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 2)])

        self.assertEquals(cmp(a, b), 0)

    def test_cmp_empty(self):
        self.assertEquals(cmp(data.BuildStatus(), data.BuildStatus()), 0)

    def test_cmp_other_failures(self):
        self.assertEquals(cmp(
            data.BuildStatus((), set(["foo"])), data.BuildStatus((), set(["foo"]))),
            0)

    def test_cmp_intermediate_errors(self):
        a = data.BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 3)])
        b = data.BuildStatus([("CONFIGURE", 2), ("TEST", 7), ("CC_CHECKER", 3)])
        self.assertEquals(cmp(a, b), 1)

    def test_cmp_bigger(self):
        a = data.BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 3)])
        b = data.BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 2)])
        c = data.BuildStatus([("CONFIGURE", 2), ("TEST", 3)])
        d = data.BuildStatus([], set(["super error"]))
        e = data.BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 1)], set(["super error"]))

        # less stage means smaller, more error/higher error code means smaller as well
        self.assertEquals(cmp(b, a), 1)

        self.assertEquals(cmp(a, c), 1)

        self.assertEquals(cmp(a, d), 1)

        self.assertEquals(cmp(b, e), 1)

    def test_cmp_smaller(self):
        a = data.BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 2)])
        b = data.BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 1)])
        c = data.BuildStatus([("CONFIGURE", 2), ("TEST", 3)])
        d = data.BuildStatus([], set(["super error"]))
        e = data.BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 1)], set(["super error"]))

        # less stage means smaller, more error/higher error code means smaller as well
        self.assertEquals(cmp(a, b), -1)

        self.assertEquals(cmp(c, b), -1)

        self.assertEquals(cmp(d, c), -1)

        self.assertEquals(cmp(e, c), -1)

    def test_cmp_with_other_failures(self):
        d = data.BuildStatus([], set(["super error"]))
        e = data.BuildStatus([("CONFIGURE", 2), ("TEST", 3), ("CC_CHECKER", 1)], set(["super error"]))
        self.assertEquals(cmp(d, e), -1)

    def test_str(self):
        a = data.BuildStatus([("CONFIGURE", 3), ("BUILD", 2)])
        self.assertEquals("3/2", str(a))

    def test_str_other_failures(self):
        a = data.BuildStatus([("CONFIGURE", 3), ("BUILD", 2)], set(["panic"]))
        self.assertEquals("panic", str(a))


class BuildStatusRegressedSinceTests(testtools.TestCase):

    def assertRegressedSince(self, expected, old_status, new_status):
        (stages1, other_failures1) = old_status
        (stages2, other_failures2) = new_status
        a = data.BuildStatus(stages1, set(other_failures1))
        b = data.BuildStatus(stages2, set(other_failures2))
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


class UploadBuildResultStoreTestBase(object):

    def test_build_fname(self):
        self.assertEquals(
            self.x.build_fname("mytree", "myhost", "cc"),
            "%s/data/upload/build.mytree.myhost.cc" % self.path)

    def test_get_new_builds(self):
        self.assertEquals([], list(self.x.get_new_builds()))
        path = self.create_mock_logfile("tdb", "charis", "cc")
        new_builds = list(self.x.get_new_builds())
        self.assertEquals(1, len(new_builds))
        self.assertEquals("tdb", new_builds[0].tree)
        self.assertEquals("charis", new_builds[0].host)
        self.assertEquals("cc", new_builds[0].compiler)


class UploadBuildResultStoreTests(UploadBuildResultStoreTestBase,BuildFarmTestCase):

    def setUp(self):
        super(UploadBuildResultStoreTests, self).setUp()

        self.x = data.UploadBuildResultStore(
            os.path.join(self.path, "data", "upload"))



