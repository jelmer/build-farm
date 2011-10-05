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
    BuildDiff,
    MissingRevisionInfo,
    NoSuchBuildError,
    )
from buildfarm import BuildFarm
from buildfarm.web import build_uri
from email.mime.text import MIMEText
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

    if cur.tree is "waf":
        # no point sending emails, as the email addresses are invalid
        return

    if cur.tree is "samba_3_waf":
        # no emails for this until it stabilises a bit
        return

    t = buildfarm.trees[cur.tree]
    diff = BuildDiff(t, old, cur)

    if not diff.is_regression():
        if opts.verbose >= 3:
            print "... hasn't regressed since %s: %s" % (diff.old_rev, diff.old_status)
        return

    recipients = set()
    change_log = ""

    for rev in diff.revisions():
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
        "cur_rev": diff.new_rev,
        "old_rev": diff.old_rev,
        "cur_status": diff.new_status,
        "old_status": diff.old_status,
        "build_link": build_uri("http://build.samba.org/build.cgi", cur)
        }

    msg = MIMEText(body)
    msg["Subject"] = "BUILD of %s:%s BROKEN on %s with %s AT REVISION %s" % (cur.tree, t.branch, cur.host, cur.compiler, diff.new_rev)
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
            prev_build = buildfarm.builds.get_latest_build(build.tree, build.host, build.compiler)
        else:
            prev_build = buildfarm.builds.get_previous_build(build.tree, build.host, build.compiler, rev)
    except NoSuchBuildError:
        if opts.verbose >= 1:
            print "Unable to find previous build for %s,%s,%s" % (build.tree, build.host, build.compiler)
        # Can't send a nastygram until there are 2 builds..
    else:
        check_and_send_mails(build, prev_build)

    if not opts.dry_run:
        old_build.remove()
        buildfarm.commit()

smtp.quit()
