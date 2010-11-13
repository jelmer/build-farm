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

from buildfarm import data
from buildfarm.sqldb import StormCachingBuildFarm
from email.mime.text import MIMEText
import logging
import optparse
import smtplib

parser = optparse.OptionParser("import-and-analyse [options]")
parser.add_option("--dry-run", help="Will cause the script to send output to stdout instead of to sendmail.", action="store_true")
parser.add_option("--verbose", help="Be verbose", action="count")

(opts, args) = parser.parse_args()

buildfarm = StormCachingBuildFarm()

smtp = smtplib.SMTP()
smtp.connect()

def check_and_send_mails(tree, host, compiler, cur, old):
    t = buildfarm.trees[tree]

    (cur_rev, cur_rev_timestamp) = cur.revision_details()
    cur_status = cur.status()

    (old_rev, old_rev_timestamp) = old.revision_details()
    old_status = old.status()

    if not cur_status.regressed_since(old_status):
        if opts.verbose >= 3:
            print "... hasn't regressed since %s: %s" % (old_rev, old_status)
        return

    recipients = set()
    change_log = ""

    for rev in t.get_branch().log(from_rev=cur.rev, exclude_revs=set([old.rev])):
        recipients.add(rev.author)
        recipients.add(rev.committer)
        change_log += """
revision: %s
author: %s
committer: %s
message:
    %s
""" % (rev.revision, rev.author, rev.committer, rev.message)

    body = """
Broken build for tree %(tree)s on host %(host)s with compiler %(compiler)s

Tree %(tree)s is %(scm)s branch %(branch)s.

Build status for new revision %(cur_rev)s is %(cur_status)s
Build status for old revision %(old_rev)s was %(old_status)s

See http://build.samba.org/?function=View+Build;host=%(host)s;tree=%(tree)s;compiler=%(compiler)s

The build may have been broken by one of the following commits:

%(change_log)s
    """ % {"tree": tree, "host": host, "compiler": compiler, "change_log": change_log, "scm": t.scm, "branch": t.branch,
            "cur_rev": cur_rev, "old_rev": old_rev, "cur_status": cur_status, "old_status": old_status }

    msg = MIMEText(body)
    msg["Subject"] = "BUILD of %s:%s BROKEN on %s with %s AT REVISION %s" % (tree, t.branch, host, compiler, cur_rev)
    msg["From"] = "\"Build Farm\" <build@samba.org>"
    msg["To"] = ",".join(recipients.keys())
    if not opts.dry_run:
        smtp.send(msg["From"], [msg["To"]], msg.as_string())
    else:
        print msg.as_string()


for build in buildfarm.get_new_builds():
    if opts.verbose >= 2:
        print "Processing %s..." % build,

    if build in buildfarm.builds:
        continue

    if not opts.dry_run:
        build = buildfarm.builds.upload_build(build)

    (rev, rev_timestamp) = build.revision_details()

    if opts.verbose >= 2:
        print str(build.status())

    try:
        if opts.dry_run:
            # Perhaps this is a dry run and rev is not in the database yet?
            prev_rev = buildfarm.builds.get_latest_revision(build.tree, build.host, build.compiler)
        else:
            prev_rev = buildfarm.builds.get_previous_revision(build.tree, build.host, build.compiler, rev)
    except data.NoSuchBuildError:
        if opts.verbose >= 1:
            print "Unable to find previous build for %s,%s,%s" % (build.tree, build.host, build.compiler)
        # Can't send a nastygram until there are 2 builds..
    else:
        try:
            prev_build = buildfarm.get_build(build.tree, build.host, build.compiler, prev_rev)
        except data.NoSuchBuildError:
            if opts.verbose >= 1:
                print "Previous build %s has disappeared" % prev_build
        else:
            check_and_send_mails(build.tree, build.host, build.compiler, build, prev_build)

    if not opts.dry_run:
        # When the new web script is introduced, kill the build here:
        # build.remove()
        buildfarm.commit()

smtp.quit()
