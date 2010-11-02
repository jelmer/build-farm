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


import ConfigParser
import os
import re
import time
import util


def span(classname, contents):
    return "<span class=\"%s\">%s</span>" % (classname, contents)


def check_dir_exists(kind, path):
    if not os.path.isdir(path):
        raise Exception("%s directory %s does not exist" % (kind, path))


class NoSuchBuildError(Exception):
    """The build with the specified name does not exist."""

    def __init__(self, tree, host, compiler, rev=None):
        self.tree = tree
        self.host = host
        self.compiler = compiler
        self.rev = rev


class Tree(object):
    """A tree to build."""

    def __init__(self, name, scm, repo, branch, subdir="", srcdir=""):
        self.name = name
        self.repo = repo
        self.branch = branch
        self.subdir = subdir
        self.srcdir = srcdir

    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.name)


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
        f = open(self._store.build_fname(self.tree, self.host, self.compiler, self.rev)+".log", "r")
        try:
            return f.read()
        finally:
            f.close()

    def read_err(self):
        """read full err file"""
        return util.FileLoad(self._store.build_fname(self.tree, self.host, self.compiler, self.rev)+".err")

    def revision_details(self):
        """get the revision of build

        :return: Tuple with revision id and timestamp (if available)
        """
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
            (revid, timestamp) = util.FileLoad("%s.revision" % cachef).split(":", 1)
            if timestamp == "":
                return (revid, None)
            else:
                return (revid, timestamp)

        revid = None
        timestamp = None
        f = open("%s.log" % file, 'r')
        try:
            for l in f.readlines():
                if l.startswith("BUILD COMMIT REVISION: "):
                    revid = l.split(":", 1)[1].strip()
                elif l.startswith("BUILD REVISION: "):
                    revid = l.split(":", 1)[1].strip()
                elif l.startswith("BUILD COMMIT TIME"):
                    timestamp = l.split(":", 1)[1].strip()
        finally:
            f.close()

        if not self._store.readonly:
            util.FileSave("%s.revision" % cachef, "%s:%s" % (revid, timestamp or ""))

        return (revid, timestamp)

    def status(self):
        """get status of build

        :return: string with build status
        """
        # FIXME: This should return a tuple

        file = self._store.build_fname(self.tree, self.host, self.compiler, self.rev)
        cachefile = self._store.cache_fname(self.tree, self.host, self.compiler, self.rev)+".status"
        st1 = os.stat("%s.log" % file)

        try:
            st2 = os.stat(cachefile)
        except OSError:
            # No such file
            st2 = None

        if st2 and st1.st_ctime <= st2.st_mtime:
            return util.FileLoad(cachefile)

        log = self.read_log()
        err = self.read_err()

        ret = self._store.html_build_status_from_logs(log, err)

        if not self._store.readonly:
            util.FileSave(cachefile, ret)

        return ret

    def err_count(self):
        """get status of build"""
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

        try:
            err = util.FileLoad("%s.err" % file)
        except OSError:
            # File does not exist
            return 0

        ret = util.count_lines(err)

        if not self._store.readonly:
            util.FileSave("%s.errcount" % cachef, str(ret))

        return ret


def read_trees_from_conf(path):
    """Read trees from a configuration file."""
    ret = {}
    cfp = ConfigParser.ConfigParser()
    cfp.readfp(open(path))
    for s in cfp.sections():
        ret[s] = Tree(name=s, **dict(cfp.items(s)))
    return s


class BuildResultStore(object):
    """The build farm build result database."""

    OLDAGE = 60*60*4,
    DEADAGE = 60*60*24*4
    LCOVHOST = "magni"

    def __init__(self, basedir, readonly=False):
        """Open the database.

        :param basedir: Build result base directory
        :param readonly: Whether to avoid saving cache files
        """
        self.basedir = basedir
        check_dir_exists("base", self.basedir)
        self.readonly = readonly

        self.webdir = os.path.join(basedir, "web")
        check_dir_exists("web", self.webdir)

        self.datadir = os.path.join(basedir, "data")
        check_dir_exists("data", self.datadir)

        self.cachedir = os.path.join(basedir, "cache")
        check_dir_exists("cache", self.cachedir)

        self.lcovdir = os.path.join(basedir, "lcov/data")
        check_dir_exists("lcov", self.lcovdir)

        self.compilers = util.load_list(os.path.join(self.webdir, "compilers.list"))
        self.hosts = util.load_hash(os.path.join(self.webdir, "hosts.list"))

        self.trees = read_trees_from_conf(os.path.join(self.webdir, "trees.conf"))

    def get_build(self, tree, host, compiler, rev=None):
        logf = self.build_fname(tree, host, compiler, rev) + ".log"
        if not os.path.exists(logf):
            raise NoSuchBuildError(tree, host, compiler, rev)
        return Build(self, tree, host, compiler, rev)

    def cache_fname(self, tree, host, compiler, rev=None):
        if rev is not None:
            return os.path.join(self.cachedir, "build.%s.%s.%s-%s" % (tree, host, compiler, rev))
        else:
            return os.path.join(self.cachedir, "build.%s.%s.%s" % (tree, host, compiler))

    def build_fname(self, tree, host, compiler, rev=None):
        """get the name of the build file"""
        if rev is not None:
            return os.path.join(self.datadir, "oldrevs/build.%s.%s.%s-%s" % (tree, host, compiler, rev))
        return os.path.join(self.datadir, "upload/build.%s.%s.%s" % (tree, host, compiler))

    def html_build_status_from_logs(self, log, err):
        def span_status(st):
            if st is None:
                return span("status unknown", "?")
            elif st == 0:
                return span("status passed", "ok")
            else:
                return span("status failed", st)
        (cstatus, bstatus, istatus, tstatus, sstatus, other_failures) = self.build_status_from_logs(log, err)
        ostatus = ""
        if "panic" in other_failures:
            ostatus += "/"+span("status panic", "PANIC")
        if "disk full" in other_failures:
            ostatus += "/"+span("status failed", "disk full")
        if "timeout" in other_failures:
            ostatus += "/"+span("status failed", "timeout")
        if sstatus is not None:
            ostatus += "/".span("status checker", sstatus)
        return "%s/%s/%s/%s%s" % (span_status(cstatus), span_status(bstatus), span_status(istatus), span_status(tstatus), ostatus)

    def build_status_from_logs(self, log, err):
        """get status of build"""
        m = re.search("TEST STATUS:(.*)", log)
        if m:
            tstatus = m.group(1)
        else:
            m = re.search("ACTION (PASSED|FAILED): test", log)
            if m:
                test_failures = len(re.findall("testsuite-(failure|error): ", log))
                test_successes = len(re.findall("testsuite-success: ", log))
                if test_successes > 0:
                    tstatus = test_failures
                else:
                    tstatus = 255
            else:
                tstatus = None

        m = re.search("INSTALL STATUS:(.*)", log)
        if m:
            istatus = m.group(1)
        else:
            istatus = None

        m = re.search("BUILD STATUS:(.*)", log)
        if m:
            bstatus = m.group(1)
        else:
            bstatus = None

        m = re.search("CONFIGURE STATUS:(.*)", log)
        if m:
            cstatus = m.group(1)
        else:
            cstatus = None

        other_failures = set()
        m = re.search("(PANIC|INTERNAL ERROR):.*", log)
        if m:
            other_failures.add("panic")

        if "No space left on device" in err or "No space left on device" in log:
            other_failures.add("disk full")

        if "maximum runtime exceeded" in log:
            other_failures.add("timeout")

        m = re.search("CC_CHECKER STATUS: (.*)", log)
        if m:
            sstatus = m.group(1)
        else:
            sstatus = None

        return (cstatus, bstatus, istatus, tstatus, sstatus, other_failures)

    def build_status_info_from_string(self, rev_seq, rev, status_raw):
        """find the build status as an object

        the 'value' gets one point for passing each stage"""
        status_split = status_raw.split("/")
        status_str = ""
        status_arr = []
        status_val = 0

        for r in status_split:
            r = r.strip()

            if r == "ok":
                e = 0
            elif r.isdigit():
                e = int(r)
                if e < 0:
                    e = 1
            else:
                e = 1

            if status_str != "":
                status_str += "/"
            status_str += "%d" % r

            status_val += e

            status_arr.append(e)

        return {
            "rev": rev,
            "rev_seq": rev_seq,
            "array": status_arr,
            "string": status_str,
            "value": status_val,
            }

    def build_status_info_from_html(self, rev_seq, rev, status_html):
        """find the build status as an perl object

        the 'value' gets one point for passing each stage
        """
        status_raw = util.strip_html(status_html)
        return self.build_status_info_from_string(rev_seq, rev, status_raw)

    def build_status_info(self, tree, host, compiler, rev_seq):
        """find the build status as an object

        the 'value' gets one point for passing each stage
        """
        build = self.get_build(tree, host, compiler, rev_seq)
        rev, rev_time = build.revision_details()
        status_html = build.status()
        return self.build_status_info_from_html(rev_seq, rev, status_html)

    def lcov_status(self, tree):
        """get status of build"""
        cachefile = os.path.join(self.cachedir, "lcov.%s.%s.status" % (
            self.LCOVHOST, tree))
        file = os.path.join(self.lcovdir, self.LCOVHOST, tree, "index.html")
        try:
            st1 = os.stat(file)
        except OSError:
            # File does not exist
            raise NoSuchBuildError(tree, self.LCOVHOST, "lcov")
        try:
            st2 = os.stat(cachefile)
        except OSError:
            # file does not exist
            st2 = None

        if st2 and st1.st_ctime <= st2.st_mtime:
            return util.FileLoad(cachefile)

        lcov_html = util.FileLoad(file)
        m = re.search('\<td class="headerItem".*?\>Code\&nbsp\;covered\:\<\/td\>.*?\n.*?\<td class="headerValue".*?\>([0-9.]+) \%', lcov_html)
        if m:
            ret = "<a href=\"/lcov/data/%s/%s\">%s %%</a>" % (self.LCOVHOST, tree, m.group(1))
        else:
            ret = ""
        if self.readonly:
            util.FileSave(cachefile, ret)
        return ret

    def get_old_revs(self, tree, host, compiler):
        """get a list of old builds and their status."""
        ret = []
        directory = os.path.join(self.datadir, "oldrevs")
        logfiles = [d for d in os.listdir(directory) if d.startswith("build.%s.%s.%s-" % (tree, host, compiler)) and d.endswith(".log")]
        for l in logfiles:
            m = re.match(".*-([0-9A-Fa-f]+).log$", l)
            if m:
                rev = m.group(1)
                stat = os.stat(os.path.join(directory, l))
                # skip the current build
                if stat.st_nlink == 2:
                    continue
                build = self.get_build(tree, host, compiler, rev)
                r = {
                    "STATUS": build.status(),
                    "REVISION": rev,
                    "TIMESTAMP": stat.st_ctime
                    }
                ret.append(r)

        ret.sort(lambda a, b: cmp(a["TIMESTAMP"], b["TIMESTAMP"]))

        return ret

    def has_host(self, host):
        return host in os.listdir(os.path.join(self.datadir, "upload"))

    def host_age(self, host):
        """get the overall age of a host"""
        ret = None
        for compiler in self.compilers:
            for tree in self.trees:
                try:
                    build = self.get_build(tree, host, compiler)
                except NoSuchBuildError:
                    pass
                else:
                    ret = min(ret, build.age_mtime())
        return ret
