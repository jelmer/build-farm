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
from testtools import TestCase
import shutil
import tempfile


class BuildFarmTestCase(TestCase):
    """Test case class that provides a build farm data directory and convenience methods.
    """

    def create_mock_logfile(self, tree, host, compiler, rev=None, 
            kind="stdout", contents="FOO"):
        basename = "build.%s.%s.%s" % (tree, host, compiler)
        if rev:
            basename += "-%s" % rev
            path = os.path.join(self.path, "data", "oldrevs", basename + "-%s" % rev)
        else:
            path = os.path.join(self.path, "data", "upload", basename)
        if kind == "stdout":
            path += ".log"
        elif kind == "stderr":
            path += ".err"
        else:
            raise ValueError("Unknown log kind %r" % kind)
        f = open(path, 'w+')
        try:
            f.write(contents)
        finally:
            f.close()
        return path

    def write_hosts(self, hosts):
        f = open(os.path.join(self.path, "web", "hosts.list"), "w")
        try:
            for host in hosts:
                f.write("%s\n" % host)
        finally:
            f.close()

    def write_compilers(self, compilers):
        f = open(os.path.join(self.path, "web", "compilers.list"), "w")
        try:
            for compiler in compilers:
                f.write("%s\n" % compiler)
        finally:
            f.close()

    def write_trees(self, trees):
        f = open(os.path.join(self.path, "web", "trees.conf"), "w")
        try:
            for t in trees:
                f.write("[%s]\n" % t)
                for k, v in trees[t].iteritems():
                    f.write("%s = %s\n" % (k, v))
                f.write("\n")
        finally:
            f.close()

    def setUp(self):
        super(BuildFarmTestCase, self).setUp()
        self.path = tempfile.mkdtemp()

        for subdir in ["data", "data/upload", "data/oldrevs", "cache", "web", "lcov", "lcov/data"]:
            os.mkdir(os.path.join(self.path, subdir))

    def tearDown(self):
        shutil.rmtree(self.path)
        super(BuildFarmTestCase, self).tearDown()
