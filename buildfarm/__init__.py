#!/usr/bin/python
# Simple database query script for the buildfarm
#
# Copyright (C) Jelmer Vernooij <jelmer@samba.org>	   2010
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


class Tree(object):
    """A tree to build."""

    def __init__(self, name, scm, repo, branch, subdir="", srcdir=""):
        self.name = name
        self.repo = repo
        self.scm = scm
        self.branch = branch
        self.subdir = subdir
        self.srcdir = srcdir
        self.scm = scm

    def get_branch(self):
        from buildfarm.history import GitBranch
        return GitBranch(self.repo, self.branch)

    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.name)


def read_trees_from_conf(path):
    """Read trees from a configuration file.

    :param path: tree path
    :return: Dictionary with trees
    """
    ret = {}
    cfp = ConfigParser.ConfigParser()
    cfp.read(path)
    for s in cfp.sections():
        ret[s] = Tree(name=s, **dict(cfp.items(s)))
    return ret


def lcov_extract_percentage(text):
    """Extract the coverage percentage from the lcov file."""
    m = re.search('\<td class="headerItem".*?\>Code\&nbsp\;covered\:\<\/td\>.*?\n.*?\<td class="headerValue".*?\>([0-9.]+) \%', text)
    if m:
        return m.group(1)
    else:
        return None


class BuildFarm(object):

    LCOVHOST = "magni"
    OLDAGE = 60*60*4,
    DEADAGE = 60*60*24*4

    def __init__(self, path=None):
        if path is None:
            path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.path = path
        self.webdir = os.path.join(self.path, "web")
        if not os.path.isdir(path):
            raise Exception("web directory %s does not exist" % self.webdir)
        self.trees = read_trees_from_conf(os.path.join(self.webdir, "trees.conf"))
        self.builds = self._open_build_results()
        self.upload_builds = self._open_upload_build_results()
        self.hostdb = self._open_hostdb()
        self.compilers = self._load_compilers()
        self.lcovdir = os.path.join(self.path, "lcov/data")

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.path)

    def _open_build_results(self):
        from buildfarm import data
        return data.BuildResultStore(os.path.join(self.path, "data", "oldrevs"))

    def _open_upload_build_results(self):
        from buildfarm import data
        return data.UploadBuildResultStore(os.path.join(self.path, "data", "upload"))

    def _open_hostdb(self):
        from buildfarm import hostdb
        return hostdb.HostDatabase(
            os.path.join(self.path, "hostdb.sqlite"))

    def _load_compilers(self):
        from buildfarm import util
        return util.load_list(os.path.join(self.webdir, "compilers.list"))

    def lcov_status(self, tree):
        """get status of build"""
        from buildfarm import data, util
        file = os.path.join(self.lcovdir, self.LCOVHOST, tree, "index.html")
        try:
            lcov_html = util.FileLoad(file)
        except (OSError, IOError):
            # File does not exist
            raise data.NoSuchBuildError(tree, self.LCOVHOST, "lcov")

        perc = lcov_extract_percentage(lcov_html)
        if perc is None:
            ret = ""
        else:
            ret = perc
        return perc

    def get_build(self, tree, host, compiler, rev=None):
        if rev:
            return self.builds.get_build(tree, host, compiler, rev)
        else:
            return self.upload_builds.get_build(tree, host, compiler)

    def get_new_builds(self):
        from buildfarm import data
        for host in self.hostdb.hosts():
            for tree in self.trees:
                for compiler in self.compilers:
                    # By building the log file name this way, using only the list of
                    # hosts, trees and compilers as input, we ensure we
                    # control the inputs
                    try:
                        yield self.upload_builds.get_build(tree, host.name, compiler)
                    except data.NoSuchBuildError:
                        continue


class CachingBuildFarm(BuildFarm):

    def __init__(self, path=None, readonly=False, cachedirname=None):
        self._cachedirname = cachedirname
        self.readonly = readonly
        super(CachingBuildFarm, self).__init__(path)

    def _get_cachedir(self):
        if self._cachedirname is not None:
            return os.path.join(self.path, self._cachedirname)
        else:
            return os.path.join(self.path, "cache")

    def _open_build_results(self):
        from buildfarm import data
        return data.CachingBuildResultStore(os.path.join(self.path, "data", "oldrevs"),
                self._get_cachedir(), readonly=self.readonly)

    def _open_upload_build_results(self):
        from buildfarm import data
        return data.CachingUploadBuildResultStore(os.path.join(self.path, "data", "upload"),
                self._get_cachedir(), readonly=self.readonly)

    def lcov_status(self, tree):
        """get status of build"""
        from buildfarm import data, util
        cachefile = os.path.join(self._get_cachedir(),
                                    "lcov.%s.%s.status" % (self.LCOVHOST, tree))
        file = os.path.join(self.lcovdir, self.LCOVHOST, tree, "index.html")
        try:
            st1 = os.stat(file)
        except OSError:
            # File does not exist
            raise data.NoSuchBuildError(tree, self.LCOVHOST, "lcov")
        try:
            st2 = os.stat(cachefile)
        except OSError:
            # file does not exist
            st2 = None

        if st2 and st1.st_ctime <= st2.st_mtime:
            ret = util.FileLoad(cachefile)
            if ret == "":
                return None
            return ret

        perc = super(CachingBuildFarm, self).lcov_status(tree)
        if not self.readonly:
            util.FileSave(cachefile, perc)
        return perc
