#!/usr/bin/python
# This CGI script presents the results of the build_farm build
#
# Copyright (C) Andrew Tridgell <tridge@samba.org>     2001-2005
# Copyright (C) Andrew Bartlett <abartlet@samba.org>   2001
# Copyright (C) Vance Lankhaar  <vance@samba.org>      2002-2005
# Copyright (C) Martin Pool <mbp@samba.org>            2001
# Copyright (C) Jelmer Vernooij <jelmer@samba.org>     2007-2010
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

# TODO: Allow filtering of the "Recent builds" list to show
# e.g. only broken builds or only builds that you care about.

from buildfarm import data, util, history

import cgi
import os
import re
import time

# Show tracebacks on errors
import cgitb
cgitb.enable()

webdir = os.path.dirname(__file__)
basedir = os.path.abspath(os.path.join(webdir, ".."))

db = data.BuildfarmDatabase(basedir)
form = cgi.FieldStorage()
history = history.History(db)

compilers = db.compilers
hosts = db.hosts
trees = db.trees
OLDAGE = db.OLDAGE

# this is automatically filled in
deadhosts = []

def cgi_headers():
    """start CGI headers"""
    print "Content-Type: text/html\n"

    print "<html>"
    print "  <head>"
    print "    <title>samba.org build farm</title>"
    print "    <script language='javascript' src='/build_farm.js'/>"
    print "    <meta name='keywords' contents='Samba SMB CIFS Build Farm'/>"
    print "    <meta name='description' contents='Home of the Samba Build Farm, the automated testing facility.'/>"
    print "    <meta name='robots' contents='noindex'/>"
    print "    <link rel='stylesheet' href='/build_farm.css' type='text/css' media='all'/>"
    print "    <link rel='stylesheet' href='http://master.samba.org/samba/style/common.css' type='text/css' media='all'/>"
    print "    <link rel='shortcut icon' href='http://www.samba.org/samba/images/favicon.ico'/>"
    print "  </head>"
    print "<body>"

    print util.FileLoad(os.path.join(webdir, "header2.html"))
    main_menu()
    print util.FileLoad(os.path.join(webdir, "header3.html"))


def cgi_footers():
    """end CGI"""
    print util.FileLoad(os.path.join(webdir, "footer.html"))
    print "</body>"
    print "</html>"


def get_param(param):
    """get a param from the request, after sanitizing it"""
    if param not in form:
        return None

    result = [s.replace(" ", "_") for s in form.getlist(param)]

    for entry in result:
        if re.match("[^a-zA-Z0-9\-\_\.]", entry):
            raise Exception("Parameter %s is invalid" % param)

    return result[0]


def build_link(host, tree, compiler, rev, status):
    if rev:
        opt_rev = ';revision=%s' % rev
    else:
        opt_rev = ''
    return "<a href='%s?function=View+Build;host=%s;tree=%s;compiler=%s%s'>%s</a>" % (myself, host, tree, compiler, opt_rev, status)


def build_status(host, tree, compiler, rev):
    status = db.build_status(host, tree, compiler, rev)
    return build_link(host, tree, compiler, rev, status)


def host_age(host):
    """get the overall age of a host"""
    ret = -1
    for compiler in compilers:
        for tree in trees:
            age = db.build_age_mtime(host, tree, compiler, "")
            if age != -1 and (age < ret or ret == -1):
                ret = age
    return ret


def red_age(age):
    """show an age as a string"""
    if age > OLDAGE:
        return "<span clsas='old'>%s</span>" % util.dhm_time(age)
    return util.dhm_time(age)


def build_status_vals(status):
    """translate a status into a set of int representing status"""
    status = util.strip_html(status)

    status = status.replace("ok", "0")
    status = status.replace("?", "0")
    status = status.replace("PANIC", "1")

    return status.split("/")


def view_summary(output_type):
    """view build summary"""
    i = 0
    cols = 2
    broken = 0
    broken_count = {}
    panic_count = {}
    host_count = {}

    # zero broken and panic counters
    for tree in trees:
        broken_count[tree] = 0
        panic_count[tree] = 0
        host_count[tree] = 0

    # set up a variable to store the broken builds table's code, so we can
    # output when we want
    broken_table = ""
    last_host = ""

    # for the text report, include the current time
    if output_type == 'text':
        t = time.gmtime()
        print "Build status as of %s\n\n" % t

    for host in hosts:
        for compiler in compilers:
            for tree in trees:
                status = build_status(host, tree, compiler, "")
                if status.startswith("Unknown Build"):
                    continue
                age_mtime = db.build_age_mtime(host, tree, compiler, "")

                if age_mtime != -1:
                    host_count[tree]+=1

                if "status failed" in status:
                    broken_count[tree]+=1
                    if "PANIC" in status:
                        panic_count[tree]+=1

    if output_type == 'text':
        print "Build counts:\n"
        print "%-12s %-6s %-6s %-6s\n" % ("Tree", "Total", "Broken", "Panic")
    else:
        print "<div id='build-counts' class='build-section'>"
        print "<h2>Build counts:</h2>"
        print "<table class='real'>"
        print "<thead><tr><th>Tree</th><th>Total</th><th>Broken</th><th>Panic</th><th>Test coverage</th></tr></thead>"
        print "<tbody>"

    for tree in sorted(trees.keys()):
        if output_type == 'text':
            print "%-12s %-6s %-6s %-6s\n" % (tree, host_count[tree],
                    broken_count[tree], panic_count[tree])
        else:
            print "<tr>"
            print "<td>%s</td>" % tree_link(tree)
            print "<td>%s</td>" % host_count[tree]
            print "<td>%s</td>" % broken_count[tree]
            if panic_count[tree]:
                    print "<td class='panic'>"
            else:
                    print "<td>"
            print panic_count[tree] + "</td>"
            print "<td>%s</td>" % db.lcov_status(tree)
            print "</tr>"

    if output_type == 'text':
        print "\n"
    else:
        print "</tbody></table>"
        print "</div>"


def revision_link(revision, tree):
    """return a link to a particular revision"""

    revision = revision.lstrip()
    if revision == "0":
        return "0"

    rev_short = revision
    if len(revision) == 40:
        rev_short = re.sub("(^.{7}).*", "\\1(git)", rev_short)

    return "<a href='%s?function=diff;tree=%s;revision=%s' title='View Diff for %s'>%s</a>" % (myself, tree, revision, revision, rev_short)


def tree_link(tree):
    # return a link to a particular tree
    branch = ""
    if tree in trees:
        branch = ":%s" % trees[tree]["branch"]

    return "<a href='%s?function=Recent+Builds;tree=%s' title='View recent builds for %s'>%s%s</a>" % (myself, tree, tree, tree, branch)


def view_recent_builds(tree, sort_by):
    """Draw the "recent builds" view"""
    i = 0
    cols = 2
    broken = 0
    last_host = ""
    all_builds = []

    def status_cmp(a, b):
        bstat = build_status_vals(b)
        astat = build_status_vals(a)

        # handle panic
        if len(bstat) > 4 and bstat[4]:
            return 1
        elif len(astat) > 4 and astat[4]:
            return -1

        return (cmp(astat[0], bstat[0]) or # configure
                cmp(astat[1], bstat[1]) or # compile
                cmp(astat[2], bstat[2]) or # install
                cmp(astat[3], bstat[3])) # test

    cmp_funcs = {
        "revision": lambda a, b: cmp(a[7], b[7]),
        "age": lambda a, b: cmp(a[0], b[0]),
        "host": lambda a, b: cmp(a[2], b[2]),
        "platform": lambda a, b: cmp(a[1], b[1]),
        "compiler": lambda a, b: cmp(a[3], b[3]),
        "status": lambda a, b: status_cmp(a[5], b[5]),
        }

    assert tree in trees, "not a build tree"
    assert sort_by in sort, "not a valid sort"

    t = trees[tree]

    for host in hosts:
        for compiler in compilers:
            status = build_status(host, tree, compiler, "")
            age_mtime = db.build_age_mtime(host, tree, compiler, "")
            age_ctime = db.build_age_ctime(host, tree, compiler, "")
            revision = db.build_revision(host, tree, compiler, "")
            revision_time = db.build_revision_time(host, tree, compiler, "")
            if age_mtime != -1:
                all_builds.append([age_ctime, hosts[host], "<a href='%s?function=View+Host;host=%s;tree=%s;compiler=%s#%s'>%s</a>" % (myself, host, tree, compiler, host, host), compiler, tree, status, revision_link(revision, tree), revision_time])

    all_builds.sort(cmp_funcs[sort_by])

    sorturl = "%s?tree=%s;function=Recent+Builds" % (myself, tree)

    print "<div id='recent-builds' class='build-section'>"
    print "<h2>Recent builds of %s (%s branch %s)</h2>" % (tree, t["scm"], t["branch"])
    print "<table class='real'>"
    print "<thead>"
    print "<tr>"
    print "<th><a href='%s;sortby=age' title='Sort by build age'>Age</a></th>" % sorturl
    print "<th><a href='%s;sortby=revision' title='Sort by build revision'>Revision</a></th>" % sorturl
    print "<th>Tree</th>"
    print "<th><a href='%s;sortby=platform' title='Sort by platform'>Platform</a></th>" % sorturl
    print "<th><a href='%s;sortby=host' title='Sort by host'>Host</a></th>" % sorturl
    print "<th><a href='%s;sortby=compiler' title='Sort by compiler'>Compiler</a></th>" % sorturl
    print "<th><a href='%s;sortby=status' title='Sort by status'>Status</a></th>" % sorturl
    print "<tbody>"

    for build in all_builds:
        print "<tr>"
        print "<td>%s</td>" % util.dhm_time(build[0])
        print "<td>%s</td>" % build[6]
        print "<td>%s</td>" % build[4]
        print "<td>%s</td>" % build[1]
        print "<td>%s</td>" % build[2]
        print "<td>%s</td>" % build[3]
        print "<td>%s</td>" % build[5]
        print "</tr>"
    print "</tbody></table>"
    print "</div>"


def draw_dead_hosts(output_type, *deadhosts):
    """Draw the "dead hosts" table"""

    # don't output anything if there are no dead hosts
    if len(deadhosts) == 0:
        return

    # don't include in text report
    if output_type == "text":
        return

    print "<div class='build-section' id='dead-hosts'>"
    print "<h2>Dead Hosts:</h2>"
    print "<table class='real'>"
    print "<thead><tr><th>Host</th><th>OS</th><th>Min Age</th></tr></thead>"
    print "<tbody>"

    for host in deadhosts:
        age_ctime = host_age(host)
        print "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (host, hosts[host], util.dhm_time(age_ctime))

    print "</tbody></table>"
    print "</div>"


def show_oldrevs(stree, host, compiler):
    """show the available old revisions, if any"""
    revs = db.get_old_revs(tree, host, compiler)

    if len(revs) == 0:
        return

    ret = "<h2>Older builds:</h2>"

    ret += "<table class='real'>"
    ret += "<thead><tr><th>Revision</th><th>Status</th></tr></thead>"
    ret += "<tbody>"

    lastrev = "" 
    for rev in revs:
        s = rev["STATUS"]
        revision = rev["REVISION"]
        s = s.replace(revision, "0")
        if s == lastrev:
            continue
        lastrev = s
        ret+= "<tr><td>%s</td><td>%s</td></tr>" % (revision_link(revision, tree), build_link(host, tree, compiler, rev["REVISION"], rev["STATUS"]))

    if lastrev != "":
        # Only print table if there was any actual data
        print ret + "</tbody></table>"


def view_build(tree, host, compiler, rev):
    """view one build in detail"""
    # ensure the params are valid before using them
    assert host in hosts, "unknown host"
    assert compiler in compilers, "unknown compiler"
    assert tree in trees, "not a build tree"

    uname = ""
    cflags = ""
    config = ""
    age_mtime = db.build_age_mtime(host, tree, compiler, rev)
    revision = db.build_revision(host, tree, compiler, rev)
    status = build_status(host, tree, compiler, rev)

    assert re.match("^[0-9a-fA-F]*$", rev)

    log = db.read_log(tree, host, compiler, rev)
    err = db.read_err(tree, host, compiler, rev)

    if log:
        log = cgi.escape(log)

        m = re.search("(.*)", log)
        if m:
            uname = m.group(1)
        m = re.search("CFLAGS=(.*)", log)
        if m:
            cflags = m.group(1)
        m = re.search("configure options: (.*)", log)
        if m:
            config = m.group(1)

    if err:
        err = cgi.escape(err)

    print '<h2>Host information:</h2>'

    print util.FileLoad("../web/%s.html" % host)

    print "<table clas='real'>"
    print "<tr><td>Host:</td><td><a href='%s?function=View+Host;host=%s;tree=%s;compiler=%s#'>%s</a> - %s</td></tr>" % (myself, host, tree, compiler, host, hosts[host])
    print "<tr><td>Uname:</td><td>%s</td></tr>" % uname
    print "<tr><td>Tree:</td><td>%s</td></tr>" % tree_link(tree)
    print "<tr><td>Build Revision:</td><td>%s</td></tr>" % revision_link(revision, tree)
    print "<tr><td>Build age:</td><td><div class='age'>%s</div></td></tr>" % red_age(age_mtime)
    print "<tr><td>Status:</td><td>%s</td></tr>" % status
    print "<tr><td>Compiler:</td><td>%s</td></tr>" % compiler
    print "<tr><td>CFLAGS:</td><td>%s</td></tr>" % flags
    print "<tr><td>configure options:</td><td>%s</td></tr>" % config

    show_oldrevs(tree, host, compiler)

    # check the head of the output for our magic string
    plain_logs = (get_param("plain") is not None and get_param("plain").lower() in ("yes", "1", "on", "true", "y"))
    rev_var = ""
    if rev:
        rev_var = ";revision=%s" % rev

    print "<div id='log'>"

    if not plain_logs:
        print "<p>Switch to the <a href='%s?function=View+Build;host=%s;tree=%s;compiler=%s%s;plain=true' title='Switch to bland, non-javascript, unstyled view'>Plain View</a></p>" % (myself, host, tree, compiler, rev_var)

        print "<div id='actionList'>"
        # These can be pretty wide -- perhaps we need to 
        # allow them to wrap in some way?
        if err == "":
            print "<h2>No error log available</h2>"
        else:
            print "<h2>Error log:</h2>"
            print make_collapsible_html('action', "Error Output", "\n%s" % err, "stderr-0")

        if log == "":
            print "<h2>No build log available</h2>"
        else:
            print "<h2>Build log:</h2>"
            print_log_pretty(log)

        print "<p><small>Some of the above icons derived from the <a href='http://www.gnome.org'>Gnome Project</a>'s stock icons.</small></p>"
        print "</div>"
    else:
        print "<p>Switch to the <a href='%s?function=View+Build;host=%s;tree=%s;compiler=%s%s' title='Switch to colourful, javascript-enabled, styled view'>Enhanced View</a></p>" % (myself, host, tree, compiler, rev_var)
        if err == "":
            print "<h2>No error log available</h2>"
        else:
            print '<h2>Error log:</h2>'
            print '<div id="errorLog"><pre>%s</pre></div>' % err
        if log == "":
            print '<h2>No build log available</h2>'
        else:
            print '<h2>Build log:</h2>'
            print '<div id="buildLog"><pre>%s</pre></div>' % log

    print '</div>'


def view_host(*requested_hosts):
    """print the host's table of information"""
    output_type = "html"

    if output_type == 'text':
        print "Host summary:\n"
    else:
        print "<div class='build-section' id='build-summary'>"
        print '<h2>Host summary:</h2>'

    for host in requested_hosts:
        assert host in hosts, "unknown host"

    for host in requested_hosts:
        # make sure we have some data from it
        if not db.has_host(host):
            if output_type == 'text':
                print "<!-- skipping %s -->" % host
            continue

        row = 0

        for compiler in compilers:
            for tree in sorted(trees.keys()):
                revision = db.build_revision(host, tree, compiler, "")
                age_mtime = db.build_age_mtime(host, tree, compiler, "")
                age_ctime = db.build_age_ctime(host, tree, compiler, "")
                warnings = db.err_count(host, tree, compiler, "")
                if age_ctime != -1:
                    status = build_status(host, tree, compiler, "")
                    if row == 0:
                        if output_type == 'text':
                            print "%-12s %-10s %-10s %-10s %-10s\n" % (
                                    "Tree", "Compiler", "Build Age", "Status", "Warnings")
                        else:
                            print "<div class='host summary'>"
                            print "<a id='host' name='host'/>"
                            print "<h3>%s - %s</h3>" % (host, hosts[host])
                            print "<table class='real'>"
                            print "<thead><tr><th>Target</th><th>Build<br/>Revision</th><th>Build<br />Age</th><th>Status<br />config/build<br />install/test</th><th>Warnings</th></tr></thead>"
                            print "<tbody>"

                    if output_type == 'text':
                        print "%-12s %-10s %-10s %-10s %-10s\n" % (
                                tree, compiler, util.dhm_time(age_mtime), 
                                util.strip_html(status), warnings)
                    else:
                        print "<tr>"
                        print "<td><span class='tree'>" + tree_link(tree) +"</span>/" + compiler + "</td>"
                        print "<td>" + revision_link(revision, tree) + "</td>"
                        print "<td><div class='age'>" + red_age(age_mtime) + "</div></td>"
                        print "<td><div class='status'>" + status + "</div></td>"
                        print "<td>%s</td>" % warnings
                        print "</tr>"
                    row+=1
        if row != 0:
            if output_type == 'text':
                print "\n"
            else:
                print "</tbody></table>"
                print "</div>"
        else:
            deadhosts.append(host)

    if output_type != 'text':
        print "</div>"

    draw_dead_hosts(output_type, *deadhosts)


def subunit_to_buildfarm_result(subunit_result):
    if subunit_result == "success":
        return "passed"
    elif subunit_result == "error":
        return "error"
    elif subunit_result == "skip":
        return "skipped"
    elif subunit_result == "failure":
        return "failed"
    elif subunit_result == "xfail":
        return "xfailed"
    else:
        return "unknown"

def format_subunit_reason(reason):
    reason = re.sub("^\[\n+(.*?)\n+\]$", "\\1", reason)

    return "<div class=\"reason\">%s</div>" % reason


def print_log_pretty(log):
    # prints the log in a visually appealing manner

    # do some pretty printing for the actions
    def pretty_print(m):
        output = m.group(1)
        actionName = m.group(2)
        status = m.group(3)
        # handle pretty-printing of static-analysis tools
        if actionName == 'cc_checker':
             output = print_log_cc_checker(output)

        id+=1
        make_collapsible_html('action', actionName, output, id, status)
        return output
    id = 1
    log = re.sub("(Running\ action\s+([\w\-]+) .*? ACTION\ (PASSED|FAILED):\ ([\w\-]+))",
                 pretty_print, log)

    # log is already CGI-escaped, so handle '>' in test name by handling &gt
    def format_stage(m):
        id += 1
        return make_collapsible_html('test', m.group(1), m.group(2), id, m.group(3))
    log = re.sub("""
          --==--==--==--==--==--==--==--==--==--==--.*?
          Running\ test\ ([\w\-=,_:\ /.&;]+).*?
          --==--==--==--==--==--==--==--==--==--==--
              (.*?)
          ==========================================.*?
          TEST\ (FAILED|PASSED|SKIPPED):.*?
          ==========================================\s+
        """, format_stage, log)

    def format_skip_testsuite(m):
        id += 1
        return make_collapsible_html('test', m.group(1), '', id, 'skipped'),

    log = re.sub("skip-testsuite: ([\w\-=,_:\ /.&; \(\)]+).*?",
            format_skip_testsuite, log)

    def format_testsuite(m):
        id += 1
        return make_collapsible_html('test', m.group(1), m.group(2)+format_subunit_reason(m.group(4)), id, subunit_to_buildfarm_result(m.group(3)))

    log = re.sub("""testsuite: ([\w\-=,_:\ /.&; \(\)\$]+).*?
          (.*?)
          testsuite-(.*?): [\w\-=,_:\ /.&; \(\)]+( \[.*?\])?.*?""",
          format_testsuite, log)

    def format_test(m):
        id += 1
        return make_collapsible_html('test', m.group(1), m.group(2)+format_subunit_reason(m.group(4)), id, subunit_to_buildfarm_result(m.group(3)))

    log = re.sub("""
          ^test: ([\w\-=,_:\ /.&; \(\)]+).*?
          (.*?)
          (success|xfail|failure|skip): [\w\-=,_:\ /.&; \(\)]+( \[.*?\])?.*?
       """, format_test, log)

    print "<pre>%s</pre>" % log


def print_log_cc_checker(input):
    # generate pretty-printed html for static analysis tools
    output = ""

    # for now, we only handle the IBM Checker's output style
    if not m.search("^BEAM_VERSION", input):
        return "here"
        return input

    content = ""
    inEntry = 0

    for line in input.splitlines():
        # for each line, check if the line is a new entry,
        # otherwise, store the line under the current entry.

        if line.startswith("-- "):
            # got a new entry
            if inEntry:
                output += make_collapsible_html('cc_checker', title, content, id, status)
            else:
                output += content

            # clear maintenance vars
            (inEntry, content) = (1, "")

            # parse the line
            m = re.match("^-- ((ERROR|WARNING|MISTAKE).*?)\s+&gt;&gt;&gt;([a-zA-Z0-9]+_(\w+)_[a-zA-Z0-9]+)", line)

            # then store the result
            (title, status, id) = ("%s %s" % (m.group(1), m.group(4)), m.group(2), m.group(3))
        elif line.startswith("CC_CHECKER STATUS"):
            if inEntry:
                output += make_collapsible_html('cc_checker', title, content, id, status)

            inEntry = 0
            content = ""

        # not a new entry, so part of the current entry's output
        content += "%s\n" % line

    output += content

    # This function does approximately the same as the following, following
    # commented-out regular expression except that the regex doesn't quite
    # handle IBM Checker's newlines quite right.
    #   $output =~ s{
    #                 --\ ((ERROR|WARNING|MISTAKE).*?)\s+
    #                        &gt;&gt;&gt
    #                 (.*?)
    #                 \n{3,}
    #               }{make_collapsible_html('cc_checker', "$1 $4", $5, $3, $2)}exgs
    return output


def make_collapsible_html(type, title, output, id, status=""):
    """generate html for a collapsible section

    :param type: the logical type of it. e.g. "test" or "action"
    :param title: the title to be displayed
    """

    if ((status == "" or "failed" in status.lower())):
        icon = 'icon_hide_16.png'
    else:
        icon = 'icon_unhide_16.png'

    # trim leading and trailing whitespace
    output = output.strip()

    # note that we may be inside a <pre>, so we don't put any extra whitespace
    # in this html
    ret = "<div class='%s unit %s' id='%s-%s'>" % (type, status, type, id)
    ret += "<a href=\"javascript:handle('%s');\">" % id
    ret += "<img id='img-%s' name='img-%s' alt='%s' src='%s'>" %(id, id, status, icon)
    ret += "<div class='%s title'>%s</div>" % (type, title)
    ret += " "
    ret += "<div class='%s status %s'>%s</div>" % (type, status, status)
    ret += "<div class='%s output' id='output-%s'><pre>%s</pre></div>" % (type, id, output)
    return ret

def main_menu():
    """main page"""

    print "<form action='GET'>"
    print "<div id='build-menu'>"
    print "<select name='host'>"
    for host in hosts:
        print "<option value='%s'>%s -- %s</option>" % (host, hosts[host], host)
    print "</select>"
    print "<select name='tree'>"
    for tree, t in trees.iteritems():
        print "<option value='%s'>%s:%s</option>" % (tree, tree, t["branch"])
    print "</select>"
    print "<select name='compiler'>"
    for compiler in compilers:
        print "<option>%s</option>" % compiler
    print "</select>"
    print "<br/>"
    print "<submit name='function' value='View Build'/>"
    print "<submit name='function' value='View Host'/>"
    print "<submit name='function' value='Recent Checkins'/>"
    print "<submit name='function' value='Summary'/>"
    print "<submit name='function' value='Recent Builds'/>"
    print "</div>"
    print "</form>"


def page_top():
    """display top of page"""
    cgi_headers()


def diff_pretty(diff):
    """pretty up a cvs diff -u"""
    ret = ""
    lines = diff.splitlines()

    line_types = {
            '^diff.*': 'diff_diff',
            '^=.*': 'diff_separator',
            '^Index:.*': 'diff_index',
            '^index.*': 'diff_index',
            '^\-.*': 'diff_removed',
            '^\+.*': 'diff_added',
            '^@@.*': 'diff_fragment_header'
            }

    for line in lines:
        for r in line_types.iterkeys():
            if r in line:
                line = "<span class=\"%s\">%s</span>" % (line_types[r], line)
                continue
        ret += line

    return ret


def web_paths(t, paths):
    """change the given source paths into links"""
    ret = ""

    fmt = None

    if t["scm"] == "cvs":
        fmt = " <a href=\"%s/%s/%%s\">%%s</a>" % (CVSWEB_BASE, t["repo"])
    elif t["scm"] == "svn":
        fmt = " <a href=\"%s/%s/%%s?root=%s\">%%s</a>" % (VIEWCVS_BASE, t["branch"], t["repo"])
    elif t["scm"] == "git":
        r = t["repo"]
        s = t["subdir"]
        b = t["branch"]
        fmt = " <a href=\"%s/?p=%s;a=history;f=%s%%s;h=%s;hb=%s\">%%s</a>" % (GITWEB_BASE, r, s, b, b)
    else:
        return paths

    for m in re.finditer("\s*([^\s]+)", paths):
        ret += fmt % (m.group(1), m.group(1))

    return ret


def history_row_html(entry, tree):
    """show one row of history table"""
    msg = cgi.escape(entry["MESSAGE"])
    t = time.asctime(time.gmtime(entry["DATE"]))
    age = util.dhm_time(time()-entry["DATE"])

    t = t.replace(" ", "&nbsp;")

    print """
<div class=\"history_row\">
    <div class=\"datetime\">
        <span class=\"date\">%s</span><br />
        <span class=\"age\">%s ago</span>""" % (t, age)
    if entry["REVISION"]:
        print " - <span class=\"revision\">%s</span><br/>" % entry["REVISION"]
        revision_url = "revision=%s" % entry["REVISION"]
    else:
        revision_url = "author=%s" % entry["AUTHOR"]
    print """    </div>
    <div class=\"diff\">
        <span class=\"html\"><a href=\"%s?function=diff;tree=%s;date=%s;%s\">show diffs</a></span>
    <br />
        <span class=\"text\"><a href=\"%s?function=text_diff;tree=%s;date=%s;%s\">download diffs</a></span>
        <br />
        <div class=\"history_log_message\">
            <pre>%s</pre>
        </div>
    </div>
    <div class=\"author\">
    <span class=\"label\">Author: </span>%s
    </div>""" % (myself, tree, entry["DATE"], revision_url,
                 myself, tree, entry["DATE"], revision_url,
                 msg, entry["AUTHOR"])

    t = db.trees.get(tree)

    if t is None:
        return paths

    if entry["FILES"]:
        print "<div class=\"files\"><span class=\"label\">Modified: </span>"
        print web_paths(t, entry["FILES"])
        print "</div>\n"

    if entry["ADDED"]:
        print "<div class=\"files\"><span class=\"label\">Added: </span>"
        print web_paths(t, entry["ADDED"])
        print "</div>\n"

    if entry["REMOVED"]:
        print "<div class=\"files\"><span class=\"label\">Removed: </span>"
        print web_paths(t, entry["REMOVED"])
        print "</div>\n"

    print "</div>\n"

def history_row_text(entry, tree):
    """show one row of history table"""
    msg = cgi.escape(entry["MESSAGE"])
    t = time.asctime(time.gmtime(entry["DATE"]))
    age = util.dhm_time(time()-entry["DATE"])

    print "Author: %s\n" % entry["AUTHOR"]
    if entry["REVISION"]:
        print "Revision: %s\n" % entry["REVISION"]
    print "Modified: %s\n" % entry["FILES"]
    print "Added: %s\n" % entry["ADDED"]
    print "Removed: %s\n" % entry["REMOVED"]
    print "\n\n%s\n\n\n" % msg


def show_diff(cmd, diff, text_html):
    if text_html == "html":
        print "<!-- %s -->\n" % cmd
        diff = cgi.escape(diff)
        diff = diff_pretty(diff)
        print "<pre>%s</pre>\n" % diff
    else:
        print "%s\n" % diff


###############################################
# main program

fn_name = get_param('function') or ''

if fn_name == 'text_diff':
    print header('application/x-diff')
    (title, entry, tree, diffs) = history.diff(get_param('author'),
          get_param('date'),
          get_param('tree'),
          get_param('revision'))
    history_row_text(entry, tree)
    for (cmd, diff) in diffs:
        show_diff(cmd, diff, "text")
elif fn_name == 'Text_Summary':
    print header('text/plain')
    view_summary('text')
else:
    page_top()

    if fn_name == "View_Build":
        view_build(get_param("tree"), get_param("host"), get_param("compiler"),
                   get_param('revision'))
    elif fn_name == "View_Host":
        view_host(get_param('host'))
    elif fn_name == "Recent_Builds":
        view_recent_builds(get_param("tree"), get_param("sortby") or "revision")
    elif fn_name == "Recent_Checkins":
        # validate the tree
        t = db.trees[tree]
        authors = set(["ALL"])
        authors.update(history.authors(tree))

        print "<h2>Recent checkins for %s (%s branch %s)</h2>\n" % (
            tree, t["scm"], t["branch"])
        print "<form action='GET'>"
        print "Select Author: "
        print "<select name='author'>"
        for name in sorted(authors):
            print "<option>%s</option>" % name
        print "</select>"
        print "<submit name='sub_function' value='Refresh'/>"
        print "<input type='hidden' name='tree' value='%s'/>" % tree
        print "<input type='hidden' name='function', value='Recent Checkins'/>"
        print "</form>"

        for entry, tree in history.history(get_param('tree'), get_param('author')):
            history_row_html(entry, tree)
        print "\n"
    elif fn_name == "diff":
        (title, entry, tree, diffs) = history.diff(get_param('author'),
                get_param('date'),
                get_param('tree'),
                get_param('revision'))
        print "<h2>%s</h2>" % title
        history_row_html(entry, tree)
        for (cmd, diff) in diffs:
            show_diff(cmd, diff, "html")
    elif os.getenv("PATH_INFO") not in (None, "", "/"):
        paths = os.getenv("PATH_INFO").split('/')
        if paths[1] == "recent":
            view_recent_builds(paths[2], get_param('sortby') or 'revision')
        elif paths[1] == "host":
            view_host(paths[2])
    else:
        view_summary('html')
    cgi_footers()
