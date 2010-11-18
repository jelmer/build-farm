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
# Copyright (C) Jelmer Vernooij <jelmer@samba.org>     2007-2009
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

"""Buildfarm web frontend."""

# TODO: Allow filtering of the "Recent builds" list to show
# e.g. only broken builds or only builds that you care about.

from collections import defaultdict
import os

from buildfarm import (
    data,
    hostdb,
    util,
    )
from buildfarm.filecache import (
    CachingBuildFarm,
    )

import cgi
from pygments import highlight
from pygments.lexers.text import DiffLexer
from pygments.formatters import HtmlFormatter
import re
import time

import wsgiref.util
webdir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "web"))

GITWEB_BASE = "http://gitweb.samba.org"
HISTORY_HORIZON = 1000

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
    status = html_build_status(build.status())
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

    if revision is None:
        return "unknown"

    revision = revision.lstrip()
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


class LogPrettyPrinter(object):

    def __init__(self):
        self.indice = 0

    def _pretty_print(self, m):
        output = m.group(1)
        actionName = m.group(2)
        status = m.group(3)
        # handle pretty-printing of static-analysis tools
        if actionName == 'cc_checker':
             output = "".join(print_log_cc_checker(output))

        self.indice += 1
        return "".join(make_collapsible_html('action', actionName, output, self.indice, status))

    # log is already CGI-escaped, so handle '>' in test name by handling &gt
    def _format_stage(self, m):
        self.indice += 1
        return "".join(make_collapsible_html('test', m.group(1), m.group(2), self.indice, m.group(3)))

    def _format_skip_testsuite(self, m):
        self.indice += 1
        return "".join(make_collapsible_html('test', m.group(1), '', self.indice, 'skipped'))

    def _format_testsuite(self, m):
        testName = m.group(1)
        content = m.group(2)
        status = subunit_to_buildfarm_result(m.group(3))
        if m.group(4):
            errorReason = format_subunit_reason(m.group(4))
        else:
            errorReason = ""
        self.indice += 1
        return "".join(make_collapsible_html('test', testName, content+errorReason, self.indice, status))

    def _format_test(self, m):
        self.indice += 1
        return "".join(make_collapsible_html('test', m.group(1), m.group(2)+format_subunit_reason(m.group(4)), self.indice, subunit_to_buildfarm_result(m.group(3))))

    def pretty_print(self, log):
        # do some pretty printing for the actions
        pattern = re.compile("(Running action\s+([\w\-]+)$(?:\s^.*$)*?\sACTION\ (PASSED|FAILED):\ ([\w\-]+)$)", re.M)
        log = pattern.sub(self._pretty_print, log)

        log = re.sub("""
              --==--==--==--==--==--==--==--==--==--==--.*?
              Running\ test\ ([\w\-=,_:\ /.&;]+).*?
              --==--==--==--==--==--==--==--==--==--==--
                  (.*?)
              ==========================================.*?
              TEST\ (FAILED|PASSED|SKIPPED):.*?
              ==========================================\s+
            """, self._format_stage, log)

        log = re.sub("skip-testsuite: ([\w\-=,_:\ /.&; \(\)]+).*?",
                self._format_skip_testsuite, log)

        pattern = re.compile("^testsuite: (.+)$\s((?:^.*$\s)*?)testsuite-(\w+): .*?(?:(\[$\s(?:^.*$\s)*?^\]$)|$)", re.M)
        log = pattern.sub(self._format_testsuite, log)
        log = re.sub("""
              ^test: ([\w\-=,_:\ /.&; \(\)]+).*?
              (.*?)
              (success|xfail|failure|skip): [\w\-=,_:\ /.&; \(\)]+( \[.*?\])?.*?
           """, self._format_test, log)

        return "<pre>%s</pre>" % log


def print_log_pretty(log):
    return LogPrettyPrinter().pretty_print(log)


def print_log_cc_checker(input):
    # generate pretty-printed html for static analysis tools
    # for now, we only handle the IBM Checker's output style
    if not re.search("^BEAM_VERSION", input):
        yield "here"
        # yield input
        return

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
                yield "".join(make_collapsible_html('cc_checker', title, content, id, status))
            else:
                yield content

            # clear maintenance vars
            (inEntry, content) = (True, "")

            # parse the line
            m = re.match("^-- ((ERROR|WARNING|MISTAKE).*?)\s+&gt;&gt;&gt;([a-zA-Z0-9]+_(\w+)_[a-zA-Z0-9]+)", line)

            # then store the result
            (title, status, id) = ("%s %s" % (m.group(1), m.group(4)), m.group(2), m.group(3))
        elif line.startswith("CC_CHECKER STATUS"):
            if inEntry:
                yield "".join(make_collapsible_html('cc_checker', title, content, id, status))

            inEntry = False
            content = ""

        # not a new entry, so part of the current entry's output
        content += "%s\n" % line

    yield content

    # This function does approximately the same as the following, following
    # commented-out regular expression except that the regex doesn't quite
    # handle IBM Checker's newlines quite right.
    #   $output =~ s{
    #                 --\ ((ERROR|WARNING|MISTAKE).*?)\s+
    #                        &gt;&gt;&gt
    #                 (.*?)
    #                 \n{3,}
    #               }{make_collapsible_html('cc_checker', "$1 $4", $5, $3, $2)}exgs


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
    yield "<div class='%s unit %s' id='%s-%s'>" % (type, status, type, id)
    yield "<a href=\"javascript:handle('%s');\">" % id
    yield "<img id='img-%s' name='img-%s' alt='%s' src='%s' />" %(id, id, status, icon)
    yield "<div class='%s title'>%s</div></a>\n" % (type, title)
    yield "<div class='%s status %s'>%s</div>\n" % (type, status, status)
    yield "<div class='%s output' id='output-%s'>\n" % (type, id)
    if output and len(output):
        yield "<pre>%s</pre>\n" % (output)
    yield "</div></div>\n"


def diff_pretty(diff):
    """pretty up a diff -u"""
    return highlight(diff, DiffLexer(), HtmlFormatter())


def web_paths(t, paths):
    """change the given source paths into links"""
    if t.scm == "git":
        for path in paths:
            yield " <a href=\"%s/?p=%s;a=history;f=%s%s;h=%s;hb=%s\">%s</a>" % (GITWEB_BASE, t.repo, t.subdir, path, t.branch, t.branch, path)
    else:
        raise Exception("Unknown scm %s" % t.scm)


def history_row_html(myself, entry, tree, changes):
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
    </div>""" % (
        myself, tree.name, entry.date, revision_url,
        myself, tree.name, entry.date, revision_url,
        msg, entry.author)

    (added, modified, removed) = changes

    if modified:
        yield "<div class=\"files\"><span class=\"label\">Modified: </span>"
        yield "".join(web_paths(tree, modified))
        yield "</div>\n"

    if added:
        yield "<div class=\"files\"><span class=\"label\">Added: </span>"
        yield "".join(web_paths(tree, added))
        yield "</div>\n"

    if removed:
        yield "<div class=\"files\"><span class=\"label\">Removed: </span>"
        yield "".join(web_paths(tree, removed))
        yield "</div>\n"

    yield "</div>\n"


def history_row_text(entry, tree, changes):
    """show one row of history table"""
    msg = cgi.escape(entry.message)
    t = time.asctime(time.gmtime(entry.date))
    age = util.dhm_time(time.time()-entry.date)

    yield "Author: %s\n" % entry.author
    if entry.revision:
        yield "Revision: %s\n" % entry.revision
    (added, modified, removed) = changes
    yield "Modified: %s\n" % modified
    yield "Added: %s\n" % added
    yield "Removed: %s\n" % removed
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
        old_rev_builds  = self.buildfarm.builds.get_old_revs(tree, host, compiler)

        if len(old_rev_builds) == 0:
            return

        yield "<h2>Older builds:</h2>\n"

        yield "<table class='real'>\n"
        yield "<thead><tr><th>Revision</th><th>Status</th></tr></thead>\n"
        yield "<tbody>\n"

        for build in old_rev_builds:
            yield "<tr><td>%s</td><td>%s</td></tr>\n" % (
                revision_link(myself, build.revision, tree),
                build_status_html(myself, build))

        yield "</tbody></table>\n"

    def render(self, myself, tree, host, compiler, rev, plain_logs=False):
        """view one build in detail"""

        build = self.buildfarm.get_build(tree, host, compiler, rev)
        try:
            (revision, revision_time) = build.revision_details()
        except data.MissingRevisionInfo:
            revision = None

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

        log = cgi.escape(log)

        m = re.search("(.*)", log)
        if m:
            uname = m.group(1)
        else:
            uname = ""
        m = re.search("CFLAGS=(.*)", log)
        if m:
            cflags = m.group(1)
        else:
            cflags = ""
        m = re.search("configure options: (.*)", log)
        if m:
            config = m.group(1)
        else:
            config = ""
        err = cgi.escape(err)

        yield '<h2>Host information:</h2>\n'

        host_web_file = "../web/%s.html" % host
        if os.path.exists(host_web_file):
            yield util.FileLoad(host_web_file)

        yield "<table class='real'>\n"
        yield ("<tr><td>Host:</td><td><a href='%s?function=View+Host;host=%s;tree=%s;"
               "compiler=%s#'>%s</a> - %s</td></tr>\n" %
                (myself, host, tree, compiler, host, self.buildfarm.hostdb.host(host).platform.encode("utf-8")))
        yield "<tr><td>Uname:</td><td>%s</td></tr>\n" % uname
        yield "<tr><td>Tree:</td><td>%s</td></tr>\n" % self.tree_link(myself, tree)
        yield "<tr><td>Build Revision:</td><td>%s</td></tr>\n" % revision_link(myself, revision, tree)
        yield "<tr><td>Build age:</td><td><div class='age'>%s</div></td></tr>\n" % self.red_age(build.age)
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

        yield "<div id='log'>\n"

        if not plain_logs:
            yield ("<p>Switch to the <a href='%s?function=View+Build;host=%s;tree=%s"
                   ";compiler=%s%s;plain=true' title='Switch to bland, non-javascript,"
                   " unstyled view'>Plain View</a></p>" % (myself, host, tree, compiler, rev_var))

            yield "<div id='actionList'>\n"
            # These can be pretty wide -- perhaps we need to
            # allow them to wrap in some way?
            if err == "":
                yield "<h2>No error log available</h2>\n"
            else:
                yield "<h2>Error log:</h2>\n"
                yield "".join(make_collapsible_html('action', "Error Output", "\n%s" % err, "stderr-0", "errorlog"))

            if log == "":
                yield "<h2>No build log available</h2>\n"
            else:
                yield "<h2>Build log:</h2>\n"
                yield print_log_pretty(log)

            yield "<p><small>Some of the above icons derived from the <a href='http://www.gnome.org'>Gnome Project</a>'s stock icons.</small></p>\n"
            yield "</div>\n"
        else:
            yield ("<p>Switch to the <a href='%s?function=View+Build;host=%s;tree=%s;"
                   "compiler=%s%s' title='Switch to colourful, javascript-enabled, styled"
                   " view'>Enhanced View</a></p>\n" % (myself, host, tree, compiler, rev_var))
            if err == "":
                yield "<h2>No error log available</h2>\n"
            else:
                yield '<h2>Error log:</h2>\n'
                yield '<div id="errorLog"><pre>%s</pre></div>\n' % err
            if log == "":
                yield '<h2>No build log available</h2>\n'
            else:
                yield '<h2>Build log:</h2>\n'
                yield '<div id="buildLog"><pre>%s</pre></div>\n' % log

        yield '</div>\n'


class ViewRecentBuildsPage(BuildFarmPage):

    def render(self, myself, tree, sort_by):
        """Draw the "recent builds" view"""
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

        for build in self.buildfarm.get_last_builds(tree=tree):
            try:
                host = self.buildfarm.hostdb.host(build.host)
            except hostdb.NoSuchHost:
                # Skip, at least for now.
                continue
            status = build_status_html(myself, build)
            try:
                (revision, revision_time) = build.revision_details()
            except data.MissingRevisionInfo:
                pass
            else:
                all_builds.append([
                    build.age,
                    host.platform.encode("utf-8"),
                    "<a href='%s?function=View+Host;host=%s;tree=%s;compiler=%s#%s'>%s</a>"
                        % (myself, host.name,
                           tree, build.compiler, host.name,
                           host.name),
                    build.compiler, tree, status, build.status(),
                    revision_link(myself, revision, tree),
                    revision_time])

        all_builds.sort(cmp_funcs[sort_by])

        t = self.buildfarm.trees[tree]

        sorturl = "%s?tree=%s;function=Recent+Builds" % (myself, tree)

        yield "<div id='recent-builds' class='build-section'>\n"
        yield "<h2>Recent builds of %s (%s branch %s)</h2>\n" % (tree, t.scm, t.branch)
        yield "<table class='real'>\n"
        yield "<thead>\n"
        yield "<tr>\n"
        yield "<th><a href='%s;sortby=age' title='Sort by build age'>Age</a></th>\n" % sorturl
        yield "<th><a href='%s;sortby=revision' title='Sort by build revision'>Revision</a></th>\n" % sorturl
        yield "<th>Tree</th>\n"
        yield "<th><a href='%s;sortby=platform' title='Sort by platform'>Platform</a></th>\n" % sorturl
        yield "<th><a href='%s;sortby=host' title='Sort by host'>Host</a></th>\n" % sorturl
        yield "<th><a href='%s;sortby=compiler' title='Sort by compiler'>Compiler</a></th>\n" % sorturl
        yield "<th><a href='%s;sortby=status' title='Sort by status'>Status</a></th>\n" % sorturl
        yield "<tbody>\n"

        for build in all_builds:
            yield "<tr>\n"
            yield "<td>%s</td>\n" % util.dhm_time(build[0])
            yield "<td>%s</td>\n" % build[7]
            yield "<td>%s</td>\n" % build[4]
            yield "<td>%s</td>\n" % build[1]
            yield "<td>%s</td>\n" % build[2]
            yield "<td>%s</td>\n" % build[3]
            yield "<td>%s</td>\n" % build[5]
            yield "</tr>\n"
        yield "</tbody></table>\n"
        yield "</div>\n"


class ViewHostPage(BuildFarmPage):

    def _render_build_list_header(self, host):
        yield "<div class='host summary'>\n"
        yield "<a id='host' name='host'/>\n"
        yield "<h3>%s - %s</h3>\n" % (host, self.buildfarm.hostdb.host(host).platform.encode("utf-8"))
        yield "<table class='real'>\n"
        yield "<thead><tr><th>Target</th><th>Build<br/>Revision</th><th>Build<br />Age</th><th>Status<br />config/build<br />install/test</th><th>Warnings</th></tr></thead>\n"
        yield "<tbody>\n"

    def _render_build_html(self, myself, build):
        try:
            (revision, revision_time) = build.revision_details()
        except data.MissingRevisionInfo:
            revision = None
        warnings = build.err_count()
        status = build_status_html(myself, build)
        yield "<tr>\n"
        yield "<td><span class='tree'>%s</span>/%s</td>\n" % (self.tree_link(myself, build.tree), build.compiler)
        yield "<td>%s</td>\n" % revision_link(myself, revision, build.tree)
        yield "<td><div class='age'>%s</div></td>\n" % self.red_age(build.age)
        yield "<td><div class='status'>%s</div></td>\n" % status
        yield "<td>%s</td>\n" % warnings
        yield "</tr>\n"

    def render_html(self, myself, *requested_hosts):
        yield "<div class='build-section' id='build-summary'>\n"
        yield '<h2>Host summary:</h2>\n'
        for host in requested_hosts:
            builds = list(self.buildfarm.get_host_builds(host))
            if len(builds) > 0:
                yield "".join(self._render_build_list_header(host))
                for build in builds:
                    yield "".join(self._render_build_html(myself, build))
                yield "</tbody></table>\n"
                yield "</div>\n"
            else:
                deadhosts.append(host)

        yield "</div>\n"
        yield "".join(self.draw_dead_hosts(*deadhosts))

    def render_text(self, myself, *requested_hosts):
        """print the host's table of information"""
        yield "Host summary:\n"

        for host in requested_hosts:
            # make sure we have some data from it
            try:
                self.buildfarm.hostdb.host(host)
            except hostdb.NoSuchHost:
                continue

            builds = list(self.buildfarm.get_host_builds(host))
            if len(builds) > 0:
                yield "%-12s %-10s %-10s %-10s %-10s\n" % (
                        "Tree", "Compiler", "Build Age", "Status", "Warnings")
                for build in builds:
                    yield "%-12s %-10s %-10s %-10s %-10s\n" % (
                            build.tree, build.compiler,
                            util.dhm_time(build.age),
                            str(build.status()), build.err_count())
                yield "\n"

    def draw_dead_hosts(self, *deadhosts):
        """Draw the "dead hosts" table"""

        # don't output anything if there are no dead hosts
        if len(deadhosts) == 0:
            return

        yield "<div class='build-section' id='dead-hosts'>\n"
        yield "<h2>Dead Hosts:</h2>\n"
        yield "<table class='real'>\n"
        yield "<thead><tr><th>Host</th><th>OS</th><th>Min Age</th></tr></thead>\n"
        yield "<tbody>\n"

        for host in deadhosts:
            age_ctime = self.buildfarm.host_age(host)
            yield "<tr><td>%s</td><td>%s</td><td>%s</td></tr>\n" %\
                    (host, self.buildfarm.hostdb.host(host).platform.encode("utf-8"),
                     util.dhm_time(age_ctime))

        yield "</tbody></table>\n"
        yield "</div>\n"


class ViewSummaryPage(BuildFarmPage):

    def _get_counts(self):
        broken_count = defaultdict(lambda: 0)
        panic_count = defaultdict(lambda: 0)
        host_count = defaultdict(lambda: 0)

        # set up a variable to store the broken builds table's code, so we can
        # output when we want
        broken_table = ""
        last_host = ""

        builds = self.buildfarm.get_last_builds()

        for build in builds:
            host_count[build.tree]+=1
            status = build.status()

            if status.failed:
                broken_count[build.tree]+=1
                if "panic" in status.other_failures:
                    panic_count[build.tree]+=1
        return (host_count, broken_count, panic_count)

    def render_text(self, myself):

        (host_count, broken_count, panic_count) = self._get_counts()
        # for the text report, include the current time
        t = time.gmtime()
        yield "Build status as of %s\n\n" % t

        yield "Build counts:\n"
        yield "%-12s %-6s %-6s %-6s\n" % ("Tree", "Total", "Broken", "Panic")

        for tree in sorted(self.buildfarm.trees.keys()):
            yield "%-12s %-6s %-6s %-6s\n" % (tree, host_count[tree],
                    broken_count[tree], panic_count[tree])

        yield "\n"

    def render_html(self, myself):
        """view build summary"""

        (host_count, broken_count, panic_count) = self._get_counts()

        yield "<div id='build-counts' class='build-section'>\n"
        yield "<h2>Build counts:</h2>\n"
        yield "<table class='real'>\n"
        yield "<thead><tr><th>Tree</th><th>Total</th><th>Broken</th><th>Panic</th><th>Test coverage</th></tr></thead>\n"
        yield "<tbody>\n"

        for tree in sorted(self.buildfarm.trees.keys()):
            yield "<tr>\n"
            yield "<td>%s</td>\n" % self.tree_link(myself, tree)
            yield "<td>%s</td>\n" % host_count[tree]
            yield "<td>%s</td>\n" % broken_count[tree]
            if panic_count[tree]:
                    yield "<td class='panic'>\n"
            else:
                    yield "<td>\n"
            yield "%d</td>\n" % panic_count[tree]
            try:
                lcov_status = self.buildfarm.lcov_status(tree)
            except data.NoSuchBuildError:
                yield "<td></td>\n"
            else:
                if lcov_status is not None:
                    yield "<td><a href=\"/lcov/data/%s/%s\">%s %%</a></td>\n" % (
                        self.buildfarm.LCOVHOST, tree, lcov_status)
                else:
                    yield "<td></td>\n"
            yield "</tr>\n"

        yield "</tbody></table>\n"
        yield "</div>\n"


class DiffPage(BuildFarmPage):

    def render(self, myself, tree, revision):
        t = self.buildfarm.trees[tree]
        branch = t.get_branch()
        (entry, diff) = branch.diff(revision)
        # get information about the current diff
        title = "GIT Diff in %s:%s for revision %s" % (
            tree, t.branch, revision)
        yield "<h2>%s</h2>" % title
        changes = branch.changes_summary(revision)
        yield "".join(history_row_html(myself, entry, t, changes))
        yield show_diff(diff, "html")


class RecentCheckinsPage(BuildFarmPage):

    limit = 40

    def render(self, myself, tree, author=None):
        t = self.buildfarm.trees[tree]
        interesting = list()
        authors = {"ALL": "ALL"}
        branch = t.get_branch()
        re_author = re.compile("^(.*) <(.*)>$")
        for entry in branch.log(limit=HISTORY_HORIZON):
            m = re_author.match(entry.author)
            authors[m.group(2)] = m.group(1)
            if author in ("ALL", "", m.group(2)):
                interesting.append(entry)

        yield "<h2>Recent checkins for %s (%s branch %s)</h2>\n" % (
            tree, t.scm, t.branch)
        yield "<form method='GET'>\n"
        yield "Select Author: \n"
        yield "<select name='author'>"
        for email in sorted(authors):
            yield "<option value='%s'>%s</option>" % (email, authors[email])
        yield "</select>"
        yield "<input type='submit' name='sub_function' value='Refresh'/>"
        yield "<input type='hidden' name='tree' value='%s'/>" % tree
        yield "<input type='hidden' name='function', value='Recent Checkins'/>"
        yield "</form>"

        for entry in interesting[:self.limit]:
            changes = branch.changes_summary(entry.revision)
            yield "".join(history_row_html(myself, entry, t, changes))
        yield "\n"


class BuildFarmApp(object):

    def __init__(self, buildfarm):
        self.buildfarm = buildfarm

    def main_menu(self):
        """main page"""

        yield "<form method='GET'>\n"
        yield "<div id='build-menu'>\n"
        yield "<select name='host'>\n"
        for  host in self.buildfarm.hostdb.hosts():
            yield "<option value='%s'>%s -- %s</option>\n" % (
                host.name, host.platform.encode("utf-8"), host.name)
        yield "</select>\n"
        yield "<select name='tree'>\n"
        for tree, t in self.buildfarm.trees.iteritems():
            yield "<option value='%s'>%s:%s</option>\n" % (tree, tree, t.branch)
        yield "</select>\n"
        yield "<select name='compiler'>\n"
        for compiler in self.buildfarm.compilers:
            yield "<option>%s</option>\n" % compiler
        yield "</select>\n"
        yield "<br/>\n"
        yield "<input type='submit' name='function' value='View Build'/>\n"
        yield "<input type='submit' name='function' value='View Host'/>\n"
        yield "<input type='submit' name='function' value='Recent Checkins'/>\n"
        yield "<input type='submit' name='function' value='Summary'/>\n"
        yield "<input type='submit' name='function' value='Recent Builds'/>\n"
        yield "</div>\n"
        yield "</form>\n"

    def __call__(self, environ, start_response):
        form = cgi.FieldStorage(fp=environ['wsgi.input'], environ=environ)
        fn_name = get_param(form, 'function') or ''
        myself = wsgiref.util.application_uri(environ)

        if fn_name == 'text_diff':
            start_response('200 OK', [('Content-type', 'application/x-diff')])
            tree = get_param(form, 'tree')
            t = self.buildfarm.trees[tree]
            branch = t.get_branch()
            revision = get_param(form, 'revision')
            (entry, diff) = branch.diff(revision)
            changes = branch.changes_summary(revision)
            yield "".join(history_row_text(entry, tree, changes))
            yield show_diff(diff, "text")
        elif fn_name == 'Text_Summary':
            start_response('200 OK', [('Content-type', 'text/plain')])
            page = ViewSummaryPage(self.buildfarm)
            yield "".join(page.render_text(myself))
        else:
            start_response('200 OK', [('Content-type', 'text/html')])

            yield "<html>\n"
            yield "  <head>\n"
            yield "    <title>samba.org build farm</title>\n"
            yield "    <script language='javascript' src='/build_farm.js'></script>\n"
            yield "    <meta name='keywords' contents='Samba SMB CIFS Build Farm'/>\n"
            yield "    <meta name='description' contents='Home of the Samba Build Farm, the automated testing facility.'/>\n"
            yield "    <meta name='robots' contents='noindex'/>\n"
            yield "    <link rel='stylesheet' href='/build_farm.css' type='text/css' media='all'/>\n"
            yield "    <link rel='stylesheet' href='http://master.samba.org/samba/style/common.css' type='text/css' media='all'/>\n"
            yield "    <link rel='shortcut icon' href='http://www.samba.org/samba/images/favicon.ico'/>\n"
            yield "  </head>\n"
            yield "<body>\n"

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
                yield "".join(page.render_html(myself, get_param(form, 'host')))
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
                    yield "".join(page.render_html(myself, paths[2]))
            else:
                page = ViewSummaryPage(self.buildfarm)
                yield "".join(page.render_html(myself))
            yield util.FileLoad(os.path.join(webdir, "footer.html"))
            yield "</body>\n"
            yield "</html>\n"


if __name__ == '__main__':
    import optparse
    parser = optparse.OptionParser("[options]")
    parser.add_option("--cachedirname", help="Cache directory name", type=str)
    parser.add_option("--port", help="Port to listen on [localhost:8000]", default="localhost:8000", type=str)
    opts, args = parser.parse_args()
    buildfarm = CachingBuildFarm(cachedirname=opts.cachedirname)
    buildApp = BuildFarmApp(buildfarm)
    from wsgiref.simple_server import make_server
    import mimetypes
    mimetypes.init()

    def standaloneApp(environ, start_response):
        if environ['PATH_INFO']:
            m = re.match("^/([a-zA-Z0-9_-]+)(\.[a-zA-Z0-9_-]+)?", environ['PATH_INFO'])
            if m:
                static_file = os.path.join(webdir, m.group(1)+m.group(2))
                if os.path.exists(static_file):
                    type = mimetypes.types_map[m.group(2)]
                    start_response('200 OK', [('Content-type', type)])
                    data = open(static_file, 'rb').read()
                    yield data
                    return
        yield "".join(buildApp(environ, start_response))
    try:
        (address, port) = opts.port.rsplit(":", 1)
    except ValueError:
        address = "localhost"
        port = opts.port
    httpd = make_server(address, int(port), standaloneApp)
    print "Serving on %s:%d..." % (address, int(port))
    httpd.serve_forever()
