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


import os
import re
import util


def span(classname, contents):
    return "<span class=\"%s\">%s</span>" % (classname, contents)


def check_dir_exists(kind, path):
    if not os.path.isdir(path):
        raise Exception("%s directory %s does not exist" % (kind, path))



def status_info_cmp(self, s1, s2):
    a1 = s1["array"]
    a2 = s2["array"]
    c1 = 0
    c2 = 0

    i = 0
    while True:
        if i >= len(a1) or i >= len(a2):
            break

        if c1 != c2:
            return c2 - c1

        if a1[i] != a2[i]:
            return a2[i] - a1[i]

    return s2["value"] - s1["value"]


class BuildfarmDatabase(object):

    OLDAGE = 60*60*4,
    DEADAGE = 60*60*24*4
    LCOVHOST = "magni"

    def __init__(self, basedir, readonly=False):
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

        self.trees = {
            'ccache': {
                'scm': 'git',
                'repo': 'ccache',
                'branch': 'master',
                'subdir': '',
                'srcdir': ''
            },
            'ccache-maint': {
                'scm': 'git',
                'repo': 'ccache',
                'branch': 'maint',
                'subdir': '',
                'srcdir': ''
            },
            'ppp': {
                'scm': 'git',
                'repo': 'ppp',
                'branch': 'master',
                'subdir': '',
                'srcdir': ''
            },
            'build_farm': {
                'scm': 'svn',
                'repo': 'build-farm',
                'branch': 'trunk',
                'subdir': '',
                'srcdir': ''
            },
            'samba-web': {
                'scm': 'svn',
                'repo': 'samba-web',
                'branch': 'trunk',
                'subdir': '',
                'srcdir': ''
            },
            'samba-docs': {
                'scm': 'svn',
                'repo': 'samba-docs',
                'branch': 'trunk',
                'subdir': '',
                'srcdir': ''
            },
            'lorikeet': {
                'scm': 'svn',
                'repo': 'lorikeeet',
                'branch': 'trunk',
                'subdir': '',
                'srcdir': ''
            },
            'samba_3_current': {
                'scm': 'git',
                'repo': 'samba.git',
                'branch': 'v3-5-test',
                'subdir': '',
                'srcdir': 'source'
            },
            'samba_3_next': {
                'scm': 'git',
                'repo': 'samba.git',
                'branch': 'v3-6-test',
                'subdir': '',
                'srcdir': 'source'
            },
            'samba_3_master': {
                'scm': 'git',
                'repo': 'samba.git',
                'branch': 'master',
                'subdir': '',
                'srcdir': 'source'
            },
            'samba_4_0_test': {
                'scm': 'git',
                'repo': 'samba.git',
                'branch': 'master',
                'subdir': '',
                'srcdir': 'source4'
            },
            'libreplace': {
                'scm': 'git',
                'repo': 'samba.git',
                'branch': 'master',
                'subdir': 'lib/replace/',
                'srcdir': ''
            },
            'talloc': {
                'scm': 'git',
                'repo': 'samba.git',
                'branch': 'master',
                'subdir': 'lib/talloc/',
                'srcdir': ''
            },
            'tdb': {
                'scm': 'git',
                'repo': 'samba.git',
                'branch': 'master',
                'subdir': 'lib/tdb/',
                'srcdir': ''
            },
            'ldb': {
                'scm': 'git',
                'repo': 'samba.git',
                'branch': 'master',
                'subdir': 'lib/ldb/',
                'srcdir': ''
            },
            'pidl': {
                'scm': 'git',
                'repo': 'samba.git',
                'branch': 'master',
                'subdir': 'pidl/',
                'srcdir': ''
            },
            'rsync': {
                'scm': 'git',
                'repo': 'rsync.git',
                'branch': 'HEAD',
                'subdir': '',
                'srcdir': ''
            }
        }

    def cache_fname(self, tree, host, compiler, rev=None):
        if rev is not None:
            return os.path.join(self.cachedir, "build.%s.%s.%s-%s" % (tree,host,compiler,rev))
        else:
            return os.path.join(self.cachedir, "build.%s.%s.%s" % (tree,host,compiler))

    def build_fname(self, tree, host, compiler, rev=None):
        """get the name of the build file"""
        if rev is not None:
            return os.path.join(self.datadir, "oldrevs/build.%s.%s.%s-%s" % (tree, host, compiler, rev))
        return os.path.join(self.datadir, "upload/build.%s.%s.%s" % (tree, host, compiler))

    ###################
    # the mtime age is used to determine if builds are still happening
    # on a host.
    # the ctime age is used to determine when the last real build happened

    ##############################################
    def build_age_mtime(self, host, tree, compiler, rev):
        """get the age of build from mtime"""
        file = self.build_fname(tree, host, compiler, rev)

        try:
            st = os.stat("%s.log" % file)
        except OSError:
            # File does not exist
            return -1
        else:
            return time.time() - st.st_mtime

    def build_age_ctime(self, host, tree, compiler, rev):
        """get the age of build from ctime"""
        file = self.build_fname(tree, host, compiler, rev)

        try:
            st = os.stat("%s.log" % file)
        except OSError:
            return -1
        else:
            return time.time() - st.st_ctime

    def build_revision_details(self, host, tree, compiler, rev=None):
        """get the svn revision of build"""
        file = self.build_fname(tree, host, compiler, rev)
        cachef = self.cache_fname(tree, host, compiler, rev)

        # don't fast-path for trees with git repository:
        # we get the timestamp as rev and want the details
        if rev:
            if tree not in self.trees:
                return rev
            if self.trees[tree]["scm"] != "git":
                return rev

        try:
            st1 = stat("%s.log" % file)
        except OSError:
            # File does not exist
            return "NO SUCH FILE"

        try:
            st2 = os.stat("%s.revision" % cachef)
        except OSError:
            # File does not exist
            st2 = None

        # the ctime/mtime asymmetry is needed so we don't get fooled by
        # the mtime update from rsync 
        if st2 and st1.st_ctime <= st2.st_mtime:
            return util.FileLoad("%s.revision" % cachef)

        log = util.FileLoad("%s.log" % file)

        m = re.search("BUILD COMMIT REVISION: (.*)", log)
        if m:
            ret = m.group(1)
        else:
            m = re.search("BUILD REVISION: (.*)", log)
            if m:
                ret = m.group(1)
            else:
                ret = ""

        m = re.search("BUILD COMMIT TIME: (.*)", log)
        if m:
            ret += ":" + m.group(1)

        if not self.readonly:
            util.FileSave("%s.revision" % cachef, ret)

        return ret

    def build_revision(self, host, tree, compiler, rev):
        r = self.build_revision_details(host, tree, compiler, rev)
        return r.split(":")[0]

    def build_revision_time(self, host, tree, compiler, rev):
        r = self.build_revision_details(host, tree, compiler, rev)
        return r.split(":", 1)[1]

    def build_status_from_logs(self, log, err):
        """get status of build"""
        def span_status(st):
            if st == 0:
                return span("status passed", "ok")
            else:
                return span("status failed", st)

        m = re.search("TEST STATUS:(.*)", log)
        if m:
            tstatus = span_status(m.group(1))
        else:
            m = re.search("ACTION (PASSED|FAILED): test", log)
            if m:
                test_failures = len(re.findall("testsuite-(failure|error): ", log))
                test_successes = len(re.findall("testsuite-success: ", log))
                if test_successes > 0:
                    tstatus = span_status(test_failures)
                else:
                    tstatus = span_status(255)
            else:
                tstatus = span("status unknown", "?")

        m = re.search("INSTALL STATUS:(.*)", log)
        if m:
            istatus = span_status(m.group(1))
        else:
            istatus = span("status unknown", "?")

        m = re.search("BUILD STATUS:(.*)", log)
        if m:
            bstatus = span_status(m.group(1))
        else:
            bstatus = span("status unknown", "?")

        m = re.search("CONFIGURE STATUS:(.*)", log)
        if m:
            cstatus = span_status(m.group(1))
        else:
            cstatus = span("status unknown", "?")

        m = re.search("(PANIC|INTERNAL ERROR):.*", log)
        if m:
            sstatus = "/"+span("status panic", "PANIC")
        else:
            sstatus = ""

        if "No space left on device" in err or "No space left on device" in log:
            dstatus = "/"+span("status failed", "disk full")
        else:
            dstatus = ""

        if "maximum runtime exceeded" in log:
            tostatus = "/"+span("status failed", "timeout")
        else:
            tostatus = ""

        m = re.search("CC_CHECKER STATUS: (.*)", log)
        if m and int(m.group(1)) > 0:
            sstatus += "/".span("status checker", m.group(1))

        return "%s/%s/%s/%s%s%s%s" % (
                cstatus, bstatus, istatus, tstatus, sstatus, dstatus, tostatus)

    def build_status(self, host, tree, compiler, rev):
        """get status of build"""
        file = self.build_fname(tree, host, compiler, rev)
        cachefile = self.cache_fname(tree, host, compiler, rev)+".status"
        try:
            st1 = os.stat("%s.log" % file)
        except OSError:
            # No such file
            return "Unknown Build"

        try:
            st2 = os.stat(cachefile)
        except OSError:
            # No such file
            st2 = None

        if st2 and st1.st_ctime <= st2.st_mtime:
            return util.FileLoad(cachefile)

        log = util.FileLoad("%s.log" % file)
        try:
            err = util.FileLoad("%s.err" % file)
        except OSError:
            # No such file
            err = ""

        ret = self.build_status_from_logs(log, err)

        if not self.readonly:
            util.FileSave(cachefile, ret)

        return ret

    def build_status_info_from_string(self, rev_seq, rev, status_raw):
        """find the build status as an perl object

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

    def build_status_info(self, host, tree, compiler, rev_seq):
        """find the build status as an perl object

        the 'value' gets one point for passing each stage
        """
        rev = self.build_revision(host, tree, compiler, rev_seq)
        status_html = self.build_status(host, tree, compiler, rev_seq)
        return self.build_status_info_from_html(rev_seq, rev, status_html)

    def lcov_status(self, tree):
        """get status of build"""
        cachefile = os.path.join(self.cachedir, "lcov.%s.%s.status" % (self.LCOVHOST, tree))
        file = os.path.join(self.lcovdir, self.LCOVHOST, tree, "index.html")
        try:
            st1 = os.stat(file)
        except OSError:
            # File does not exist
            return ""
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

    def err_count(self, host, tree, compiler, rev):
        """get status of build"""
        file = self.build_fname(tree, host, compiler, rev)
        cachef = self.cache_fname(tree, host, compiler, rev)

        try:
            st1 = os.stat("%s.err" % file)
        except OSError:
            # File does not exist
            return 0
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

        if not self.readonly:
            util.FileSave("%s.errcount" % cachef, str(ret))

        return ret

    def read_log(self, tree, host, compiler, rev):
        """read full log file"""
        return util.FileLoad(self.build_fname(tree, host, compiler, rev)+".log")

    def read_err(self, tree, host, compiler, rev):
        """read full err file"""
        return util.FileLoad(self.build_fname(tree, host, compiler, rev)+".err")

    def get_old_revs(self, tree, host, compiler):
        """get a list of old builds and their status."""
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
                r = {
                    "STATUS": self.build_status(host, tree, compiler, rev),
                    "REVISION": rev,
                    "TIMESTAMP": stat.st_ctime
                    }
                ret.append(r)

        ret.sort(lambda a, b: cmp(a["TIMESTAMP"], b["TIMESTAMP"]))

        return ret

    def has_host(self, host):
        return host in os.listdir(os.path.join(self.datadir, "upload"))