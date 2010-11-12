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

from buildfarm.history import GitBranch

from dulwich.repo import Repo

import tempfile
from testtools import TestCase


class GitBranchTests(TestCase):

    def setUp(self):
        super(GitBranchTests, self).setUp()
        self.repo = Repo.init(tempfile.mkdtemp())

    def test_log_empty(self):
        branch = GitBranch(self.repo.path, "master")
        self.assertEquals([], list(branch.log()))

    def test_log_commits(self):
        branch = GitBranch(self.repo.path, "master")
        self.repo.do_commit("message", committer="Jelmer Vernooij")
        log = list(branch.log())
        self.assertEquals(1, len(log))
        self.assertEquals("message", log[0].message)

    def test_empty_diff(self):
        branch = GitBranch(self.repo.path, "master")
        revid = self.repo.do_commit("message", committer="Jelmer Vernooij")
        entry, diff = list(branch.diff(revid))
        self.assertEquals("message", entry.message)
        self.assertEquals("", diff)
