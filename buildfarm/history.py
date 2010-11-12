#!/usr/bin/python
# script to show recent checkins in git
#
# Copyright (C) Andrew Tridgell <tridge@samba.org>     2001
# Copyright (C) Martin Pool <mbp@samba.org>            2003
# Copyright (C) Jelmer Vernooij <jelmer@samba.org>     2007-2010
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


from dulwich.repo import Repo
import subprocess

BASEDIR = "/home/build/master"
HISTORYDIR = "/home/build/master/cache"
TIMEZONE = "PST"
TIMEOFFSET = 0
UNPACKED_DIR = "/home/ftp/pub/unpacked"


class Branch(object):

    def authors(self):
        ret = set()
        for rev in self.log():
            ret.add(rev.author)
        return ret

    def log(self):
        raise NotImplementedError(self.log)

    def diff(self, revision):
        raise NotImplementedError(self.diff)


class Revision(object):

    def __init__(self, revision, date, author, message, modified=[], added=[], removed=[]):
        self.revision = revision
        self.date = date
        self.author = author
        self.message = message
        self.modified = modified
        self.added = added
        self.removed = removed


class GitBranch(object):

    def __init__(self, path, branch="master"):
        self.repo = Repo(path)
        self.branch = branch

    def _revision_from_commit(self, commit):
        # FIXME: modified/added/removed
        return Revision(commit.id, commit.commit_time, commit.author, commit.message)

    def log(self):
        try:
            commit = self.repo["refs/heads/%s" % self.branch]
        except KeyError:
            return
        done = set()
        pending_commits = [commit.id]
        while pending_commits != []:
             commit_id = pending_commits.pop(0)
             commit = self.repo[commit_id]
             yield self._revision_from_commit(commit)
             done.add(commit.id)
             # FIXME: Add sorted by commit_time
             pending_commits.extend(commit.parents)

    def diff(self, revision):
        commit = self.repo[revision]
        x = subprocess.Popen(["git", "show", revision], cwd=self.repo.path, stdout=subprocess.PIPE)
        return (self._revision_from_commit(commit), x.communicate()[0])
