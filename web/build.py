#!/usr/bin/python
# This CGI script presents the results of the build_farm build

# Copyright (C) Jelmer Vernooij <jelmer@samba.org>     2010
# Copyright (C) Matthieu Patou <mat@matws.net>         2010
#
# Based on the original web/build.pl:
#
# Copyright (C) Andrew Tridgell <tridge@samba.org>     2001-2005
# Copyright (C) Andrew Bartlett <abartlet@samba.org>   2001
# Copyright (C) Vance Lankhaar  <vance@samba.org>      2002-2005
# Copyright (C) Martin Pool <mbp@samba.org>            2001
# Copyright (C) Jelmer Vernooij <jelmer@samba.org>     2007
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

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from buildfarm import (
    CachingBuildFarm,
    data,
    hostdb,
    util,
    )

import cgi
import re
import time

import wsgiref.util
standalone = 0
webdir = os.path.dirname(__file__)
basedir = os.path.abspath(os.path.join(webdir, ".."))


UNPACKED_BASE = "http://svn.samba.org/ftp/unpacked"
GITWEB_BASE = "http://gitweb.samba.org"

# this is automatically filled in
deadhosts = []

def get_param(form, param):
    """get a param from the request, after sanitizing it"""
    if param not in form:
        return None

    result = [s.replace(" ", "_") for s in form.getlist(param)]

    for entry in result:
        if re.match("[^a-zA-Z0-9\-\_\.]", entry):
            raise Exception("Parameter %s is invalid" % param)

    return result[0]


def build_link(myself, tree, host, compiler, rev, status):
    if rev:
        opt_rev = ';revision=%s' % rev
    else:
        opt_rev = ''
    return "<a href='%s?function=View+Build;host=%s;tree=%s;compiler=%s%s'>%s</a>" % (
           myself, host, tree, compiler, opt_rev, status)


def html_build_status(status):
    def span(classname, contents):
        return "<span class=\"%s\">%s</span>" % (classname, contents)

    def span_status(stage):
        if stage.name == "CC_CHECKER":
            if stage.result == 0:
                return span("status checker", "ok")
            else:
                return span("status checker", stage.result)

        if stage.result is None:
            return span("status unknown", "?")
        elif stage.result == 0:
            return span("status passed", "ok")
        else:
            return span("status failed", stage.result)

    ostatus = ""
    if "panic" in status.other_failures:
        ostatus += "/"+span("status panic", "PANIC")
    if "disk full" in status.other_failures:
        ostatus += "/"+span("status failed", "disk full")
    if "timeout" in status.other_failures:
        ostatus += "/"+span("status failed", "timeout")
    if "inconsistent test result" in status.other_failures:
        ostatus += "/"+span("status failed", "unexpected return code")
    bstatus = "/".join([span_status(s) for s in status.stages])
    if bstatus == "":
        bstatus = "?"
    return bstatus + ostatus


def build_status_html(myself, build):
    rawstatus = build.status()
    status = html_build_status(rawstatus)
    return build_link(myself, build.tree, build.host, build.compiler, build.revision, status)


def build_status_vals(status):
    """translate a status into a set of int representing status"""
    status = util.strip_html(status)

    status = status.replace("ok", "0")
    status = status.replace("-", "0")
    status = status.replace("?", "0.1")
    status = status.replace("PANIC", "1")

    return status.split("/")


def revision_link(myself, revision, tree):
    """return a link to a particular revision"""

    revision = revision.lstrip()
    if revision == "0":
        return "0"

    rev_short = revision
    if len(revision) == 40:
        rev_short = re.sub("(^.{7}).*", "\\1(git)", rev_short)

    return "<a href='%s?function=diff;tree=%s;revision=%s' title='View Diff for %s'>%s</a>" % (myself, tree, revision, revision, rev_short)


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
    global indice
    indice = 0

    # do some pretty printing for the actions
    def pretty_print(m):
        global indice
        output = m.group(1)
        actionName = m.group(2)
        status = m.group(3)
        # handle pretty-printing of static-analysis tools
        if actionName == 'cc_checker':
             output = print_log_cc_checker(output)

        indice += 1
        return make_collapsible_html('action', actionName, output, indice, status)

    pattern = re.compile("(Running action\s+([\w\-]+)$(?:\s^.*$)*?\sACTION\ (PASSED|FAILED):\ ([\w\-]+)$)", re.M)
    log = pattern.sub(pretty_print, log)

    # log is already CGI-escaped, so handle '>' in test name by handling &gt
    def format_stage(m):
        indice += 1
        return make_collapsible_html('test', m.group(1), m.group(2), indice, m.group(3))

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
        global indice
        indice += 1
        return make_collapsible_html('test', m.group(1), '', indice, 'skipped')

    log = re.sub("skip-testsuite: ([\w\-=,_:\ /.&; \(\)]+).*?",
            format_skip_testsuite, log)

    def format_testsuite(m):
        global indice
        testName = m.group(1)
        content = m.group(2)
        status = subunit_to_buildfarm_result(m.group(3))
        if m.group(4):
            errorReason = format_subunit_reason(m.group(4))
        else:
            errorReason = ""
        indice += 1
        return make_collapsible_html('test', testName, content+errorReason, indice, status)

    pattern = re.compile("^testsuite: (.+)$\s((?:^.*$\s)*?)testsuite-(\w+): .*?(?:(\[$\s(?:^.*$\s)*?^\]$)|$)", re.M)
    log = pattern.sub(format_testsuite, log)

    def format_test(m):
        id += 1
        return make_collapsible_html('test', m.group(1), m.group(2)+format_subunit_reason(m.group(4)), id, subunit_to_buildfarm_result(m.group(3)))

    log = re.sub("""
          ^test: ([\w\-=,_:\ /.&; \(\)]+).*?
          (.*?)
          (success|xfail|failure|skip): [\w\-=,_:\ /.&; \(\)]+( \[.*?\])?.*?
       """, format_test, log)

    return "<pre>%s</pre>" % log


def print_log_cc_checker(input):
    # generate pretty-printed html for static analysis tools
    output = ""

    # for now, we only handle the IBM Checker's output style
    if not re.search("^BEAM_VERSION", input):
        return "here"
        return input

    content = ""
    inEntry = False
    title = None
    status = None

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
            (inEntry, content) = (True, "")

            # parse the line
            m = re.match("^-- ((ERROR|WARNING|MISTAKE).*?)\s+&gt;&gt;&gt;([a-zA-Z0-9]+_(\w+)_[a-zA-Z0-9]+)", line)

            # then store the result
            (title, status, id) = ("%s %s" % (m.group(1), m.group(4)), m.group(2), m.group(3))
        elif line.startswith("CC_CHECKER STATUS"):
            if inEntry:
                output += make_collapsible_html('cc_checker', title, content, id, status)

            inEntry = False
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
    if ((status == "" or "failed" == status.lower())):
        icon = 'icon_hide_16.png'
    else:
        icon = 'icon_unhide_16.png'

    # trim leading and trailing whitespace
    output = output.strip()

    # note that we may be inside a <pre>, so we don't put any extra whitespace
    # in this html
    ret = "<div class='%s unit %s' id='%s-%s'>" % (type, status, type, id)
    ret += "<a href=\"javascript:handle('%s');\">" % id
    ret += "<img id='img-%s' name='img-%s' alt='%s' src='%s' />" %(id, id, status, icon)
    ret += "<div class='%s title'>%s</div></a>" % (type, title)
    #ret += " "
    ret += "<div class='%s status %s'>%s</div>" % (type, status, status)
    ret += "<div class='%s output' id='output-%s'>" % (type, id)
    if output and len(output):
        ret += "<pre>%s</pre>>" % (output)
    ret += "</div></div>"
    return ret


def diff_pretty(diff):
    """pretty up a diff -u"""
    # FIXME: JRV 20101109 Use pygments for this
    ret = ""
    lines = diff.splitlines()

    line_types = {
            'diff': 'diff_diff',
            '=': 'diff_separator',
            'Index:': 'diff_index',
            'index': 'diff_index',
            '-': 'diff_removed',
            '+': 'diff_added',
            '@@': 'diff_fragment_header'
            }

    for line in lines:
        for r, cls in line_types.iteritems():
            if line.startswith(r):
                line = "<span class=\"%s\">%s</span>" % (cls, line)
                continue
        ret += line + "\n"

    return ret


def web_paths(t, paths):
    """change the given source paths into links"""
    if t.scm == "git":
        ret = ""
        for path in paths:
            ret += " <a href=\"%s/?p=%s;a=history;f=%s%s;h=%s;hb=%s\">%s</a>" % (GITWEB_BASE, t.repo, t.subdir, path, t.branch, t.branch, path)
        return ret
    else:
        raise Exception("Unknown scm %s" % t.scm)


def history_row_html(myself, entry, tree):
    """show one row of history table"""
    msg = cgi.escape(entry.message)
    t = time.asctime(time.gmtime(entry.date))
    age = util.dhm_time(time.time()-entry.date)

    t = t.replace(" ", "&nbsp;")

    yield """
<div class=\"history_row\">
    <div class=\"datetime\">
        <span class=\"date\">%s</span><br />
        <span class=\"age\">%s ago</span>""" % (t, age)
    if entry.revision:
        yield " - <span class=\"revision\">%s</span><br/>" % entry.revision
        revision_url = "revision=%s" % entry.revision
    else:
        revision_url = "author=%s" % entry.author
    yield """    </div>
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
    </div>""" % (myself, tree.name, entry.date, revision_url,
                 myself, tree.name, entry.date, revision_url,
                 msg, entry.author)

    if entry.modified:
        yield "<div class=\"files\"><span class=\"label\">Modified: </span>"
        yield web_paths(tree, entry.modified)
        yield "</div>\n"

    if entry.added:
        yield "<div class=\"files\"><span class=\"label\">Added: </span>"
        yield web_paths(tree, entry.added)
        yield "</div>\n"

    if entry.removed:
        yield "<div class=\"files\"><span class=\"label\">Removed: </span>"
        yield web_paths(tree, entry.removed)
        yield "</div>\n"

    yield "</div>\n"


def history_row_text(entry, tree):
    """show one row of history table"""
    msg = cgi.escape(entry.message)
    t = time.asctime(time.gmtime(entry.date))
    age = util.dhm_time(time.time()-entry.date)

    yield "Author: %s\n" % entry.author
    if entry.revision:
        yield "Revision: %s\n" % entry.revision
    yield "Modified: %s\n" % entry.modified
    yield "Added: %s\n" % entry.added
    yield "Removed: %s\n" % entry.removed
    yield "\n\n%s\n\n\n" % msg


def show_diff(diff, text_html):
    if text_html == "html":
        diff = cgi.escape(diff)
        diff = diff_pretty(diff)
        return "<pre>%s</pre>\n" % diff
    else:
        return "%s\n" % diff


class BuildFarmPage(object):

    def __init__(self, buildfarm):
        self.buildfarm = buildfarm

    def red_age(self, age):
        """show an age as a string"""
        if age > self.buildfarm.OLDAGE:
            return "<span clsas='old'>%s</span>" % util.dhm_time(age)
        return util.dhm_time(age)

    def tree_link(self, myself, tree):
        # return a link to a particular tree
        branch = ""
        if tree in self.buildfarm.trees:
            branch = ":%s" % self.buildfarm.trees[tree].branch

        return "<a href='%s?function=Recent+Builds;tree=%s' title='View recent builds for %s'>%s%s</a>" % (myself, tree, tree, tree, branch)

    def render(self, output_type):
        raise NotImplementedError(self.render)


class ViewBuildPage(BuildFarmPage):

    def show_oldrevs(self, myself, tree, host, compiler):
        """show the available old revisions, if any"""
        revs = self.buildfarm.builds.get_old_revs(tree, host, compiler)

        if len(revs) == 0:
            return

        yield "<h2>Older builds:</h2>"

        yield "<table class='real'>"
        yield "<thead><tr><th>Revision</th><th>Status</th></tr></thead>"
        yield "<tbody>"

        lastrev = ""
        for rev in revs:
            s = html_build_status(rev["STATUS"])
            revision = rev["REVISION"]
            s = s.replace(revision, "0")
            if s == lastrev:
                continue
            lastrev = s
            yield "<tr><td>%s</td><td>%s</td></tr>" % (revision_link(myself, revision, tree), build_link(myself, tree, host, compiler, rev["REVISION"], html_build_status(rev["STATUS"])))

        if lastrev != "":
            # Only print table if there was any actual data
            yield "</tbody></table>"

    def render(self, myself, tree, host, compiler, rev, plain_logs=False):
        """view one build in detail"""
        # ensure the params are valid before using them
        #assert host in self.buildfarm.hostdb, "unknown host %s" % host
        assert compiler in self.buildfarm.compilers, "unknown compiler %s" % compiler
        assert tree in self.buildfarm.trees, "not a build tree %s" % tree

        uname = ""
        cflags = ""
        config = ""
        build = buildfarm.get_build(tree, host, compiler, rev)
        age_mtime = build.age_mtime()
        (revision, revision_time) = build.revision_details()
        status = build_status_html(myself, build)

        if rev:
            assert re.match("^[0-9a-fA-F]*$", rev)

        f = build.read_log()
        try:
            log = f.read()
        finally:
            f.close()
        f = build.read_err()
        try:
            err = f.read()
        finally:
            f.close()

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
        yield '<h2>Host information:</h2>'

        host_web_file = "../web/%s.html" % host
        if os.path.exists(host_web_file):
            yield util.FileLoad(host_web_file)

        yield "<table class='real'>\n"
        yield "<tr><td>Host:</td><td><a href='%s?function=View+Host;host=%s;tree=%s;"\
              "compiler=%s#'>%s</a> - %s</td></tr>\n" %\
                (myself, host, tree, compiler, host, self.buildfarm.hostdb.host(host).platform.encode("utf-8"))
        yield "<tr><td>Uname:</td><td>%s</td></tr>\n" % uname
        yield "<tr><td>Tree:</td><td>%s</td></tr>\n" % self.tree_link(myself, tree)
        yield "<tr><td>Build Revision:</td><td>%s</td></tr>\n" % revision_link(myself, revision, tree)
        yield "<tr><td>Build age:</td><td><div class='age'>%s</div></td></tr>\n" % self.red_age(age_mtime)
        yield "<tr><td>Status:</td><td>%s</td></tr>\n" % status
        yield "<tr><td>Compiler:</td><td>%s</td></tr>\n" % compiler
        yield "<tr><td>CFLAGS:</td><td>%s</td></tr>\n" % cflags
        yield "<tr><td>configure options:</td><td>%s</td></tr>\n" % config
        yield "</table>\n"

        yield "".join(self.show_oldrevs(myself, tree, host, compiler))

        # check the head of the output for our magic string
        rev_var = ""
        if rev:
            rev_var = ";revision=%s" % rev

        yield "<div id='log'>"

        if not plain_logs:
            yield "<p>Switch to the <a href='%s?function=View+Build;host=%s;tree=%s"\
                  ";compiler=%s%s;plain=true' title='Switch to bland, non-javascript,"\
                  " unstyled view'>Plain View</a></p>" % (myself, host, tree, compiler, rev_var)

            yield "<div id='actionList'>"
            # These can be pretty wide -- perhaps we need to
            # allow them to wrap in some way?
            if err == "":
                yield "<h2>No error log available</h2>\n"
            else:
                yield "<h2>Error log:</h2>"
                yield make_collapsible_html('action', "Error Output", "\n%s" % err, "stderr-0", "errorlog")

            if log == "":
                yield "<h2>No build log available</h2>"
            else:
                yield "<h2>Build log:</h2>\n"
                yield print_log_pretty(log)

            yield "<p><small>Some of the above icons derived from the <a href='http://www.gnome.org'>Gnome Project</a>'s stock icons.</small></p>"
            yield "</div>"
        else:
            yield "<p>Switch to the <a href='%s?function=View+Build;host=%s;tree=%s;"\
                  "compiler=%s%s' title='Switch to colourful, javascript-enabled, styled"\
                  " view'>Enhanced View</a></p>" % (myself, host, tree, compiler, rev_var)
            if err == "":
                yield "<h2>No error log available</h2>"
            else:
                yield '<h2>Error log:</h2>\n'
                yield '<div id="errorLog"><pre>%s</pre></div>' % err
            if log == "":
                yield '<h2>No build log available</h2>'
            else:
                yield '<h2>Build log:</h2>\n'
                yield '<div id="buildLog"><pre>%s</pre></div>' % log

        yield '</div>'


class ViewRecentBuildsPage(BuildFarmPage):

    def render(self, myself, tree, sort_by):
        """Draw the "recent builds" view"""
        i = 0
        cols = 2
        broken = 0
        last_host = ""
        all_builds = []

        cmp_funcs = {
            "revision": lambda a, b: cmp(a[7], b[7]),
            "age": lambda a, b: cmp(a[0], b[0]),
            "host": lambda a, b: cmp(a[2], b[2]),
            "platform": lambda a, b: cmp(a[1], b[1]),
            "compiler": lambda a, b: cmp(a[3], b[3]),
            "status": lambda a, b: cmp(a[6], b[6]),
            }

        assert tree in self.buildfarm.trees, "not a build tree"
        assert sort_by in cmp_funcs, "not a valid sort"

        t = self.buildfarm.trees[tree]

        for host in self.buildfarm.hostdb.hosts():
            for compiler in self.buildfarm.compilers:
                try:
                    build = buildfarm.get_build(tree, host.name.encode("utf-8"), compiler)
                    status = build_status_html(myself, build)
                except data.NoSuchBuildError:
                    pass
                else:
                    age_mtime = build.age_mtime()
                    age_ctime = build.age_ctime()
                    (revision, revision_time) = build.revision_details()
                    if revision:
                        all_builds.append([
                            age_ctime,
                            host.platform.encode("utf-8"),
                            "<a href='%s?function=View+Host;host=%s;tree=%s;compiler=%s#%s'>%s</a>"
                                % (myself, host.name.encode("utf-8"),
                                   tree, compiler, host.name.encode("utf-8"),
                                   host.name.encode("utf-8")),
                            compiler, tree, status, build.status(),
                            revision_link(myself, revision, tree),
                            revision_time])

        all_builds.sort(cmp_funcs[sort_by])

        sorturl = "%s?tree=%s;function=Recent+Builds" % (myself, tree)

        yield "<div id='recent-builds' class='build-section'>"
        yield "<h2>Recent builds of %s (%s branch %s)</h2>" % (tree, t.scm, t.branch)
        yield "<table class='real'>"
        yield "<thead>"
        yield "<tr>"
        yield "<th><a href='%s;sortby=age' title='Sort by build age'>Age</a></th>" % sorturl
        yield "<th><a href='%s;sortby=revision' title='Sort by build revision'>Revision</a></th>" % sorturl
        yield "<th>Tree</th>"
        yield "<th><a href='%s;sortby=platform' title='Sort by platform'>Platform</a></th>" % sorturl
        yield "<th><a href='%s;sortby=host' title='Sort by host'>Host</a></th>" % sorturl
        yield "<th><a href='%s;sortby=compiler' title='Sort by compiler'>Compiler</a></th>" % sorturl
        yield "<th><a href='%s;sortby=status' title='Sort by status'>Status</a></th>" % sorturl
        yield "<tbody>"

        for build in all_builds:
            yield "<tr>"
            yield "<td>%s</td>" % util.dhm_time(build[0])
            yield "<td>%s</td>" % build[7]
            yield "<td>%s</td>" % build[4]
            yield "<td>%s</td>" % build[1]
            yield "<td>%s</td>" % build[2]
            yield "<td>%s</td>" % build[3]
            yield "<td>%s</td>" % build[5]
            yield "</tr>"
        yield "</tbody></table>"
        yield "</div>"


class ViewHostPage(BuildFarmPage):

    def render(self, myself, output_type, *requested_hosts):
        """print the host's table of information"""

        if output_type == 'text':
            yield "Host summary:\n"
        else:
            yield "<div class='build-section' id='build-summary'>"
            yield '<h2>Host summary:</h2>'

        for host in requested_hosts:
            # make sure we have some data from it
            try:
                self.buildfarm.hostdb.host(host)
            except hostdb.NoSuchHost:
                continue

            row = 0

            for compiler in self.buildfarm.compilers:
                for tree in sorted(self.buildfarm.trees.keys()):
                    try:
                        build = buildfarm.get_build(tree, host, compiler)
                    except data.NoSuchBuildError:
                        pass
                    else:
                        (revision, revision_time) = build.revision_details()
                        age_mtime = build.age_mtime()
                        age_ctime = build.age_ctime()
                        warnings = build.err_count()
                        status = build_status_html(myself, build)
                        if row == 0:
                            if output_type == 'text':
                                yield "%-12s %-10s %-10s %-10s %-10s\n" % (
                                        "Tree", "Compiler", "Build Age", "Status", "Warnings")
                            else:
                                yield "<div class='host summary'>"
                                yield "<a id='host' name='host'/>"
                                yield "<h3>%s - %s</h3>" % (host, self.buildfarm.hostdb.host(host).platform.encode("utf-8"))
                                yield "<table class='real'>"
                                yield "<thead><tr><th>Target</th><th>Build<br/>Revision</th><th>Build<br />Age</th><th>Status<br />config/build<br />install/test</th><th>Warnings</th></tr></thead>"
                                yield "<tbody>"

                        if output_type == 'text':
                            yield "%-12s %-10s %-10s %-10s %-10s\n" % (
                                    tree, compiler, util.dhm_time(age_mtime),
                                    util.strip_html(status), warnings)
                        else:
                            yield "<tr>"
                            yield "<td><span class='tree'>" + self.tree_link(myself, tree) +"</span>/" + compiler + "</td>"
                            yield "<td>" + revision_link(myself, revision, tree) + "</td>"
                            yield "<td><div class='age'>" + self.red_age(age_mtime) + "</div></td>"
                            yield "<td><div class='status'>%s</div></td>" % status
                            yield "<td>%s</td>" % warnings
                            yield "</tr>"
                        row+=1
            if row != 0:
                if output_type == 'text':
                    yield "\n"
                else:
                    yield "</tbody></table>"
                    yield "</div>"
            else:
                deadhosts.append(host)

        if output_type != 'text':
            yield "</div>"
            yield "".join(self.draw_dead_hosts(*deadhosts))

    def draw_dead_hosts(self, *deadhosts):
        """Draw the "dead hosts" table"""

        # don't output anything if there are no dead hosts
        if len(deadhosts) == 0:
            return

        yield "<div class='build-section' id='dead-hosts'>"
        yield "<h2>Dead Hosts:</h2>"
        yield "<table class='real'>"
        yield "<thead><tr><th>Host</th><th>OS</th><th>Min Age</th></tr></thead>"
        yield "<tbody>"

        for host in deadhosts:
            age_ctime = self.buildfarm.hostdb.host_age(host)
            yield "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" %\
                    (host, self.buildfarm.hostdb.host(host).platform.encode("utf-8"),
                     util.dhm_time(age_ctime))

        yield "</tbody></table>"
        yield "</div>"


class ViewSummaryPage(BuildFarmPage):

    def render(self, myself, output_type):
        """view build summary"""
        i = 0
        cols = 2
        broken = 0
        broken_count = {}
        panic_count = {}
        host_count = {}

        # zero broken and panic counters
        for tree in self.buildfarm.trees:
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
            yield "Build status as of %s\n\n" % t

        for host in self.buildfarm.hostdb.hosts():
            for compiler in self.buildfarm.compilers:
                for tree in self.buildfarm.trees:
                    try:
                        build = buildfarm.get_build(tree, host.name.encode("utf-8"), compiler)
                        status = build_status_html(myself, build)
                    except data.NoSuchBuildError:
                        continue
                    age_mtime = build.age_mtime()
                    host_count[tree]+=1

                    if "status failed" in status:
                        broken_count[tree]+=1
                        if "PANIC" in status:
                            panic_count[tree]+=1

        if output_type == 'text':
            yield "Build counts:\n"
            yield "%-12s %-6s %-6s %-6s\n" % ("Tree", "Total", "Broken", "Panic")
        else:
            yield "<div id='build-counts' class='build-section'>"
            yield "<h2>Build counts:</h2>"
            yield "<table class='real'>"
            yield "<thead><tr><th>Tree</th><th>Total</th><th>Broken</th><th>Panic</th><th>Test coverage</th></tr></thead>"
            yield "<tbody>"

        for tree in sorted(self.buildfarm.trees.keys()):
            if output_type == 'text':
                yield "%-12s %-6s %-6s %-6s\n" % (tree, host_count[tree],
                        broken_count[tree], panic_count[tree])
            else:
                yield "<tr>"
                yield "<td>%s</td>" % self.tree_link(myself, tree)
                yield "<td>%s</td>" % host_count[tree]
                yield "<td>%s</td>" % broken_count[tree]
                if panic_count[tree]:
                        yield "<td class='panic'>"
                else:
                        yield "<td>"
                yield "%d</td>" % panic_count[tree]
                try:
                    lcov_status = buildfarm.lcov_status(tree)
                except data.NoSuchBuildError:
                    yield "<td></td>"
                else:
                    if lcov_status is not None:
                        yield "<td><a href=\"/lcov/data/%s/%s\">%s %%</a></td>" % (buildfarm.LCOVHOST, tree, lcov_status)
                    else:
                        yield "<td></td>"
                yield "</tr>"

        if output_type == 'text':
            yield "\n"
        else:
            yield "</tbody></table>"
            yield "</div>"


class DiffPage(BuildFarmPage):

    def render(self, myself, tree, revision):
        t = self.buildfarm.trees[tree]
        (entry, diff) = t.get_branch().diff(revision)
        # get information about the current diff
        title = "GIT Diff in %s:%s for revision %s" % (
            tree, t.branch, revision)
        yield "<h2>%s</h2>" % title
        yield "".join(history_row_html(myself, entry, t))
        yield show_diff(diff, "html")


class RecentCheckinsPage(BuildFarmPage):

    def render(self, myself, tree, author=None):
        t = self.buildfarm.trees[tree]
        authors = set(["ALL"])
        authors.update(t.get_branch().authors(tree))

        yield "<h2>Recent checkins for %s (%s branch %s)</h2>\n" % (
            tree, t.scm, t.branch)
        yield "<form method='GET'>"
        yield "Select Author: "
        yield "<select name='author'>"
        for name in sorted(authors):
            yield "<option>%s</option>" % name
        yield "</select>"
        yield "<input type='submit' name='sub_function' value='Refresh'/>"
        yield "<input type='hidden' name='tree' value='%s'/>" % tree
        yield "<input type='hidden' name='function', value='Recent Checkins'/>"
        yield "</form>"

        branch = t.get_branch()

        for entry in branch.log():
            if author in ("ALL", "", entry.author):
                yield "".join(history_row_html(myself, entry, t))
        yield "\n"



class BuildFarmApp(object):

    def __init__(self, buildfarm):
        self.buildfarm = buildfarm
        self.db = data.BuildResultStore(basedir)
        self.hostsdb = buildfarm.hostdb

        self.compilers = buildfarm.compilers
        # host.properties are unicode object and the framework expect string object
        self.hosts = dict([(host.name.encode("utf-8"), host) for host in self.hostsdb.hosts()])

    def main_menu(self):
        """main page"""

        yield "<form method='GET'>"
        yield "<div id='build-menu'>"
        yield "<select name='host'>"
        for name, host in self.hosts.iteritems():
            yield "<option value='%s'>%s -- %s</option>\n" % (name, host.platform.encode("utf-8"), name)
        yield "</select>"
        yield "<select name='tree'>"
        for tree, t in self.buildfarm.trees.iteritems():
            yield "<option value='%s'>%s:%s</option>\n" % (tree, tree, t.branch)
        yield "</select>"
        yield "<select name='compiler'>"
        for compiler in self.buildfarm.compilers:
            yield "<option>%s</option>\n" % compiler
        yield "</select>"
        yield "<br/>"
        yield "<input type='submit' name='function' value='View Build'/>"
        yield "<input type='submit' name='function' value='View Host'/>"
        yield "<input type='submit' name='function' value='Recent Checkins'/>"
        yield "<input type='submit' name='function' value='Summary'/>"
        yield "<input type='submit' name='function' value='Recent Builds'/>"
        yield "</div>"
        yield "</form>"

    def __call__(self, environ, start_response):
        form = cgi.FieldStorage(fp=environ['wsgi.input'], environ=environ)
        fn_name = get_param(form, 'function') or ''
        myself = wsgiref.util.application_uri(environ)

        if standalone and environ['PATH_INFO']:
            dir = os.path.join(os.path.dirname(__file__))
            if re.match("^/[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)?", environ['PATH_INFO']):
                static_file = "%s/%s" % (dir, environ['PATH_INFO'])
                if os.path.exists(static_file):
                    tab = environ['PATH_INFO'].split('.')
                    if len(tab) > 1:
                        extension = tab[-1]
                        import mimetypes
                        mimetypes.init()
                        type = mimetypes.types_map[".%s" % extension]
                        start_response('200 OK', [('Content-type', type)])
                        data = open(static_file, 'rb').read()
                        yield data
                        return

        if fn_name == 'text_diff':
            start_response('200 OK', [('Content-type', 'application/x-diff')])
            tree = get_param(form, 'tree')
            t = self.buildfarm.trees[tree]
            (entry, diff) = t.get_branch().diff(get_param(form, 'revision'))
            yield "".join(history_row_text(entry, tree))
            yield show_diff(diff, "text")
        elif fn_name == 'Text_Summary':
            start_response('200 OK', [('Content-type', 'text/plain')])
            page = ViewSummaryPage(self.buildfarm)
            yield "".join(page.render(myself, 'text'))
        else:
            start_response('200 OK', [('Content-type', 'text/html')])

            yield "<html>"
            yield "  <head>"
            yield "    <title>samba.org build farm</title>"
            yield "    <script language='javascript' src='/build_farm.js'></script>"
            yield "    <meta name='keywords' contents='Samba SMB CIFS Build Farm'/>"
            yield "    <meta name='description' contents='Home of the Samba Build Farm, the automated testing facility.'/>"
            yield "    <meta name='robots' contents='noindex'/>"
            yield "    <link rel='stylesheet' href='/build_farm.css' type='text/css' media='all'/>"
            if standalone:
                yield "    <link rel='stylesheet' href='common.css' type='text/css' media='all'/>"
            else:
                yield "    <link rel='stylesheet' href='http://master.samba.org/samba/style/common.css' type='text/css' media='all'/>"
            yield "    <link rel='shortcut icon' href='http://www.samba.org/samba/images/favicon.ico'/>"
            yield "  </head>"
            yield "<body>"

            yield util.FileLoad(os.path.join(webdir, "header2.html"))
            yield "".join(self.main_menu())
            yield util.FileLoad(os.path.join(webdir, "header3.html"))
            if fn_name == "View_Build":
                plain_logs = (get_param(form, "plain") is not None and get_param(form, "plain").lower() in ("yes", "1", "on", "true", "y"))
                tree = get_param(form, "tree")
                host = get_param(form, "host")
                compiler = get_param(form, "compiler")
                page = ViewBuildPage(self.buildfarm)
                yield "".join(page.render(myself, tree, host, compiler, get_param(form, "revision"), plain_logs))
            elif fn_name == "View_Host":
                page = ViewHostPage(self.buildfarm)
                yield "".join(page.render(myself, "html", get_param(form, 'host')))
            elif fn_name == "Recent_Builds":
                page = ViewRecentBuildsPage(self.buildfarm)
                yield "".join(page.render(myself, get_param(form, "tree"), get_param(form, "sortby") or "revision"))
            elif fn_name == "Recent_Checkins":
                # validate the tree
                tree =  get_param(form, "tree")
                author = get_param(form, 'author')
                page = RecentCheckinsPage(self.buildfarm)
                yield "".join(page.render(myself, tree, author))
            elif fn_name == "diff":
                tree =  get_param(form, "tree")
                revision = get_param(form, 'revision')
                page = DiffPage(self.buildfarm)
                yield "".join(page.render(myself, tree, revision))
            elif os.getenv("PATH_INFO") not in (None, "", "/"):
                paths = os.getenv("PATH_INFO").split('/')
                if paths[1] == "recent":
                    page = ViewRecentBuildsPage(self.buildfarm)
                    yield "".join(page.render(myself, paths[2], get_param(form, 'sortby') or 'revision'))
                elif paths[1] == "host":
                    page = ViewHostPage(self.buildfarm)
                    yield "".join(page.render(myself, "html", paths[2]))
            else:
                page = ViewSummaryPage(self.buildfarm)
                yield "".join(page.render(myself, 'html'))
            yield util.FileLoad(os.path.join(webdir, "footer.html"))
            yield "</body>"
            yield "</html>"


if __name__ == '__main__':
    import optparse
    parser = optparse.OptionParser("[options]")
    parser.add_option("--standalone", help="Run as standalone server (useful for debugging)", action="store_true")
    parser.add_option("--cachedirname", help="Cache directory name", type=str)
    opts, args = parser.parse_args()
    buildfarm = CachingBuildFarm(cachedirname=opts.cachedirname)
    buildApp = BuildFarmApp(buildfarm)
    if opts.standalone:
        standalone = 1
        from wsgiref.simple_server import make_server
        httpd = make_server('localhost', 8000, buildApp)
        print "Serving on port 8000..."
        httpd.serve_forever()
    else:
        import wsgiref.handlers
        handler = wsgiref.handlers.CGIHandler()
        handler.run(buildApp)
