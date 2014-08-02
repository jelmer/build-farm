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

from buildfarm.build import BuildStatus
from buildfarm.sqldb import distinct_builds, Cast, StormBuild, setup_schema, StormHostDatabase
from buildfarm.tree import Tree
from storm.database import create_database
from storm.expr import Desc
from storm.store import Store

import ConfigParser
import os
import re

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
    m = re.search('\<td class="headerCovTableEntryLo".*?\>([0-9.]+) \%', f.read())
    if m:
        return m.group(1)
    else:
        return None


class BuildFarm(object):

    LCOVHOST = "coverage"
    OLDAGE = 60*60*4,
    DEADAGE = 60*60*24*4

    def __init__(self, path=None, store=None, timeout=0.5):
        self.timeout = timeout
        self.store = store
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
        path = os.path.join(self.path, "data", "oldrevs")
        from buildfarm.build import BuildResultStore
        return BuildResultStore(path, self._get_store())

    def _open_upload_build_results(self):
        from buildfarm.build import UploadBuildResultStore
        path = os.path.join(self.path, "data", "upload")
        return UploadBuildResultStore(path)

    def _open_hostdb(self):
        return StormHostDatabase(self._get_store())

    def _load_compilers(self):
        from buildfarm import util
        return set(util.load_list(os.path.join(self.webdir, "compilers.list")))

    def commit(self):
        if self.store is not None:
            self.store.commit()

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

    def unused_fns(self, tree):
        """get status of build"""
        from buildfarm.build import NoSuchBuildError
        file = os.path.join(self.lcovdir, self.LCOVHOST, tree, "unused-fns.txt")
        try:
            unused_fns_file = open(file, 'r')
        except (OSError, IOError):
            # File does not exist
            raise NoSuchBuildError(tree, self.LCOVHOST, "unused_fns")
        try:
            return "unused-fns.txt"
        finally:
            unused_fns_file.close()

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
        result = self._get_store().find(StormBuild)
        return distinct_builds(result.order_by(Desc(StormBuild.upload_time)))

    def get_summary_builds(self):
        """Return last build age, status for each tree/host/compiler.

        :return: iterator over tree, status
        """
        store = self._get_store()
        return ((tree, BuildStatus.__deserialize__(status_str))
                for (tree, status_str) in store.execute("""
SELECT obd.tree, obd.status AS status_str
FROM build obd
INNER JOIN(
    SELECT MAX(age) age, tree, host, compiler
    FROM build
    GROUP BY tree, host, compiler
) ibd ON obd.age = ibd.age AND
         obd.tree = ibd.tree AND
         obd.host = ibd.host AND
         obd.compiler = ibd.compiler;
"""))

    def get_tree_builds(self, tree):
        result = self._get_store().find(StormBuild,
            Cast(StormBuild.tree, "TEXT") == Cast(tree, "TEXT"))
        return distinct_builds(result.order_by(Desc(StormBuild.upload_time)))

    def host_last_build(self, host):
        return max([build.upload_time for build in self.get_host_builds(host)])

    def get_host_builds(self, host):
        result = self._get_store().find(StormBuild, StormBuild.host == host)
        return distinct_builds(result.order_by(Desc(StormBuild.upload_time)))

    def _get_store(self):
        if self.store is not None:
            return self.store
        db_dir_path = os.path.join(self.path, "db")
        if not os.path.isdir(db_dir_path):
            os.mkdir(db_dir_path)
        db_path = os.path.join(db_dir_path, "hostdb.sqlite")
        db = create_database("sqlite:%s?timeout=%f" % (db_path, self.timeout))
        self.store = Store(db)
        setup_schema(self.store)
        return self.store

    def get_revision_builds(self, tree, revision=None):
        return self._get_store().find(StormBuild,
            Cast(StormBuild.tree, "TEXT") == Cast(tree, "TEXT"),
            Cast(StormBuild.revision, "TEXT") == Cast(revision, "TEXT"))
