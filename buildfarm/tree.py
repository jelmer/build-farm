
#!/usr/bin/python
# Tree support
#
# Copyright (C) Jelmer Vernooij <jelmer@samba.org>   2010
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


from buildfarm.history import GitBranch
import os

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
            return GitBranch(os.path.join(GIT_ROOT, self.repo), self.branch)
        else:
            raise NotImplementedError(self.scm)

    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.name)
