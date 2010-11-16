#!/usr/bin/python
# This CGI script presents the results of the build_farm build

# Copyright (C) Jelmer Vernooij <jelmer@samba.org>     2010
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

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from buildfarm.sqldb import StormCachingBuildFarm
from buildfarm.web import BuildFarmApp
import wsgiref.handlers
import resource

resource.setrlimit(resource.RLIMIT_RSS, (300000, 300000))
resource.setrlimit(resource.RLIMIT_DATA, (300000, 300000))

buildfarm = StormCachingBuildFarm()
buildApp = BuildFarmApp(buildfarm)
handler = wsgiref.handlers.CGIHandler()
CGI_DEBUG = False

if CGI_DEBUG:
    import cgitb
    cgitb.enable()
    handler.log_exception = cgitb.handler
handler.run(buildApp)
