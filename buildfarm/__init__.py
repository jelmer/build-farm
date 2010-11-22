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

GIT_ROOT = "/data/git"


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
        if self.scm == "git":
            from buildfarm.history import GitBranch
            return GitBranch(os.path.join(GIT_ROOT, self.repo), self.branch)
        else:
            raise NotImplementedError(self.scm)

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


def lcov_extract_percentage(f):
    """Extract the coverage percentage from the lcov file."""
    m = re.search('\<td class="headerItem".*?\>Code\&nbsp\;covered\:\<\/td\>.*?\n.*?\<td class="headerValue".*?\>([0-9.]+) \%', f.read())
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
        from buildfarm.build import BuildResultStore
        path = os.path.join(self.path, "data", "oldrevs")
        return BuildResultStore(path)

    def _open_upload_build_results(self):
        from buildfarm.build import UploadBuildResultStore
        path = os.path.join(self.path, "data", "upload")
        return UploadBuildResultStore(path)

    def _open_hostdb(self):
        from buildfarm import hostdb
        return hostdb.PlainTextHostDatabase.from_file(os.path.join(self.webdir, "hosts.list"))

    def _load_compilers(self):
        from buildfarm import util
        return set(util.load_list(os.path.join(self.webdir, "compilers.list")))

    def commit(self):
        pass

    def lcov_status(self, tree):
        """get status of build"""
        from buildfarm.build import NoSuchBuildError
        file = os.path.join(self.lcovdir, self.LCOVHOST, tree, "index.html")
        try:
            lcov_html = open(file, 'r')
        except (OSError, IOError):
            # File does not exist
            raise NoSuchBuildError(tree, self.LCOVHOST, "lcov")
        try:
            return lcov_extract_percentage(lcov_html)
        finally:
            lcov_html.close()

    def get_build(self, tree, host, compiler, rev=None, checksum=None):
        if rev is not None:
            return self.builds.get_build(tree, host, compiler, rev,
                checksum=checksum)
        else:
            return self.upload_builds.get_build(tree, host, compiler)

    def get_new_builds(self):
        hostnames = set([host.name for host in self.hostdb.hosts()])
        for build in self.upload_builds.get_all_builds():
            if (build.tree in self.trees and
                build.compiler in self.compilers and
                build.host in hostnames):
                yield build

    def get_last_builds(self):
        return sorted(self.get_new_builds(), reverse=True)

    def get_tree_builds(self, tree):
        ret = []
        for build in self.builds.get_all_builds():
            if build.tree == tree:
                ret.append(build)
        ret.sort(reverse=True)
        return ret

    def host_last_build(self, host):
        return max([build.upload_time for build in self.get_host_builds(host)])

    def get_host_builds(self, host):
        from buildfarm.build import NoSuchBuildError
        ret = []
        for compiler in self.compilers:
            for tree in sorted(self.trees.keys()):
                try:
                    ret.append(self.get_build(tree, host, compiler))
                except NoSuchBuildError:
                    pass
        ret.sort(reverse=True)
        return ret
