#!/usr/bin/python
# Samba.org buildfarm
# Copyright (C) 2010 Jelmer Vernooij <jelmer@samba.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from buildfarm.sqldb import BuildFarm
import optparse
import sys

parser = optparse.OptionParser("")
parser.add_option("--tree", help="Print builds for a specific tree.", type=str)
parser.add_option("--last", help="Print last builds.", action="store_true")

(opts, args) = parser.parse_args()

buildfarm = BuildFarm()

if opts.tree:
    builds = buildfarm.get_tree_builds(opts.tree)
elif opts.last:
    builds = buildfarm.get_last_builds()
else:
    parser.print_usage()
    sys.exit(1)

for build in builds:
    print build
