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

from buildfarm import (
    BuildFarm,
    )
from buildfarm.data import (
    Build,
    BuildResultStore,
    NoSuchBuildError,
    )
from buildfarm.hostdb import (
    Host,
    HostDatabase,
    HostAlreadyExists,
    NoSuchHost,
    )

import os
import pysqlite2
from storm.database import create_database
from storm.locals import Bool, Desc, Int, Unicode, RawStr
from storm.store import Store


class StormBuild(Build):
    __storm_table__ = "build"

    id = Int(primary=True)
    tree = Unicode()
    revision = RawStr()
    host = Unicode()
    compiler = Unicode()
    checksum = RawStr()
    age = Int()
    status = Unicode()
    commit_revision = RawStr()

    def remove(self):
        super(StormBuild, self).remove()
        Store.of(self).remove(self)


class StormHost(Host):
    __storm_table__ = "host"

    name = Unicode(primary=True)
    owner_name = Unicode(name="owner")
    owner_email = Unicode()
    password = Unicode()
    ssh_access = Bool()
    fqdn = RawStr()
    platform = Unicode()
    permission = Unicode()
    last_dead_mail = Int()
    join_time = Int()

    def _set_owner(self, value):
        if value is None:
            self.owner_name = None
            self.owner_email = None
        else:
            (self.owner_name, self.owner_email) = value

    def _get_owner(self):
        if self.owner_name is None:
            return None
        else:
            return (self.owner_name, self.owner_email)

    owner = property(_get_owner, _set_owner)


class StormHostDatabase(HostDatabase):

    def __init__(self, store=None):
        if store is None:
            self.store = memory_store()
        else:
            self.store = store

    def createhost(self, name, platform=None, owner=None, owner_email=None, password=None, permission=None):
        newhost = StormHost(unicode(name), owner=owner, owner_email=owner_email, password=password, permission=permission, platform=platform)
        try:
            self.store.add(newhost)
            self.store.flush()
        except pysqlite2.dbapi2.IntegrityError:
            raise HostAlreadyExists(name)
        return newhost

    def deletehost(self, name):
        """Remove a host."""
        host = self.host(name)
        self.store.remove(host)

    def hosts(self):
        """Retrieve an iterable over all hosts."""
        return self.store.find(StormHost).order_by(StormHost.name)

    def host(self, name):
        ret = self.hosts().find(StormHost.name==name).one()
        if ret is None:
            raise NoSuchHost(name)
        return ret

    def commit(self):
        self.store.commit()


class StormCachingBuildResultStore(BuildResultStore):

    def __init__(self, basedir, store=None):
        super(StormCachingBuildResultStore, self).__init__(basedir)

        if store is None:
            store = memory_store()

        self.store = store

    def get_previous_revision(self, tree, host, compiler, revision):
        result = self.store.find(StormBuild,
            StormBuild.tree == unicode(tree),
            StormBuild.host == unicode(host),
            StormBuild.compiler == unicode(compiler),
            StormBuild.commit_revision == revision)
        cur_build = result.any()
        if cur_build is None:
            raise NoSuchBuildError(tree, host, compiler, revision)

        result = self.store.find(StormBuild,
            StormBuild.tree == unicode(tree),
            StormBuild.host == unicode(host),
            StormBuild.compiler == unicode(compiler),
            StormBuild.commit_revision != revision,
            StormBuild.id < cur_build.id)
        result = result.order_by(Desc(StormBuild.id))
        prev_build = result.first()
        if prev_build is None:
            raise NoSuchBuildError(tree, host, compiler, revision)
        return prev_build.commit_revision

    def get_latest_revision(self, tree, host, compiler):
        result = self.store.find(StormBuild,
            StormBuild.tree == unicode(tree),
            StormBuild.host == unicode(host),
            StormBuild.compiler == unicode(compiler))
        result = result.order_by(Desc(StormBuild.id))
        build = result.first()
        if build is None:
            raise NoSuchBuildError(tree, host, compiler)
        return build.revision

    def upload_build(self, build):
        super(StormCachingBuildResultStore, self).upload_build(build)
        rev, timestamp = build.revision_details()
        new_basename = self.build_fname(build.tree, build.host, build.compiler, rev)
        new_build = StormBuild(new_basename, unicode(build.tree), unicode(build.host), unicode(build.compiler), rev)
        new_build.checksum = build.log_checksum()
        new_build.age = build.age_mtime()
        new_build.status = unicode(str(build.status()))
        self.store.add(new_build)


class StormCachingBuildFarm(BuildFarm):

    def __init__(self, path=None, store=None):
        self.store = store
        super(StormCachingBuildFarm, self).__init__(path)

    def _get_store(self):
        if self.store is not None:
            return self.store
        else:
            db = create_database("sqlite:" + os.path.join(self.path, "hostdb.sqlite"))
            self.store = Store(db)
            setup_schema(self.store)
            return self.store

    def _open_hostdb(self):
        return StormHostDatabase(self._get_store())

    def _open_build_results(self):
        return StormCachingBuildResultStore(os.path.join(self.path, "data", "oldrevs"),
            self._get_store())

    def commit(self):
        self.store.commit()


def setup_schema(db):
    db.execute("CREATE TABLE IF NOT EXISTS host (name text, owner text, owner_email text, password text, ssh_access int, fqdn text, platform text, permission text, last_dead_mail int, join_time int);", noresult=True)
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS unique_hostname ON host (name);", noresult=True)
    db.execute("CREATE TABLE IF NOT EXISTS build (id integer primary key autoincrement, tree text, revision text, host text, compiler text, checksum text, age int, status text, commit_revision text);", noresult=True)
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS unique_checksum ON build (checksum);", noresult=True)


def memory_store():
    db = create_database("sqlite:")
    store = Store(db)
    setup_schema(store)
    return store