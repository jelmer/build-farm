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

from buildfarm.build import (
    MissingRevisionInfo,
    NoSuchBuildError,
    )
from buildfarm.sqldb import BuildFarm
from buildfarm.web import build_uri
from email.mime.text import MIMEText
import logging
import optparse
import resource
import smtplib

parser = optparse.OptionParser("import-and-analyse [options]")
parser.add_option("--dry-run", help="Will cause the script to send output to stdout instead of to sendmail.", action="store_true")
parser.add_option("--verbose", help="Be verbose", action="count")

(opts, args) = parser.parse_args()

resource.setrlimit(resource.RLIMIT_RSS, (300000, 300000))
resource.setrlimit(resource.RLIMIT_DATA, (300000, 300000))

buildfarm = BuildFarm(timeout=40.0)

smtp = smtplib.SMTP()
smtp.connect()

def check_and_send_mails(cur, old):
    t = buildfarm.trees[cur.tree]

    cur_rev = cur.revision_details()
    cur_status = cur.status()

    old_rev = old.revision_details()
    old_status = old.status()

    if not cur_status.regressed_since(old_status):
        if opts.verbose >= 3:
            print "... hasn't regressed since %s: %s" % (old_rev, old_status)
        return

    branch = t.get_branch()
    recipients = set()
    change_log = ""

    for rev in branch.log(from_rev=cur.revision, exclude_revs=set([old.revision])):
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

See %(build_link)s

The build may have been broken by one of the following commits:

%(change_log)s
    """ % {
        "tree": cur.tree, "host": cur.host, "compiler": cur.compiler,
        "change_log": change_log,
        "scm": t.scm,
        "branch": t.branch,
        "cur_rev": cur_rev,
        "old_rev": old_rev,
        "cur_status": cur_status,
        "old_status": old_status,
        "build_link": build_uri("http://build.samba.org/build.cgi", cur)
        }

    msg = MIMEText(body)
    msg["Subject"] = "BUILD of %s:%s BROKEN on %s with %s AT REVISION %s" % (cur.tree, t.branch, cur.host, cur.compiler, cur_rev)
    msg["From"] = "\"Build Farm\" <build@samba.org>"
    msg["To"] = ",".join(recipients)
    if not opts.dry_run:
        smtp.sendmail(msg["From"], [msg["To"]], msg.as_string())
    else:
        print msg.as_string()


for build in buildfarm.get_new_builds():
    if build in buildfarm.builds:
        continue

    if not opts.dry_run:
        old_build = build
        try:
            build = buildfarm.builds.upload_build(old_build)
        except MissingRevisionInfo:
            print "No revision info in %r, skipping" % build
            continue

    try:
        rev = build.revision_details()
    except MissingRevisionInfo:
        print "No revision info in %r, skipping" % build
        continue

    if opts.verbose >= 2:
        print "%s... " % build,
        print str(build.status())

    try:
        if opts.dry_run:
            # Perhaps this is a dry run and rev is not in the database yet?
            prev_rev = buildfarm.builds.get_latest_revision(build.tree, build.host, build.compiler)
        else:
            prev_rev = buildfarm.builds.get_previous_revision(build.tree, build.host, build.compiler, rev)
    except NoSuchBuildError:
        if opts.verbose >= 1:
            print "Unable to find previous build for %s,%s,%s" % (build.tree, build.host, build.compiler)
        # Can't send a nastygram until there are 2 builds..
    else:
        try:
            assert prev_rev is not None
            prev_build = buildfarm.builds.get_build(build.tree, build.host, build.compiler, prev_rev)
        except NoSuchBuildError:
            if opts.verbose >= 1:
                print "Previous build %s has disappeared" % prev_build
        else:
            check_and_send_mails(build, prev_build)

    if not opts.dry_run:
        old_build.remove()
        buildfarm.commit()

smtp.quit()
