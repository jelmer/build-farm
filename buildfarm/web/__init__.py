#!/usr/bin/python
# This CGI script presents the results of the build_farm build

# Copyright (C) Jelmer Vernooij <jelmer@samba.org>     2010-2014
# Copyright (C) Matthieu Patou <mat@matws.net>         2010-2012
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
import sys

from buildfarm import (
    hostdb,
    util,
    )
from buildfarm.build import (
    LogFileMissing,
    NoSuchBuildError,
    NoTestOutput,
    )

import cgi
from pygments import highlight
from pygments.lexers.text import DiffLexer
from pygments.formatters import HtmlFormatter
import re
import time

import wsgiref.util
webdir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "web"))

GITWEB_BASE = "https://gitweb.samba.org"
HISTORY_HORIZON = 1000

# Maximum age of builds to consider when displaying summary page statistics.
# Note that trees only get rebuilt when they change, so this value is
# intentionally set to a high value to cope with trees that don't change often.
SUMMARY_MAX_BUILD_AGE = (180 * 24 * 60 * 60)

# this is automatically filled in
deadhosts = []

def select(name, values, default=None):
    yield "<select name='%s'>" % name
    for key in sorted(values):
        if key == default:
            yield "<option selected value='%s'>%s</option>" % (key, values[key])
        else:
            yield "<option value='%s'>%s</option>" % (key, values[key])
    yield "</select>"


def get_param(form, param):
    """get a param from the request, after sanitizing it"""
    if param not in form:
        return None

    result = [s.replace(" ", "_") for s in form.getlist(param)]

    for entry in result:
        if re.match("[^a-zA-Z0-9\-\_\.]", entry):
            raise Exception("Parameter %s is invalid" % param)

    return result[0]


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

    ostatus = []
    if "panic" in status.other_failures:
        ostatus.append(span("status panic", "PANIC"))
    if "disk full" in status.other_failures:
        ostatus.append(span("status failed", "disk full"))
    if "timeout" in status.other_failures:
        ostatus.append(span("status failed", "timeout"))
    if "inconsistent test result" in status.other_failures:
        ostatus.append(span("status failed", "unexpected return code"))
    bstatus = "/".join([span_status(s) for s in status.stages])
    ret = bstatus
    if ostatus:
        ret += "(%s)" % ",".join(ostatus)
    if ret == "":
        ret = "?"
    return ret


def build_uri(myself, build):
    return "%s/build/%s" % (myself, build.log_checksum())


def build_link(myself, build):
    return "<a href='%s'>%s</a>" % (
        build_uri(myself, build), html_build_status(build.status()))


def tree_uri(myself, tree):
    return "%s/tree/%s" % (myself, tree.name)


def tree_link(myself, tree):
    """return a link to a particular tree"""
    return "<a href='%s' title='View recent builds for %s'>%s:%s</a>" % (
        tree_uri(myself, tree), tree.name, tree.name, tree.branch)


def host_uri(myself, host):
    return "%s/host/%s" % (myself, host)

def host_link(myself, host):
    return "<a href='%s'>%s</a>" % (host_uri(myself, host), host)


def revision_uri(myself, revision, tree):
    return "%s?function=diff;tree=%s;revision=%s" % (myself, tree, revision)


def revision_link(myself, revision, tree):
    """return a link to a particular revision"""
    if revision is None:
        return "unknown"
    return "<a href='%s' title='View Diff for %s'>%s</a>" % (
        revision_uri(myself, revision, tree), revision, revision[:7])


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
    elif subunit_result == "uxsuccess":
        return "uxpassed"
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
             output = print_log_cc_checker(output)

        self.indice += 1
        return "".join(make_collapsible_html('action', actionName, output, self.indice, status))

    # log is already CGI-escaped, so handle '>' in test name by handling &gt
    def _format_stage(self, m):
        self.indice += 1
        return "".join(make_collapsible_html('test', m.group(1), m.group(2), self.indice, m.group(3)))

    def _format_skip_testsuite(self, m):
        self.indice += 1
        return "".join(make_collapsible_html('test', m.group(1), '', self.indice, 'skipped'))

    def _format_pretestsuite(self, m):
        self.indice += 1
        return m.group(1)+"".join(make_collapsible_html('pretest', 'Pretest infos', m.group(2), self.indice, 'ok'))+"\n"+m.group(3)

    def _format_testsuite(self, m):
        testName = m.group(1)
        content = m.group(2)
        status = subunit_to_buildfarm_result(m.group(3))
        if m.group(4):
            errorReason = format_subunit_reason(m.group(4))
        else:
            errorReason = ""
        self.indice += 1
        backlink = ""
        if m.group(3) in ("error", "failure"):
            self.test_links.append([testName, 'lnk-test-%d' %self.indice])
            backlink = "<p><a href='#shortcut2errors'>back to error list</a>"
        return "".join(make_collapsible_html('test', testName, content+errorReason+backlink, self.indice, status))

    def _format_test(self, m):
        self.indice += 1
        return "".join(make_collapsible_html('test', m.group(1), m.group(2)+format_subunit_reason(m.group(4)), self.indice, subunit_to_buildfarm_result(m.group(3))))

    def pretty_print(self, log):
        # do some pretty printing for the actions
        pattern = re.compile("(Running action\s+([\w\-]+)$(?:\s^.*$)*?\sACTION\ (PASSED|FAILED):\ ([\w\-]+)$)", re.M)
        log = pattern.sub(self._pretty_print, log)
        buf = ""

        log = re.sub("""
              --==--==--==--==--==--==--==--==--==--==--.*?
              Running\ test\ ([\w\-=,_:\ /.&;]+).*?
              --==--==--==--==--==--==--==--==--==--==--
                  (.*?)
              ==========================================.*?
              TEST\ (FAILED|PASSED|SKIPPED):.*?
              ==========================================\s+
            """, self._format_stage, log)

        pattern = re.compile("(Running action test).*$\s((?:^.*$\s)*?)^((?:skip-)?testsuite: )", re.M)
        log = pattern.sub(self._format_pretestsuite, log)

        log = re.sub("skip-testsuite: ([\w\-=,_:\ /.&; \(\)]+).*?",
                self._format_skip_testsuite, log)

        self.test_links = []
        pattern = re.compile("^testsuite: (.+)$\s((?:^.*$\s)*?)testsuite-(\w+): .*?(?:(\[$\s(?:^.*$\s)*?^\]$)|$)", re.M)
        log = pattern.sub(self._format_testsuite, log)
        log = re.sub("""
              ^test: ([\w\-=,_:\ /.&; \(\)]+).*?
              (.*?)
              (success|xfail|failure|skip|uxsuccess): [\w\-=,_:\ /.&; \(\)]+( \[.*?\])?.*?
           """, self._format_test, log)

        for tst in self.test_links:
            buf = "%s\n<A href='#%s'>%s</A>" % (buf, tst[1], tst[0])

        if not buf == "":
            divhtml = "".join(make_collapsible_html('testlinks', 'Shortcut to failed tests', "<a name='shortcut2errors'></a>%s" % buf, self.indice, ""))+"\n"
            log = re.sub("Running action\s+test", divhtml, log)
        return "<pre>%s</pre>" % log


def print_log_pretty(log):
    return LogPrettyPrinter().pretty_print(log)


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
                output += "".join(make_collapsible_html('cc_checker', title, content, id, status))
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
                output += "".join(make_collapsible_html('cc_checker', title, content, id, status))

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
    if status.lower() in ("", "failed"):
        icon = '/icon_hide_16.png'
    else:
        icon = '/icon_unhide_16.png'

    # trim leading and trailing whitespace
    output = output.strip()

    # note that we may be inside a <pre>, so we don't put any extra whitespace
    # in this html
    yield "<div class='%s unit %s' id='%s-%s'>" % (type, status, type, id)
    yield "<a name='lnk-%s-%s' href=\"javascript:handle('%s');\">" % (type, id, id)
    yield "<img id='img-%s' name='img-%s' alt='%s' src='%s' />" % (id, id, status, icon)
    yield "<div class='%s title'>%s</div></a>" % (type, title)
    yield "<div class='%s status %s'>%s</div>" % (type, status, status)
    yield "<div class='%s output' id='output-%s'>" % (type, id)
    if output:
        yield "<pre>%s</pre>" % (output,)
    yield "</div></div>"


def web_paths(t, paths):
    """change the given source paths into links"""
    if t.scm == "git":
        ret = ""
        for path in paths:
            ret += " <a href=\"%s/?p=%s;a=history;f=%s%s;h=%s;hb=%s\">%s</a>" % (GITWEB_BASE, t.repo, t.subdir, path, t.branch, t.branch, path)
        return ret
    else:
        raise Exception("Unknown scm %s" % t.scm)


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


class BuildFarmPage(object):

    def __init__(self, buildfarm):
        self.buildfarm = buildfarm

    def red_age(self, age):
        """show an age as a string"""
        if age > self.buildfarm.OLDAGE:
            return "<span class='old'>%s</span>" % util.dhm_time(age)
        return util.dhm_time(age)

    def tree_link(self, myself, treename):
        try:
            return tree_link(myself, self.buildfarm.trees[treename])
        except KeyError:
            return treename

    def render(self, output_type):
        raise NotImplementedError(self.render)


class ViewBuildPage(BuildFarmPage):

    def show_oldrevs(self, myself, build, host, compiler, limit=None):
        """show the available old revisions, if any"""

        tree = build.tree
        old_builds = self.buildfarm.builds.get_old_builds(tree, host, compiler)

        if not old_builds:
            return

        yield "<h2>Older builds:</h2>\n"

        yield "<table class='real'>\n"
        yield "<thead><tr><th>Revision</th><th>Status</th><th>Age</th></tr></thead>\n"
        yield "<tbody>\n"

        for old_build in old_builds[:limit]:
            yield "<tr><td>%s</td><td>%s</td><td>%s</td></tr>\n" % (
                revision_link(myself, old_build.revision, tree),
                build_link(myself, old_build),
                util.dhm_time(old_build.age))

        yield "</tbody></table>\n"

        yield "<p><a href='%s/limit/-1'>Show all previous build list</a>\n" % (build_uri(myself, build))

    def render(self, myself, build, plain_logs=False, limit=10):
        """view one build in detail"""

        uname = None
        cflags = None
        config = None

        try:
            f = build.read_log()
            try:
                log = f.read()
            finally:
                f.close()
        except LogFileMissing:
            log = None
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

        err = cgi.escape(err)
        yield '<h2>Host information:</h2>'

        host_web_file = "../web/%s.html" % build.host
        if os.path.exists(host_web_file):
            yield util.FileLoad(host_web_file)

        yield "<table class='real'>\n"
        yield "<tr><td>Host:</td><td><a href='%s?function=View+Host;host=%s;tree=%s;"\
              "compiler=%s#'>%s</a> - %s</td></tr>\n" %\
                (myself, build.host, build.tree, build.compiler, build.host, self.buildfarm.hostdb[build.host].platform.encode("utf-8"))
        if uname is not None:
            yield "<tr><td>Uname:</td><td>%s</td></tr>\n" % uname
        yield "<tr><td>Tree:</td><td>%s</td></tr>\n" % self.tree_link(myself, build.tree)
        yield "<tr><td>Build Revision:</td><td>%s</td></tr>\n" % revision_link(myself, build.revision, build.tree)
        yield "<tr><td>Build age:</td><td><div class='age'>%s</div></td></tr>\n" % self.red_age(build.age)
        yield "<tr><td>Status:</td><td>%s</td></tr>\n" % build_link(myself, build)
        yield "<tr><td>Compiler:</td><td>%s</td></tr>\n" % build.compiler
        if cflags is not None:
            yield "<tr><td>CFLAGS:</td><td>%s</td></tr>\n" % cflags
        if config is not None:
            yield "<tr><td>configure options:</td><td>%s</td></tr>\n" % config
        yield "</table>\n"

        yield "".join(self.show_oldrevs(myself, build, build.host, build.compiler, limit))

        # check the head of the output for our magic string
        rev_var = ""
        if build.revision:
            rev_var = ";revision=%s" % build.revision

        yield "<div id='log'>"

        yield "<p><a href='%s/+subunit'>Subunit output</a>" % build_uri(myself, build)
        try:
            previous_build = self.buildfarm.builds.get_previous_build(build.tree, build.host, build.compiler, build.revision)
        except NoSuchBuildError:
            pass
        else:
            yield ", <a href='%s/+subunit-diff/%s'>diff against previous</a>" % (
                build_uri(myself, build), previous_build.log_checksum())
        yield "</p>"
        yield "<p><a href='%s/+stdout'>Standard output (as plain text)</a>, " % build_uri(myself, build)
        yield "<a href='%s/+stderr'>Standard error (as plain text)</a>" % build_uri(myself, build)
        yield "</p>"

        if not plain_logs:
            yield "<p>Switch to the <a href='%s?function=View+Build;host=%s;tree=%s"\
                  ";compiler=%s%s;plain=true' title='Switch to bland, non-javascript,"\
                  " unstyled view'>Plain View</a></p>" % (myself, build.host, build.tree, build.compiler, rev_var)

            yield "<div id='actionList'>"
            # These can be pretty wide -- perhaps we need to
            # allow them to wrap in some way?
            if err == "":
                yield "<h2>No error log available</h2>\n"
            else:
                yield "<h2>Error log:</h2>"
                yield "".join(make_collapsible_html('action', "Error Output", "\n%s" % err, "stderr-0", "errorlog"))

            if log is None:
                yield "<h2>No build log available</h2>"
            else:
                yield "<h2>Build log:</h2>\n"
                yield print_log_pretty(log)

            yield "<p><small>Some of the above icons derived from the <a href='https://www.gnome.org'>Gnome Project</a>'s stock icons.</small></p>"
            yield "</div>"
        else:
            yield "<p>Switch to the <a href='%s?function=View+Build;host=%s;tree=%s;"\
                  "compiler=%s%s' title='Switch to colourful, javascript-enabled, styled"\
                  " view'>Enhanced View</a></p>" % (myself, build.host, build.tree, build.compiler, rev_var)
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

    def render(self, myself, tree, sort_by=None):
        """Draw the "recent builds" view"""
        all_builds = []

        def build_platform(build):
            host = self.buildfarm.hostdb[build.host]
            return host.platform.encode("utf-8")

        def build_platform_safe(build):
            try:
                host = self.buildfarm.hostdb[build.host]
            except hostdb.NoSuchHost:
                return "UNKNOWN"
            else:
                return host.platform.encode("utf-8")

        cmp_funcs = {
            "revision": lambda a, b: cmp(a.revision, b.revision),
            "age": lambda a, b: cmp(a.age, b.age),
            "host": lambda a, b: cmp(a.host, b.host),
            "platform": lambda a, b: cmp(build_platform_safe(a), build_platform_safe(b)),
            "compiler": lambda a, b: cmp(a.compiler, b.compiler),
            "status": lambda a, b: cmp(a.status(), b.status()),
            }

        if sort_by is None:
            sort_by = "age"

        if sort_by not in cmp_funcs:
            yield "not a valid sort mechanism: %r" % sort_by
            return

        all_builds = list(self.buildfarm.get_tree_builds(tree))

        all_builds.sort(cmp_funcs[sort_by])

        t = self.buildfarm.trees[tree]

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
            try:
                build_platform_name = build_platform(build)
                yield "<tr>"
                yield "<td>%s</td>" % util.dhm_time(build.age)
                yield "<td>%s</td>" % revision_link(myself, build.revision, build.tree)
                yield "<td>%s</td>" % build.tree
                yield "<td>%s</td>" % build_platform_name
                yield "<td>%s</td>" % host_link(myself, build.host)
                yield "<td>%s</td>" % build.compiler
                yield "<td>%s</td>" % build_link(myself, build)
                yield "</tr>"
            except hostdb.NoSuchHost:
                pass
        yield "</tbody></table>"
        yield "</div>"


class ViewHostPage(BuildFarmPage):

    def _render_build_list_header(self, host):
        yield "<div class='host summary'>"
        yield "<a id='host' name='host'/>"
        yield "<h3>%s - %s</h3>" % (host.name, host.platform.encode("utf-8"))
        yield "<table class='real'>"
        yield "<thead><tr><th>Target</th><th>Build<br/>Revision</th><th>Build<br />Age</th><th>Status<br />config/build<br />install/test</th><th>Warnings</th></tr></thead>"
        yield "<tbody>"

    def _render_build_html(self, myself, build):
        warnings = build.err_count()
        yield "<tr>"
        yield "<td><span class='tree'>" + self.tree_link(myself, build.tree) +"</span>/" + build.compiler + "</td>"
        yield "<td>" + revision_link(myself, build.revision, build.tree) + "</td>"
        yield "<td><div class='age'>" + self.red_age(build.age) + "</div></td>"
        yield "<td><div class='status'>%s</div></td>" % build_link(myself, build)
        yield "<td>%s</td>" % warnings
        yield "</tr>"

    def render_html(self, myself, *requested_hosts):
        yield "<div class='build-section' id='build-summary'>"
        yield '<h2>Host summary:</h2>'
        for hostname in requested_hosts:
            try:
                host = self.buildfarm.hostdb[hostname]
            except hostdb.NoSuchHost:
                continue
            builds = list(self.buildfarm.get_host_builds(hostname))
            if len(builds) > 0:
                yield "".join(self._render_build_list_header(host))
                for build in builds:
                    yield "".join(self._render_build_html(myself, build))
                yield "</tbody></table>"
                yield "</div>"
            else:
                deadhosts.append(hostname)

        yield "</div>"
        yield "".join(self.draw_dead_hosts(*deadhosts))

    def render_text(self, myself, *requested_hosts):
        """print the host's table of information"""
        yield "Host summary:\n"

        for host in requested_hosts:
            # make sure we have some data from it
            try:
                self.buildfarm.hostdb[host]
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

        yield "<div class='build-section' id='dead-hosts'>"
        yield "<h2>Dead Hosts:</h2>"
        yield "<table class='real'>"
        yield "<thead><tr><th>Host</th><th>OS</th><th>Min Age</th></tr></thead>"
        yield "<tbody>"

        for host in deadhosts:
            last_build = self.buildfarm.host_last_build(host)
            age = time.time() - last_build
            try:
                platform = self.buildfarm.hostdb[host].platform.encode("utf-8")
            except hostdb.NoSuchHost:
                continue
            yield "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" %\
                    (host, platform, util.dhm_time(age))

        yield "</tbody></table>"
        yield "</div>"


class ViewSummaryPage(BuildFarmPage):

    def _get_counts(self):
        broken_count = defaultdict(lambda: 0)
        panic_count = defaultdict(lambda: 0)
        host_count = defaultdict(lambda: 0)

        # set up a variable to store the broken builds table's code, so we can
        # output when we want
        broken_table = ""

        builds = self.buildfarm.get_summary_builds(min_age=time.time() - SUMMARY_MAX_BUILD_AGE)

        for tree, status in builds:
            host_count[tree]+=1

            if status.failed:
                broken_count[tree]+=1
                if "panic" in status.other_failures:
                    panic_count[tree]+=1
        return (host_count, broken_count, panic_count)

    def render_text(self, myself):
        (host_count, broken_count, panic_count) = self._get_counts()
        # for the text report, include the current time
        yield "Build status as of %s\n\n" % time.asctime()

        yield "Build counts:\n"
        yield "%-12s %-6s %-6s %-6s\n" % ("Tree", "Total", "Broken", "Panic")

        for tree in sorted(self.buildfarm.trees.keys()):
            yield "%-12s %-6s %-6s %-6s\n" % (tree, host_count[tree],
                    broken_count[tree], panic_count[tree])
        yield "\n"

    def render_html(self, myself):
        """view build summary"""

        (host_count, broken_count, panic_count) = self._get_counts()

        yield "<div id='build-counts' class='build-section'>"
        yield "<h2>Build counts:</h2>"
        yield "<table class='real'>"
        yield "<thead><tr><th>Tree</th><th>Total</th><th>Broken</th><th>Panic</th><th>Test coverage</th></tr></thead>"
        yield "<tbody>"

        for tree in sorted(self.buildfarm.trees.keys()):
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
                lcov_status = self.buildfarm.lcov_status(tree)
            except NoSuchBuildError:
                yield "<td></td>"
            else:
                if lcov_status is not None:
                    yield "<td><a href=\"/lcov/data/%s/%s\">%s %%</a></td>" % (
                        self.buildfarm.LCOVHOST, tree, lcov_status)
                else:
                    yield "<td></td>"

            try:
                unused_fns = self.buildfarm.unused_fns(tree)
            except NoSuchBuildError:
                yield "<td></td>"
            else:
                if unused_fns is not None:
                    yield "<td><a href=\"/lcov/data/%s/%s/%s\">Unused Functions</a></td>" % (
                        self.buildfarm.LCOVHOST, tree, unused_fns)
                else:
                    yield "<td></td>"
            yield "</tr>"

        yield "</tbody></table>"
        yield "</div>"


class HistoryPage(BuildFarmPage):

    def history_row_html(self, myself, entry, tree, changes):
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

        (added, modified, removed) = changes

        if modified:
            yield "<div class=\"files\"><span class=\"label\">Modified: </span>"
            yield web_paths(tree, modified)
            yield "</div>\n"

        if added:
            yield "<div class=\"files\"><span class=\"label\">Added: </span>"
            yield web_paths(tree, added)
            yield "</div>\n"

        if removed:
            yield "<div class=\"files\"><span class=\"label\">Removed: </span>"
            yield web_paths(tree, removed)
            yield "</div>\n"

        builds = list(self.buildfarm.get_revision_builds(tree.name, entry.revision))
        if builds:
            yield "<div class=\"builds\">\n"
            yield "<span class=\"label\">Builds: </span>\n"
            for build in builds:
                yield "%s(%s) " % (build_link(myself, build), host_link(myself, build.host))
            yield "</div>\n"
        yield "</div>\n"


class DiffPage(HistoryPage):

    def render(self, myself, tree, revision):
        try:
            t = self.buildfarm.trees[tree]
        except KeyError:
            yield "Unknown tree %s" % tree
            return
        branch = t.get_branch()
        (entry, diff) = branch.diff(revision)
        # get information about the current diff
        title = "GIT Diff in %s:%s for revision %s" % (
            tree, t.branch, revision)
        yield "<h2>%s</h2>" % title
        changes = branch.changes_summary(revision)
        yield "".join(self.history_row_html(myself, entry, t, changes))
        diff = highlight(diff, DiffLexer(), HtmlFormatter())
        yield "<pre>%s</pre>\n" % diff.encode("utf-8")


class RecentCheckinsPage(HistoryPage):

    limit = 10

    def render(self, myself, tree, gitstart, author=None):
        t = self.buildfarm.trees[tree]
        interesting = list()
        authors = {"ALL": "ALL"}
        branch = t.get_branch()
        re_author = re.compile("^(.*) <(.*)>$")
 
        for entry in branch.log(limit=HISTORY_HORIZON):
            m = re_author.match(entry.author)
            authors[m.group(2)] = m.group(1)
            if author in (None, "ALL", m.group(2)):
                interesting.append(entry)

        yield "<h2>Recent checkins for %s (%s branch %s)</h2>\n" % (
            tree, t.scm, t.branch)
        yield "<form method='GET'>"
        yield "Select Author: "
        yield "".join(select(name="author", values=authors, default=author))
        yield "<input type='submit' name='sub_function' value='Refresh'/>"
        yield "<input type='hidden' name='tree' value='%s'/>" % tree
        yield "<input type='hidden' name='function', value='Recent Checkins'/>"
        yield "</form>"

        gitstop = gitstart + self.limit

        for entry in interesting[gitstart:gitstop]:
            changes = branch.changes_summary(entry.revision)
            yield "".join(self.history_row_html(myself, entry, t, changes))
        yield "\n"

        yield "<form method='GET'>"
        yield "<div class='newform'>\n"
        if gitstart != 0:
            yield "<button name='gitstart' type='submit' value=" + str(gitstart - self.limit) + " style='position:absolute;left:0px;'>Previous</button>"
        if len(interesting) > gitstop:
            yield "<button name='gitstart' type='submit' value=" + str(gitstop) + " style='position:absolute;right:0px;'>Next</button>"
        yield "<input type='hidden' name='function', value='Recent Checkins'/>"
        yield "<input type='hidden' name='gitcount' value='%s'/>" % gitstop
        if author and author != "ALL":
            yield "<input type='hidden' name='author' value='%s'/>" % author
        yield "<input type='hidden' name='tree' value='%s'/>" % tree
        yield "</div>\n"
        yield "</form>"
        yield "<br>"


class BuildFarmApp(object):

    def __init__(self, buildfarm):
        self.buildfarm = buildfarm

    def main_menu(self, tree, host, compiler):
        """main page"""

        yield "<form method='GET'>\n"
        yield "<div id='build-menu'>\n"
        host_dict = {}
        for h in self.buildfarm.hostdb.hosts():
            host_dict[h.name] = "%s -- %s" % (h.platform.encode("utf-8"), h.name)
        yield "".join(select("host", host_dict, default=host))
        tree_dict = {}
        for t in self.buildfarm.trees.values():
            tree_dict[t.name] = "%s:%s" % (t.name, t.branch)
        yield "".join(select("tree", tree_dict, default=tree))
        yield "".join(select("compiler", dict(zip(self.buildfarm.compilers, self.buildfarm.compilers)), default=compiler))
        yield "<br/>\n"
        yield "<input type='submit' name='function' value='View Build'/>\n"
        yield "<input type='submit' name='function' value='View Host'/>\n"
        yield "<input type='submit' name='function' value='Recent Checkins'/>\n"
        yield "<input type='submit' name='function' value='Summary'/>\n"
        yield "<input type='submit' name='function' value='Recent Builds'/>\n"
        yield "</div>\n"
        yield "</form>\n"

    def html_page(self, form, lines):
        yield "<html>\n"
        yield "  <head>\n"
        yield "    <title>samba.org build farm</title>\n"
        yield "    <script language='javascript' src='/build_farm.js'></script>\n"
        yield "    <meta name='keywords' contents='Samba SMB CIFS Build Farm'/>\n"
        yield "    <meta name='description' contents='Home of the Samba Build Farm, the automated testing facility.'/>\n"
        yield "    <meta name='robots' contents='noindex'/>"
        yield "    <link rel='stylesheet' href='/build_farm.css' type='text/css' media='all'/>"
        yield "    <link rel='stylesheet' href='//www.samba.org/samba/style/common.css' type='text/css' media='all'/>"
        yield "    <link rel='shortcut icon' href='//www.samba.org/samba/images/favicon.ico'/>"
        yield "  </head>"
        yield "<body>"

        yield util.FileLoad(os.path.join(webdir, "header2.html"))

        tree = get_param(form, "tree")
        host = get_param(form, "host")
        compiler = get_param(form, "compiler")
        yield "".join(self.main_menu(tree, host, compiler))
        yield util.FileLoad(os.path.join(webdir, "header3.html"))
        yield "".join(lines)
        yield util.FileLoad(os.path.join(webdir, "footer.html"))
        yield "</body>"
        yield "</html>"

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
            yield "%s\n" % diff
        elif fn_name == 'Text_Summary':
            start_response('200 OK', [('Content-type', 'text/plain')])
            page = ViewSummaryPage(self.buildfarm)
            yield "".join(page.render_text(myself))
        elif fn_name:
            start_response('200 OK', [
                ('Content-type', 'text/html; charset=utf-8')])

            tree = get_param(form, "tree")
            host = get_param(form, "host")
            compiler = get_param(form, "compiler")

            if fn_name == "View_Build":
                plain_logs = (get_param(form, "plain") is not None and get_param(form, "plain").lower() in ("yes", "1", "on", "true", "y"))
                revision = get_param(form, "revision")
                checksum = get_param(form, "checksum")
                try:
                    build = self.buildfarm.get_build(tree, host,
                        compiler, revision, checksum=checksum)
                except NoSuchBuildError:
                    yield "No such build: %s on %s with %s, rev %r, checksum %r" % (
                        tree, host, compiler, revision, checksum)
                else:
                    page = ViewBuildPage(self.buildfarm)
                    plain_logs = (get_param(form, "plain") is not None and get_param(form, "plain").lower() in ("yes", "1", "on", "true", "y"))
                    yield "".join(self.html_page(form, page.render(myself, build, plain_logs)))
            elif fn_name == "View_Host":
                page = ViewHostPage(self.buildfarm)
                yield "".join(self.html_page(form, page.render_html(myself, get_param(form, 'host'))))
            elif fn_name == "Recent_Builds":
                page = ViewRecentBuildsPage(self.buildfarm)
                yield "".join(self.html_page(form, page.render(myself, get_param(form, "tree"), get_param(form, "sortby") or "age")))
            elif fn_name == "Recent_Checkins":
                # validate the tree
                author = get_param(form, 'author')
                gitstart = get_param(form, 'gitstart')
                if gitstart is None:
                    gitstart = 0
                else:
                    gitstart = int(gitstart)
                page = RecentCheckinsPage(self.buildfarm)
                yield "".join(self.html_page(form, page.render(myself, tree, gitstart, author)))
            elif fn_name == "diff":
                revision = get_param(form, 'revision')
                page = DiffPage(self.buildfarm)
                yield "".join(self.html_page(form, page.render(myself, tree, revision)))
            elif fn_name == "Summary":
                page = ViewSummaryPage(self.buildfarm)
                yield "".join(self.html_page(form, page.render_html(myself)))
            else:
                yield "Unknown function %s" % fn_name
        else:
            fn = wsgiref.util.shift_path_info(environ)
            if fn == "tree":
                tree = wsgiref.util.shift_path_info(environ)
                subfn = wsgiref.util.shift_path_info(environ)
                if subfn in ("", None, "+recent"):
                    start_response('200 OK', [
                        ('Content-type', 'text/html; charset=utf-8')])
                    page = ViewRecentBuildsPage(self.buildfarm)
                    yield "".join(self.html_page(form, page.render(myself, tree, get_param(form, 'sortby') or 'age')))
                elif subfn == "+recent-ids":
                    start_response('200 OK', [
                        ('Content-type', 'text/plain; charset=utf-8')])
                    yield "".join([x.log_checksum()+"\n" for x in self.buildfarm.get_tree_builds(tree) if x.has_log()])
                else:
                    start_response('200 OK', [
                        ('Content-type', 'text/html; charset=utf-8')])
                    yield "Unknown subfn %s" % subfn
            elif fn == "host":
                start_response('200 OK', [
                    ('Content-type', 'text/html; charset=utf-8')])
                page = ViewHostPage(self.buildfarm)
                yield "".join(self.html_page(form, page.render_html(myself, wsgiref.util.shift_path_info(environ))))
            elif fn == "build":
                build_checksum = wsgiref.util.shift_path_info(environ)
                try:
                    build = self.buildfarm.builds.get_by_checksum(build_checksum)
                except NoSuchBuildError:
                    start_response('404 Page Not Found', [
                        ('Content-Type', 'text/html; charset=utf8')])
                    yield "No build with checksum %s found" % build_checksum
                    return
                page = ViewBuildPage(self.buildfarm)
                subfn = wsgiref.util.shift_path_info(environ)
                if subfn == "+plain":
                    start_response('200 OK', [
                        ('Content-type', 'text/html; charset=utf-8')])
                    yield "".join(page.render(myself, build, True))
                elif subfn == "+subunit":
                    start_response('200 OK', [
                        ('Content-type', 'text/x-subunit; charset=utf-8'),
                        ('Content-Disposition', 'attachment; filename="%s.%s.%s-%s.subunit"' % (build.tree, build.host, build.compiler, build.revision))])
                    try:
                        yield build.read_subunit().read()
                    except NoTestOutput:
                        yield "There was no test output"
                elif subfn == "+stdout":
                    start_response('200 OK', [
                        ('Content-type', 'text/plain; charset=utf-8'),
                        ('Content-Disposition', 'attachment; filename="%s.%s.%s-%s.log"' % (build.tree, build.host, build.compiler, build.revision))])
                    yield build.read_log().read()
                elif subfn == "+stderr":
                    start_response('200 OK', [
                        ('Content-type', 'text/plain; charset=utf-8'),
                        ('Content-Disposition', 'attachment; filename="%s.%s.%s-%s.err"' % (build.tree, build.host, build.compiler, build.revision))])
                    yield build.read_err().read()
                elif subfn == "+subunit-diff":
                    start_response('200 OK', [
                        ('Content-type', 'text/plain; charset=utf-8')])
                    subunit_this = build.read_subunit().readlines()
                    other_build_checksum = wsgiref.util.shift_path_info(environ)
                    other_build = self.buildfarm.builds.get_by_checksum(other_build_checksum)
                    subunit_other = other_build.read_subunit().readlines()
                    import difflib
                    yield "".join(difflib.unified_diff(subunit_other, subunit_this))

                elif subfn in ("", "limit", None):
                    if subfn == "limit":
                        try:
                            limit = int(wsgiref.util.shift_path_info(environ))
                        except:
                            limit = 10
                    else:
                        limit = 10
                    start_response('200 OK', [
                        ('Content-type', 'text/html; charset=utf-8')])
                    yield "".join(self.html_page(form, page.render(myself, build, False, limit)))
            elif fn in ("", None):
                start_response('200 OK', [
                    ('Content-type', 'text/html; charset=utf-8')])
                page = ViewSummaryPage(self.buildfarm)
                yield "".join(self.html_page(form, page.render_html(myself)))
            else:
                start_response('404 Page Not Found', [
                    ('Content-type', 'text/html; charset=utf-8')])
                yield "Unknown function %s" % fn


if __name__ == '__main__':
    import optparse
    parser = optparse.OptionParser("[options]")
    parser.add_option("--debug-storm", help="Enable storm debugging",
                      default=False, action='store_true')
    parser.add_option("--port", help="Port to listen on [localhost:8000]",
        default="localhost:8000", type=str)
    opts, args = parser.parse_args()
    from buildfarm import BuildFarm
    buildfarm = BuildFarm()
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
    if opts.debug_storm:
        from storm.tracer import debug
        debug(True, stream=sys.stdout)
    httpd = make_server(address, int(port), standaloneApp)
    print "Serving on %s:%d..." % (address, int(port))
    httpd.serve_forever()
