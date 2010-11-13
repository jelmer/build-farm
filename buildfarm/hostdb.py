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

from buildfarm import setup_db

import pysqlite2
from storm.database import create_database
from storm.store import Store
import time


class HostAlreadyExists(Exception):
    """The specified host already exists."""

    def __init__(self, name):
        super(HostAlreadyExists, self).__init__()
        self.name = name


class NoSuchHost(Exception):
    """The specified host did not exist."""

    def __init__(self, name):
        super(NoSuchHost, self).__init__()
        self.name = name


class Host(object):
    """A host in the buildfarm."""

    def __init__(self, name, owner=None, owner_email=None, password=None, platform=None,
                 ssh_access=False, last_update=None, fqdn=None):
        self.name = name
        if owner:
            self.owner = (owner, owner_email)
        else:
            self.owner = None
        self.password = password
        self.platform = platform
        self.ssh_access = ssh_access
        self.last_update = last_update
        self.fqdn = fqdn

    def __cmp__(self, other):
        return cmp(self.name, other.name)


class HostDatabase(object):
    """Host database."""

    def __init__(self, filename=None):
        if filename is None:
            self.db = create_database("sqlite:")
        else:
            self.db = create_database("sqlite:" + filename)
        self.store = Store(self.db)
        setup_db(self.store)
        self.store.flush()

    def createhost(self, name, platform=None, owner=None, owner_email=None, password=None, permission=None):
        try:
            self.store.execute("INSERT INTO host (name, platform, owner, owner_email, password, permission, join_time) VALUES (?,?,?,?,?,?,?)",
                    (name, platform, owner, owner_email, password, permission, time.time()))
        except (pysqlite2.dbapi2.IntegrityError,):
            raise HostAlreadyExists(name)
        self.store.flush()

    def deletehost(self, name):
        cursor = self.store.execute("DELETE FROM host WHERE name = ?", (name,))
        if cursor.rowcount == 0:
            raise NoSuchHost(name)
        self.store.flush()

    def hosts(self):
        cursor = self.store.execute("SELECT name, owner, owner_email, password, platform, ssh_access, fqdn FROM host ORDER BY name")
        for row in cursor:
            yield Host(name=row[0], owner=row[1], owner_email=row[2], password=row[3], platform=row[4], ssh_access=bool(row[5]), fqdn=row[6])

    def dead_hosts(self, age):
        dead_time = time.time() - age
        cursor = self.store.execute("SELECT host.name AS host, host.owner AS owner, host.owner_email AS owner_email, MAX(age) AS last_update FROM host LEFT JOIN build ON ( host.name == build.host) WHERE ifnull(last_dead_mail, 0) < %d AND ifnull(join_time, 0) < %d GROUP BY host.name having ifnull(MAX(age),0) < %d" % (dead_time, dead_time, dead_time))
        for row in cursor:
            yield Host(row[0], owner=row[1], owner_email=row[2], last_update=row[3])

    def host_ages(self):
        cursor = self.store.execute("SELECT host.name AS host, host.owner AS owner, host.owner_email AS owner_email, MAX(age) AS last_update FROM host LEFT JOIN build ON ( host.name == build.host) GROUP BY host.name ORDER BY age")
        for row in cursor:
            yield Host(row[0], owner=row[1], owner_email=row[2], last_update=row[3])

    def sent_dead_mail(self, host):
        self.store.execute("UPDATE host SET last_dead_mail = ? WHERE name = ?", (int(time.time()), host))
        self.store.flush()

    def host(self, name):
        for host in self.hosts():
            if host.name == name:
                return host
        return None

    def update_platform(self, name, new_platform):
        cursor = self.store.execute("UPDATE host SET platform = ? WHERE name = ?", (new_platform, name))
        if cursor.rowcount == 0:
            raise NoSuchHost(name)
        self.store.flush()

    def update_owner(self, name, new_owner, new_owner_email):
        cursor = self.store.execute(
            "UPDATE host SET owner = ?, owner_email = ? WHERE name = ?", (new_owner,
            new_owner_email, name))
        if cursor.rowcount == 0:
            raise NoSuchHost(name)
        self.store.flush()

    def create_rsync_secrets(self):
        """Write out the rsyncd.secrets"""
        yield "# rsyncd.secrets file\n"
        yield "# automatically generated by textfiles.pl. DO NOT EDIT!\n\n"

        for host in self.hosts():
            if host.owner:
                yield "# %s, owner: %s <%s>\n" % (host.name, host.owner[0], host.owner[1])
            else:
                yield "# %s, owner unknown\n" % (host.name,);
            if host.password:
                yield "%s:%s\n\n" % (host.name, host.password)
            else:
                yield "# %s password is unknown\n\n" % host.name

    def create_hosts_list(self):
        """Write out the web/"""

        for host in self.hosts():
            yield "%s: %s\n" % (host.name, host.platform)
