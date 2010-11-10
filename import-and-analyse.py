#!/usr/bin/python
# Write sqlite entries for test reports in the build farm
# Copyright (C) 2007-2010 Jelmer Vernooij <jelmer@samba.org>
# Copyright (C) 2007-2010 Andrew Bartlett <abartlet@samba.org>
# Published under the GNU GPL

"""Script to parse build farm log files from the data directory, import
them into the database, add links to the oldrevs/ directory and send
some mail chastising the possible culprits when the build fails, based
on recent commits.
"""

from buildfarm import (
    BuildFarm,
    data,
    hostdb,
    )
import commands
from email.mime.text import MIMEText
import logging
import optparse
import os
import re
import smtplib

dry_run = True

parser = optparse.OptionParser("import-and-analyse [options]")
parser.add_option("--dry-run", help="Will cause the script to send output to stdout instead of to sendmail.", action="store_true")
parser.add_option("--verbose", help="Be verbose", action="count")

(opts, args) = parser.parse_args()

UNPACKED_DIR = "/home/ftp/pub/unpacked"

# we open readonly here as only apache(www-run) has write access
buildfarm = BuildFarm()
db = data.BuildResultStore(os.path.abspath(os.path.dirname(__file__)), True)
hostsdb = buildfarm.hostdb

hosts = hostsdb.hosts()

smtp = smtplib.SMTP()
smtp.connect()

class Log(object):

    def __init__(self):
        self.change_log = None
        self.committers = set()
        self.authors = set()
        self.recipients = None


def get_log_git(tree, cur, old):
    cmd = "cd %s/%s && git log --pretty=full %s..%s ./" % (UNPACKED_DIR, tree, old, cur)

    log = Log()

    log.change_log = commands.getoutput(cmd)
    #print log.change_log

    # get the list of possible culprits
    log2 = log.change_log

    for m in re.findall("[\n]*Author: [^<]*<([^>]+)>\nCommit: [^<]*<([^>]+)>\n(.*)$", log.change_log):
        author = m.group(1)
        committer = m.group(2)

        # handle cherry-picks from svnmirror repo
        author = author.replace("0c0555d6-39d7-0310-84fc-f1cc0bd64818", "samba.org")

        # for now only send reports to samba.org addresses.
        if not "@samba.org" in author:
            author = None

        if author:
            log.authors.add(author)
        if committer:
            log.committers.add(committer)

    # Add a URL to the diffs for each change
    log.change_log = re.sub("([\n]*commit ([0-9a-f]+))", "\\1\nhttp:\/\/build.samba.org\/?function=diff;tree=%s;revision=\\2" % tree, log.change_log)

    all = set()
    all.update(log.authors)
    all.update(log.committers)
    log.recipients = all
    return log


def get_log(tree, cur, old):
    treedir = os.path.join(UNPACKED_DIR, tree)

    if os.path.exists(os.path.join(treedir, ".git")):
        return get_log_git(tree, cur, old)
    else:
        raise Exception("Unknown vcs for %s" % treedir)


def check_and_send_mails(tree, host, compiler, cur, old):
    t = buildfarm.trees[tree]

    (cur_rev, cur_rev_timestamp) = cur.revision_details()
    cur_status = cur.status()

    (old_rev, old_rev_timestamp) = old.revision_details()
    old_status = old.status()

    if dry_run:
        print "rev=%s status=%s" % (cur_rev, cur_status)
        print "old rev=%s status=%s" % (old_rev, old_status)

    if not cur_status.regressed_since(old_status):
        if dry_run:
            print "the build didn't get worse since %r" % old_status
        return

    log = get_log(tree, cur, old)
    if not log:
        if dry_run:
            print "no log"
        return

    recipients = ",".join(log.recipients.keys())

    body = """
Broken build for tree %(tree)s on host %(host)s with compiler %(compiler)s

Tree %(tree)s is %(scm)s branch %(branch)s.

Build status for new revision %(cur_rev)s is %(cur_status)s
Build status for old revision %(old_rev)s was %(old_status)s

See http://build.samba.org/?function=View+Build;host=%(host)s;tree=%(tree)s;compiler=%(compiler)s

The build may have been broken by one of the following commits:

%(change_log)s
    """ % {"tree": tree, "host": host, "compiler": compiler, "change_log": log.change_log, "scm": t.scm, "branch": t.branch}

    msg = MIMEText(body)
    msg["Subject"] = "BUILD of %s:%s BROKEN on %s with %s AT REVISION %s" % (tree, t.branch, host, compiler, cur_rev)
    msg["From"] = "\"Build Farm\" <build@samba.org>"
    msg["To"] = recipients
    smtp.send(msg["From"], [msg["To"]], msg.as_string())


for host in hosts:
    for tree in buildfarm.trees:
        for compiler in buildfarm.compilers:
            if opts.verbose >= 2:
                print "Looking for a log file for %s %s %s..." % (host, compiler, tree)

            # By building the log file name this way, using only the list of
            # hosts, trees and compilers as input, we ensure we
            # control the inputs
            try:
                build = buildfarm.upload_builds.get_build(host, tree, compiler)
            except data.NoSuchBuildError:
                continue

            if opts.verbose >= 2:
                print "Processing %s..." % build

            db.upload_build(build)

            (rev, commit_rev, rev_timestamp) = db.revision_details()

            try:
                prev_rev = db.get_previous_revision(tree, host, compiler, rev)
            except hostdb.NoSuchBuild:
                # Can't send a nastygram until there are 2 builds..
                continue
            else:
                prev_build = db.get_build(tree, host, compiler, prev_rev)
                check_and_send_mails(tree, host, compiler, build.status(), prev_build.status())


smtp.quit()
