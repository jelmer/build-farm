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


from buildfarm import util

import commands
import os

BASEDIR = "/home/build/master"
HISTORYDIR = "/home/build/master/cache"
TIMEZONE = "PST"
TIMEOFFSET = 0
UNPACKED_DIR = "/home/ftp/pub/unpacked"

class History(object):

    def __init__(self, db):
        self.db = db

    def _log(self, tree):
        return util.LoadStructure(os.path.join(HISTORYDIR, "history.%s" % tree))

    def diff(self, author, date, tree, revision):
        """get recent git entries"""
        # validate the tree
        t = self.db.trees[tree]

        if t.scm == "git":
            self._git_diff(t, revision, tree)
        else:
            raise Exception("Unknown VCS %s" % t.scm)

    def _git_diff(self, t, revision, tree):
        """show recent git entries"""
        os.chdir(os.path.join(UNPACKED_DIR, tree))

        log = self._log(tree)

        # backwards? why? well, usually our users are looking for the newest
        # stuff, so it's most likely to be found sooner
        for i in range(len(log), 0, -1):
            if log[i]["REVISION"] == revision:
                entry = log[i]
                break
        else:
            raise Exception("Unable to locate commit information revision[%s]." % revision)

        # get information about the current diff
        title = "GIT Diff in %s:%s for revision %s" % (
            tree, t.branch, revision)

        cmd = "git diff %s^ %s ./" % (revision, revision)
        return (title, entry, tree, [(cmd, commands.getoutput("%s 2> /dev/null" % cmd))])

    def authors(self, tree):
        log = self._log(tree)
        authors = set()
        for entry in log:
            authors.add(entry["AUTHOR"])
        return authors

    def history(self, tree, author=None):
        """get commit history for the given tree"""
        log = self._log(tree)

        # what? backwards? why is that? oh... I know... we want the newest first
        for i in range(len(log), 0, -1):
            entry = log[i]
            if (author is None or
                (author == "") or
                (author == "ALL") or
                (author == entry["AUTHOR"])):
                yield entry, tree
