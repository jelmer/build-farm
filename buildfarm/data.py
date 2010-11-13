#!/usr/bin/python
# Simple database query script for the buildfarm
#
# Copyright (C) Andrew Tridgell <tridge@samba.org>     2001-2005
# Copyright (C) Andrew Bartlett <abartlet@samba.org>   2001
# Copyright (C) Vance Lankhaar  <vance@samba.org>      2002-2005
# Copyright (C) Martin Pool <mbp@samba.org>            2001
# Copyright (C) Jelmer Vernooij <jelmer@samba.org>	   2007-2010
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
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
import collections
import hashlib
import os
import re
import time


class BuildSummary(object):

    def __init__(self, host, tree, compiler, revision, status):
        self.host = host
        self.tree = tree
        self.compiler = compiler
        self.revision = revision
        self.status = status


BuildStageResult = collections.namedtuple("BuildStageResult", "name result")


class BuildStatus(object):

    def __init__(self, stages=None, other_failures=None):
        if stages is not None:
            self.stages = stages
        else:
            self.stages = []
        if other_failures is not None:
            self.other_failures = other_failures
        else:
            self.other_failures = set()

    def __str__(self):
        if self.other_failures:
            return ",".join(self.other_failures)
        return "/".join(map(str, self._status_tuple()))

    def broken_host(self):
        if "disk full" in self.other_failures:
            return True
        return False

    def _status_tuple(self):
        return [sr.result for sr in self.stages]

    def regressed_since(self, other):
        """Check if this build has regressed since another build."""
        if "disk full" in self.other_failures:
            return False
        if "timeout" in self.other_failures and "timeout" in other.other_failures:
            # When the timeout happens exactly can differ slightly, so it's okay
            # if the numbers are a bit different..
            return False
        if "panic" in self.other_failures and not "panic" in other.other_failures:
            return True
        return cmp(self._status_tuple(), other._status_tuple())

    def __cmp__(self, other):
        other_extra = other.other_failures - self.other_failures
        self_extra = self.other_failures - other.other_failures
        # Give more importance to other failures
        if other_extra:
            return 1
        if self_extra:
            return -1

        la = len(self.stages)
        lb = len(other.stages)
        if la > lb:
            return 1
        elif lb > la:
            return -1
        else:
            return cmp(other.stages, self.stages)

    def __repr__(self):
        return "%s(%r, %r)" % (self.__class__.__name__, self.stages, self.other_failures)


def check_dir_exists(kind, path):
    if not os.path.isdir(path):
        raise Exception("%s directory %s does not exist" % (kind, path))


def build_status_from_logs(log, err):
    """get status of build"""
    test_failures = 0
    test_successes = 0
    test_seen = 0
    ret = BuildStatus()

    stages = []
    re_status = re.compile("^([A-Z_]+) STATUS:(\s*\d+)$")
    re_action = re.compile("^ACTION (PASSED|FAILED):\s+test$")

    for l in log:
        if l.startswith("No space left on device"):
            ret.other_failures.add("disk full")
            continue
        if l.startswith("maximum runtime exceeded"):
            ret.other_failures.add("timeout")
            continue
        if l.startswith("PANIC:") or l.startswith("INTERNAL ERROR:"):
            ret.other_failures.add("panic")
            continue
        if l.startswith("testsuite-failure: ") or l.startswith("testsuite-error: "):
            test_failures += 1
            continue
        if l.startswith("testsuite-success: "):
            test_successes += 1
            continue
        m = re_status.match(l)
        if m:
            stages.append(BuildStageResult(m.group(1), int(m.group(2).strip())))
            if m.group(1) == "TEST":
                test_seen = 1
            continue
        m = re_action.match(l)
        if m and not test_seen:
            if m.group(1) == "PASSED":
                stages.append(BuildStageResult("TEST", 0))
            else:
                stages.append(BuildStageResult("TEST", 1))
            continue

    # Scan err file for specific errors
    for l in err:
        if "No space left on device" in l:
            ret.other_failures.add("disk full")

    def map_stage(sr):
        if sr.name != "TEST":
            return sr
        # TEST is special
        if test_successes + test_failures == 0:
            # No granular test output
            return BuildStageResult("TEST", sr.result)
        if sr.result == 1 and test_failures == 0:
            ret.other_failures.add("inconsistent test result")
            return BuildStageResult("TEST", -1)
        return BuildStageResult("TEST", test_failures)

    ret.stages = map(map_stage, stages)
    return ret


class NoSuchBuildError(Exception):
    """The build with the specified name does not exist."""

    def __init__(self, tree, host, compiler, rev=None):
        self.tree = tree
        self.host = host
        self.compiler = compiler
        self.rev = rev


class Build(object):
    """A single build of a tree on a particular host using a particular compiler.
    """

    def __init__(self, basename, tree, host, compiler, rev=None):
        self.basename = basename
        self.tree = tree
        self.host = host
        self.compiler = compiler
        self.commit_revision = self.revision = rev

    def __repr__(self):
        if self.revision is not None:
            return "<%s: revision %s of %s on %s using %s>" % (self.__class__.__name__, self.revision, self.tree, self.host, self.compiler)
        else:
            return "<%s: %s on %s using %s>" % (self.__class__.__name__, self.tree, self.host, self.compiler)

    def remove_logs(self):
        os.unlink(self.basename + ".log")
        if os.path.exists(self.basename+".err"):
            os.unlink(self.basename+".err")

    def remove(self):
        self.remove_logs()

    ###################
    # the mtime age is used to determine if builds are still happening
    # on a host.
    # the ctime age is used to determine when the last real build happened

    def age_mtime(self):
        """get the age of build from mtime"""
        st = os.stat("%s.log" % self.basename)
        return time.time() - st.st_mtime

    def age_ctime(self):
        """get the age of build from ctime"""
        st = os.stat("%s.log" % self.basename)
        return time.time() - st.st_ctime

    def read_log(self):
        """read full log file"""
        return open(self.basename+".log", "r")

    def read_err(self):
        """read full err file"""
        try:
            return open(self.basename+".err", 'r')
        except IOError:
            # No such file
            return StringIO()

    def log_checksum(self):
        f = self.read_log()
        try:
            return hashlib.sha1(f.read()).hexdigest()
        finally:
            f.close()

    def summary(self):
        (revid, timestamp) = self.revision_details()
        status = self.status()
        return BuildSummary(self.host, self.tree, self.compiler, revid, status)

    def revision_details(self):
        """get the revision of build

        :return: Tuple with revision id and timestamp (if available)
        """
        revid = None
        timestamp = None
        f = self.read_log()
        try:
            for l in f:
                if l.startswith("BUILD COMMIT REVISION: "):
                    revid = l.split(":", 1)[1].strip()
                elif l.startswith("BUILD COMMIT TIME"):
                    timestamp = l.split(":", 1)[1].strip()
        finally:
            f.close()

        return (revid, timestamp)

    def status(self):
        """get status of build

        :return: tuple with build status
        """
        log = self.read_log()
        try:
            err = self.read_err()
            try:
                return build_status_from_logs(log, err)
            finally:
                err.close()
        finally:
            log.close()

    def err_count(self):
        """get status of build"""
        file = self.read_err()
        return len(file.readlines())


class UploadBuildResultStore(object):

    def __init__(self, path):
        """Open the database.

        :param path: Build result base directory
        """
        self.path = path

    def get_new_builds(self):
        for name in os.listdir(self.path):
            try:
                (build, tree, host, compiler, extension) = name.split(".")
            except ValueError:
                continue
            if build != "build" or extension != "log":
                continue
            yield self.get_build(tree, host, compiler)

    def build_fname(self, tree, host, compiler):
        return os.path.join(self.path, "build.%s.%s.%s" % (tree, host, compiler))

    def has_host(self, host):
        for name in os.listdir(self.path):
            try:
                if name.split(".")[2] == host:
                    return True
            except IndexError:
                pass
        return False

    def get_build(self, tree, host, compiler):
        basename = self.build_fname(tree, host, compiler)
        logf = "%s.log" % basename
        if not os.path.exists(logf):
            raise NoSuchBuildError(tree, host, compiler)
        return Build(basename, tree, host, compiler)


class BuildResultStore(object):
    """The build farm build result database."""

    def __init__(self, path):
        """Open the database.

        :param path: Build result base directory
        """
        self.path = path

    def get_build(self, tree, host, compiler, rev):
        basename = self.build_fname(tree, host, compiler, rev)
        logf = "%s.log" % basename
        if not os.path.exists(logf):
            raise NoSuchBuildError(tree, host, compiler, rev)
        return Build(basename, tree, host, compiler, rev)

    def build_fname(self, tree, host, compiler, rev):
        """get the name of the build file"""
        return os.path.join(self.path, "build.%s.%s.%s-%s" % (tree, host, compiler, rev))

    def get_old_revs(self, tree, host, compiler):
        """get a list of old builds and their status."""
        ret = []
        logfiles = [d for d in os.listdir(self.path) if d.startswith("build.%s.%s.%s-" % (tree, host, compiler)) and d.endswith(".log")]
        for l in logfiles:
            m = re.match(".*-([0-9A-Fa-f]+).log$", l)
            if m:
                rev = m.group(1)
                stat = os.stat(os.path.join(self.path, l))
                # skip the current build
                if stat.st_nlink == 2:
                    continue
                ret.append(self.get_build(tree, host, compiler, rev))

        ret.sort(lambda a, b: cmp(a.age_mtime(), b.age_mtime()))

        return ret

    def upload_build(self, build):
        (rev, rev_timestamp) = build.revision_details()

        if not rev:
            raise Exception("Unable to find revision in %r log" % build)

        new_basename = self.build_fname(build.tree, build.host, build.compiler, rev)
        try:
            existing_build = self.get_build(build.tree, build.host, build.compiler, rev)
        except NoSuchBuildError:
            pass
        else:
            existing_build.remove_logs()
        os.link(build.basename+".log", new_basename+".log")
        if os.path.exists(build.basename+".err"):
            os.link(build.basename+".err", new_basename+".err")
        return Build(new_basename, build.tree, build.host, build.compiler, rev)

    def get_previous_revision(self, tree, host, compiler, revision):
        raise NoSuchBuildError(tree, host, compiler, revision)

    def get_latest_revision(self, tree, host, compiler):
        raise NoSuchBuildError(tree, host, compiler)
