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
import hashlib
import os
import re
import time
import util


class BuildSummary(object):

    def __init__(self, host, tree, compiler, rev, status):
        self.host = host
        self.tree = tree
        self.compiler = compiler
        self.rev = rev
        self.status = status


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

    def broken_host(self):
        if "disk full" in self.other_failures:
            return True
        return False

    def _status_tuple(self):
        return [v for (k, v) in self.stages]

    def regressed_since(self, other):
        """Check if this build has regressed since another build."""
        if "disk full" in self.other_failures:
            return False
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

    def __str__(self):
        return repr((self.stages, self.other_failures))


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

    for l in log:
        m = re.match("^([A-Z_]+) STATUS:(\s*\d+)$", l)
        if m:
            stages.append((m.group(1), int(m.group(2).strip())))
            if m.group(1) == "TEST":
                test_seen = 1
            continue
        m = re.match("^ACTION (PASSED|FAILED):\s+test$", l)
        if m and not test_seen:
            if m.group(1) == "PASSED":
                stages.append(("TEST", 0))
            else:
                stages.append(("TEST", 1))
            continue

        if l.startswith("No space left on device"):
            ret.other_failures.add("disk full")
            continue
        if l.startswith("maximum runtime exceeded"):
            ret.other_failures.add("timeout")
            continue
        m = re.match("^(PANIC|INTERNAL ERROR):.*$", l)
        if m:
            ret.other_failures.add("panic")
            continue
        if l.startswith("testsuite-failure: ") or l.startswith("testsuite-error: "):
            test_failures += 1
            continue
        if l.startswith("testsuite-success: "):
            test_successes += 1
            continue

    # Scan err file for specific errors
    for l in err:
        if "No space left on device" in l:
            ret.other_failures.add("disk full")

    def map_stage(name, result):
        if name != "TEST":
            return (name, result)
        # TEST is special
        if test_successes + test_failures == 0:
            # No granular test output
            return ("TEST", result)
        if result == 1 and test_failures == 0:
            ret.other_failures.add("inconsistent test result")
            return ("TEST", -1)
        return ("TEST", test_failures)

    ret.stages = [map_stage(name, result) for (name, result) in stages]
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

    def __init__(self, store, tree, host, compiler, rev=None):
        self._store = store
        self.tree = tree
        self.host = host
        self.compiler = compiler
        self.rev = rev

    ###################
    # the mtime age is used to determine if builds are still happening
    # on a host.
    # the ctime age is used to determine when the last real build happened

    def age_mtime(self):
        """get the age of build from mtime"""
        file = self._store.build_fname(self.tree, self.host, self.compiler, self.rev)

        st = os.stat("%s.log" % file)
        return time.time() - st.st_mtime

    def age_ctime(self):
        """get the age of build from ctime"""
        file = self._store.build_fname(self.tree, self.host, self.compiler, self.rev)

        st = os.stat("%s.log" % file)
        return time.time() - st.st_ctime

    def read_log(self):
        """read full log file"""
        return open(self._store.build_fname(self.tree, self.host, self.compiler, self.rev)+".log", "r")

    def read_err(self):
        """read full err file"""
        try:
            return open(self._store.build_fname(self.tree, self.host, self.compiler, self.rev)+".err", 'r')
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
        (revid, commit_revid, timestamp) = self.revision_details()
        if commit_revid:
            revid = commit_revid
        status = self.status()
        return BuildSummary(self.host, self.tree, self.compiler, revid, status)

    def revision_details(self):
        """get the revision of build

        :return: Tuple with revision id and timestamp (if available)
        """

        revid = None
        commit_revid = None
        timestamp = None
        f = self.read_log()
        try:
            for l in f.readlines():
                if l.startswith("BUILD COMMIT REVISION: "):
                    commit_revid = l.split(":", 1)[1].strip()
                elif l.startswith("BUILD REVISION: "):
                    revid = l.split(":", 1)[1].strip()
                elif l.startswith("BUILD COMMIT TIME"):
                    timestamp = l.split(":", 1)[1].strip()
        finally:
            f.close()

        return (revid, commit_revid, timestamp)

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


class CachingBuild(Build):
    """Build subclass that caches some of the results that are expensive
    to calculate."""

    def revision_details(self):
        file = self._store.build_fname(self.tree, self.host, self.compiler, self.rev)
        cachef = self._store.cache_fname(self.tree, self.host, self.compiler, self.rev)
        st1 = os.stat("%s.log" % file)

        try:
            st2 = os.stat("%s.revision" % cachef)
        except OSError:
            # File does not exist
            st2 = None

        # the ctime/mtime asymmetry is needed so we don't get fooled by
        # the mtime update from rsync
        if st2 and st1.st_ctime <= st2.st_mtime:
            (revid, commit_revid, timestamp) = util.FileLoad("%s.revision" % cachef).split(":", 2)
            if timestamp == "":
                timestamp = None
            if revid == "":
                revid = None
            if commit_revid == "":
                commit_revid = None
            return (revid, commit_revid, timestamp)
        (revid, commit_revid, timestamp) = super(CachingBuild, self).revision_details()
        if not self._store.readonly:
            util.FileSave("%s.revision" % cachef, "%s:%s:%s" % (revid, commit_revid or "", timestamp or ""))
        return (revid, commit_revid, timestamp)

    def err_count(self):
        file = self._store.build_fname(self.tree, self.host, self.compiler, self.rev)
        cachef = self._store.cache_fname(self.tree, self.host, self.compiler, self.rev)
        st1 = os.stat("%s.err" % file)

        try:
            st2 = os.stat("%s.errcount" % cachef)
        except OSError:
            # File does not exist
            st2 = None

        if st2 and st1.st_ctime <= st2.st_mtime:
            return util.FileLoad("%s.errcount" % cachef)

        ret = super(CachingBuild, self).err_count()

        if not self._store.readonly:
            util.FileSave("%s.errcount" % cachef, str(ret))

        return ret

    def status(self):
        file = self._store.build_fname(self.tree, self.host, self.compiler, self.rev)
        cachefile = self._store.cache_fname(self.tree, self.host, self.compiler, self.rev)+".status"

        st1 = os.stat("%s.log" % file)

        try:
            st2 = os.stat(cachefile)
        except OSError:
            # No such file
            st2 = None

        if st2 and st1.st_ctime <= st2.st_mtime:
            return BuildStatus(*eval(util.FileLoad(cachefile)))

        ret = super(CachingBuild, self).status()

        if not self._store.readonly:
            util.FileSave(cachefile, str(ret))

        return ret


class UploadBuildResultStore(object):

    def __init__(self, path):
        """Open the database.

        :param path: Build result base directory
        """
        self.path = path

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
        logf = self.build_fname(tree, host, compiler) + ".log"
        if not os.path.exists(logf):
            raise NoSuchBuildError(tree, host, compiler)
        return Build(self, tree, host, compiler)


class CachingUploadBuildResultStore(UploadBuildResultStore):

    def __init__(self, basedir, cachedir, readonly=False):
        """Open the database.

        :param readonly: Whether to avoid saving cache files
        """
        super(CachingUploadBuildResultStore, self).__init__(basedir)
        self.cachedir = cachedir
        self.readonly = readonly

    def cache_fname(self, tree, host, compiler):
        return os.path.join(self.cachedir, "build.%s.%s.%s" % (tree, host, compiler))

    def get_build(self, tree, host, compiler):
        logf = self.build_fname(tree, host, compiler) + ".log"
        if not os.path.exists(logf):
            raise NoSuchBuildError(tree, host, compiler)
        return CachingBuild(self, tree, host, compiler)


class BuildResultStore(object):
    """The build farm build result database."""

    def __init__(self, path):
        """Open the database.

        :param path: Build result base directory
        """
        self.path = path

    def get_build(self, tree, host, compiler, rev):
        logf = self.build_fname(tree, host, compiler, rev) + ".log"
        if not os.path.exists(logf):
            raise NoSuchBuildError(tree, host, compiler, rev)
        return Build(self, tree, host, compiler, rev)

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
                build = self.get_build(tree, host, compiler, rev)
                r = {
                    "STATUS": build.status(),
                    "REVISION": rev,
                    "TIMESTAMP": build.age_ctime(),
                    }
                ret.append(r)

        ret.sort(lambda a, b: cmp(a["TIMESTAMP"], b["TIMESTAMP"]))

        return ret

"""
    def get_previous_revision(self, tree, host, compiler, revision):
        # Look up the database to find the previous status
        $st = $dbh->prepare("SELECT status, revision, commit_revision FROM build WHERE tree = ? AND host = ? AND compiler = ? AND revision != ? AND commit_revision != ? ORDER BY id DESC LIMIT 1")
        $st->execute( $tree, $host, $compiler, $rev, $commit)

        while ( my @row = $st->fetchrow_array ) {
            $old_status_html = @row[0]
            $old_rev = @row[1]
            $old_commit = @row[2]

    def upload_build(self, build):

        my $expression = "SELECT checksum FROM build WHERE age >= ? AND tree = ? AND host = ? AND compiler = ?"
        my $st = $dbh->prepare($expression)
        $st->execute($stat->ctime, $tree, $host, $compiler)
        # Don't bother if we've already processed this file
        my $relevant_rows = $st->fetchall_arrayref()
        $st->finish()

        if relevant_rows > 0:
            return

        data = build.read_log()
        # Don't bother with empty logs, they have no meaning (and would all share the same checksum)
        if not data:
            return

        err = build.read_err()
        checksum = build.log_checksum()
        if ($dbh->selectrow_array("SELECT checksum FROM build WHERE checksum = '$checksum'")):
            $dbh->do("UPDATE BUILD SET age = ? WHERE checksum = ?", undef, 
                 ($stat->ctime, $checksum))
            continue

        (rev, rev_timestamp) = build.revision_details()

        status_html = db.build_status_from_logs(data, err)

        $st->finish()

        $st = $dbh->prepare("INSERT INTO build (tree, revision, commit_revision, host, compiler, checksum, age, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
        $st->execute($tree, $rev, $commit, $host, $compiler, $checksum, $stat->ctime, $status_html)

       $st->finish()

        cur_status = db.build_status_info_from_html(rev, commit, status_html)

        # If we were able to put this into the DB (ie, a
        # one-off event, so we won't repeat this), then also
        # hard-link the log files to the revision, if we know
        # it.

        # This ensures that the names under 'oldrev' are well known and well formed 
        log_rev = self.build_fname(tree, host, compiler, commit) + ".log"
        err_rev = self.build_fname(tree, host, compiler, commit) + ".err"
        unlink $log_rev
        unlink $err_rev
        link($logfn . ".log", $log_rev) || die "Failed to link $logfn to $log_rev"

        # this prevents lots of links building up with err files
        copy($logfn . ".err", $err_rev) || die "Failed to copy $logfn to $err_rev"
        unlink($logfn . ".err")
        link($err_rev, $logfn . ".err")
        """


class CachingBuildResultStore(BuildResultStore):

    def __init__(self, basedir, cachedir, readonly=False):
        super(CachingBuildResultStore, self).__init__(basedir)

        self.cachedir = cachedir
        check_dir_exists("cache", self.cachedir)

        self.readonly = readonly

    def get_build(self, tree, host, compiler, rev):
        logf = self.build_fname(tree, host, compiler, rev) + ".log"
        if not os.path.exists(logf):
            raise NoSuchBuildError(tree, host, compiler, rev)
        return CachingBuild(self, tree, host, compiler, rev)

    def cache_fname(self, tree, host, compiler, rev):
        return os.path.join(self.cachedir, "build.%s.%s.%s-%s" % (tree, host, compiler, rev))



