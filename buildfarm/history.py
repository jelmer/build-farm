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

from cStringIO import StringIO

from dulwich.objects import Tree
from dulwich.patch import write_tree_diff
from dulwich.repo import Repo


class Branch(object):
    """A version control branch."""

    def log(self, limit=None):
        raise NotImplementedError(self.log)

    def diff(self, revision):
        raise NotImplementedError(self.diff)

    def changes_summary(self, revision):
        raise NotImplementedError(self.changes_summary)


class Revision(object):

    def __init__(self, revision, date, committer, author, message):
        self.revision = revision
        self.date = date
        self.author = author
        self.committer = committer
        self.message = message


class GitBranch(Branch):

    def __init__(self, path, branch="master"):
        self.repo = Repo(path)
        self.store = self.repo.object_store
        self.branch = branch

    def _changes_for(self, commit):
        if len(commit.parents) == 0:
            parent_tree = Tree().id
        else:
            parent_tree = self.store[commit.parents[0]].tree
        return self.store.tree_changes(parent_tree, commit.tree)

    def _revision_from_commit(self, commit):
        return Revision(commit.id, commit.commit_time,
            committer=commit.committer, author=commit.author,
            message=commit.message)

    def log(self, from_rev=None, exclude_revs=None, limit=None):
        if exclude_revs is None:
            exclude_revs = set()
        if from_rev is None:
            try:
                commit = self.repo["refs/heads/%s" % self.branch]
            except KeyError:
                return
            from_rev = commit.id
        done = set()
        pending_commits = [from_rev]
        while pending_commits != []:
             commit_id = pending_commits.pop(0)
             commit = self.repo[commit_id]
             yield self._revision_from_commit(commit)
             done.add(commit.id)
             if len(done) >= limit:
                 return
             exclude_revs.add(commit.id)
             # FIXME: Add sorted by commit_time
             for p in commit.parents:
                 if p in exclude_revs:
                     continue
                 pending_commits.append(p)
                 exclude_revs.add(p)

    def changes_summary(self, revision):
        commit = self.repo[revision]
        added = set()
        modified = set()
        removed = set()
        for ((oldpath, newpath), (oldmode, newmode), (oldsha, newsha)) in self._changes_for(commit):
            if oldpath is None:
                added.add(newpath)
            elif newpath is None:
                removed.add(oldpath)
            else:
                modified.add(newpath)
        return (added, modified, removed)

    def diff(self, revision):
        commit = self.repo[revision]
        f = StringIO()
        if len(commit.parents) == 0:
            parent_tree = Tree().id
        else:
            parent_tree = self.store[commit.parents[0]].tree
        write_tree_diff(f, self.store, parent_tree, commit.tree)
        return (self._revision_from_commit(commit), f.getvalue())
