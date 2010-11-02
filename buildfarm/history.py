#!/usr/bin/python
# script to show recent checkins in cvs / svn / git
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
import time

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
        """get recent cvs/svn entries"""
        # validate the tree
        t = self.db.trees[tree]

        if t.scm == "cvs":
            self._cvs_diff(t, author, date, tree)
        elif t.scm == "svn":
            self._svn_diff(t, revision, tree)
        elif t.scm == "git":
            self._git_diff(t, revision, tree)
        else:
            raise Exception("Unknown VCS %s" % t.scm)

    def _svn_diff(self, t, revision, tree):
        """show recent svn entries"""

        os.chdir(os.path.join(UNPACKED_DIR, tree))

        # determine the most recent version known to this database
        for l in commands.getoutput("svn info").splitlines():
            if l.startswith("Revision"):
                current_revision = l.strip().split(":")
                break
        else:
            raise Exception("Unable to find current revision")

        if (not revision.isdigit() or int(revision) < 0 or
            int(revision) > int(current_revision)):
            raise Exception("unknown revision[%s]" % revision)

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
        title = "SVN Diff in %s:%s for revision r%s" % (
            tree, t.branch, revision)

        old_revision = revision - 1
        cmd = "svn diff -r %s:%s" % (old_revision, revision)

        return (title, entry, tree, [(cmd, commands.getoutput("%s 2> /dev/null" % cmd))])

    def _cvs_diff(self, t, author, date, tree):
        """show recent cvs entries"""
        os.chdir(os.path.join(UNPACKED_DIR, tree))

        log = self._log(tree)

        # for paranoia, check that the date string is a valid date
        if not date[0].isdigit():
            raise Exception("unknown date")

        for i in range(log):
            if author == log[i]["AUTHOR"] and date == log[i]["DATE"]:
                entry = log[i]
                break
        else:
            raise Exception("Unable to locate commit information author[%s] data[%s]." % (
                author, date))

        t1 = time.ctime(date-60+(TIMEOFFSET*60*60)).strip()
        t2 = time.ctime(date+60+(TIMEOFFSET*60*60)).strip()

        title = "CVS Diff in %s:%s for %s" % (tree, t.branch, t1)

        if entry["TAG"] != "" and entry["REVISIONS"] != "":
            raise Exception("sorry, cvs diff on branches not currently possible due to a limitation in cvs")

        os.environ['CVS_PASSFILE'] = os.path.join(BASEDIR, ".cvspass")

        if entry["REVISIONS"]:
            diffs = []
            for f in entry["REVISIONS"].keys():
                if entry["REVISIONS"][f]["REV1"] == "NONE":
                    cmd = "cvs rdiff -u -r 0 -r %s %s" % (entry["REVISIONS"][f]["REV2"], f)
                elif entry["REVISIONS"][f]["REV2"] == "NONE":
                    cmd = "cvs rdiff -u -r %s -r 0 %s" % (
                        entry["REVISIONS"][f]["REV1"], f)
                else:
                    cmd = "cvs diff -b -u -r %s -r %s %s" % (
                        entry["REVISIONS"][f]["REV1"], entry["REVISIONS"][f]["REV2"], f)

                diffs.append((cmd, commands.getoutput("%s 2> /dev/null" % cmd)))
        else:
            cmd = "cvs diff -b -u -D \"%s %s\" -D \"%s %s\" %s" % (
                t1, TIMEZONE, t2, TIMEZONE, entry["FILES"])

            diffs = [(cmd, commands.getoutput("%s 2> /dev/null" % cmd))]
        return (title, entry, tree, diffs)

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
