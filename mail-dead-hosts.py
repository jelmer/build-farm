#!/usr/bin/python
# Samba.org buildfarm
# Copyright (C) 2008 Andrew Bartlett <abartlet@samba.org>
# Copyright (C) 2008-2010 Jelmer Vernooij <jelmer@samba.org>
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

from buildfarm import (
    BuildFarm,
    )
import smtplib
from email.MIMEText import MIMEText
import time

buildfarm = BuildFarm()
db = buildfarm.hostdb
dry_run = False

hosts = db.dead_hosts(7 * 86400)
for host in hosts:
    db.sent_dead_mail(host.name)

    if host.last_update:
        last_update = time.strftime ("%a %b %e %H:%M:%S %Y", time.gmtime(host.last_update))
    else:
        last_update = "a long time"

    body = """
Your host %s has been part of the Samba Build farm, hosted
at http://build.samba.org.

Sadly however we have not heard from it since %s.

Could you see if something has changed recently, and examine the logs
(typically in ~build/build_farm/build.log and ~build/cron.err) to see
why we have not heard from your host?

If you no longer wish your host to participate in the Samba Build
Farm, then please let us know so we can remove its records.

You can see the summary for your host at:
http://build.samba.org/?function=View+Host;host=%s

Thanks,

The Build Farm administration team.

""" % (host.name, last_update, host.name)

    msg = MIMEText(body)

    # send an e-mail to the owner
    msg["Subject"] ="Your build farm host %s appears dead" % host.name
    msg["From"] = "\"Samba Build Farm\" <build@samba.org>"
    msg["To"] = "\"%s\" <%s>" % host.owner

    if dry_run:
        print msg.as_string()
    else:
        s = smtplib.SMTP()
        s.connect()
        s.send(msg["From"], [msg["To"]], msg.as_string())
        s.quit()
