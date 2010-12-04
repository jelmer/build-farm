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

from buildfarm.tree import (
    Tree,
    )
from buildfarm.build import (
    StormBuild,
    Test,
    TestResult,
    )
from buildfarm.hostdb import (
    Host,
    HostDatabase,
    HostAlreadyExists,
    NoSuchHost,
    )


try:
    from pysqlite2 import dbapi2 as sqlite3
except ImportError:
    import sqlite3
from storm.database import create_database
from storm.expr import EXPR, FuncExpr, compile
from storm.locals import Bool, Desc, Int, RawStr, Reference, Unicode
from storm.store import Store


class Cast(FuncExpr):
    __slots__ = ("column", "type")
    name = "CAST"

    def __init__(self, column, type):
        self.column = column
        self.type = type

@compile.when(Cast)
def compile_count(compile, cast, state):
    state.push("context", EXPR)
    column = compile(cast.column, state)
    state.pop()
    return "CAST(%s AS %s)" % (column, cast.type)


class StormHost(Host):
    __storm_table__ = "host"

    id = Int(primary=True)
    name = RawStr()
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

    def createhost(self, name, platform=None, owner=None, owner_email=None,
            password=None, permission=None):
        """See `HostDatabase.createhost`."""
        newhost = StormHost(name, owner=owner, owner_email=owner_email,
                password=password, permission=permission, platform=platform)
        try:
            self.store.add(newhost)
            self.store.flush()
        except sqlite3.IntegrityError:
            raise HostAlreadyExists(name)
        return newhost

    def deletehost(self, name):
        """Remove a host."""
        self.store.remove(self[name])

    def hosts(self):
        """Retrieve an iterable over all hosts."""
        return self.store.find(StormHost).order_by(StormHost.name)

    def __getitem__(self, name):
        result = self.store.find(StormHost,
            Cast(StormHost.name, "TEXT") == Cast(name, "TEXT"))
        ret = result.one()
        if ret is None:
            raise NoSuchHost(name)
        return ret

    def commit(self):
        self.store.commit()


def distinct_builds(builds):
    done = set()
    for build in builds:
        key = (build.tree, build.compiler, build.host)
        if key in done:
            continue
        done.add(key)
        yield build


class StormTree(Tree):
    __storm_table__ = "tree"

    id = Int(primary=True)
    name = RawStr()
    scm = Int()
    branch = RawStr()
    subdir = RawStr()
    repo = RawStr()
    scm = RawStr()


class StormTest(Test):
    __storm_table__ = "test"

    id = Int(primary=True)
    name = RawStr()


class StormTestResult(TestResult):
    __storm_table__ = "test_result"

    id = Int(primary=True)
    build_id = Int(name="build")
    build = Reference(build_id, StormBuild)

    test_id = Int(name="test")
    test = Reference(test_id, StormTest)


def setup_schema(db):
    db.execute("PRAGMA foreign_keys = 1;", noresult=True)
    db.execute("""
CREATE TABLE IF NOT EXISTS host (
    id integer primary key autoincrement,
    name blob not null,
    owner text,
    owner_email text,
    password text,
    ssh_access int,
    fqdn text,
    platform text,
    permission text,
    last_dead_mail int,
    join_time int
);""", noresult=True)
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS unique_hostname ON host (name);", noresult=True)
    db.execute("""
CREATE TABLE IF NOT EXISTS build (
    id integer primary key autoincrement,
    tree blob not null,
    tree_id int,
    revision blob,
    host blob not null,
    host_id integer,
    compiler blob not null,
    compiler_id int,
    checksum blob,
    age int,
    status blob,
    basename blob,
    FOREIGN KEY (host_id) REFERENCES host (id),
    FOREIGN KEY (tree_id) REFERENCES tree (id),
    FOREIGN KEY (compiler_id) REFERENCES compiler (id)
);""", noresult=True)
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS unique_checksum ON build (checksum);", noresult=True)
    db.execute("""
CREATE TABLE IF NOT EXISTS tree (
    id integer primary key autoincrement,
    name blob not null,
    scm int,
    branch blob,
    subdir blob,
    repo blob
    );
    """, noresult=True)
    db.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS unique_tree_name ON tree(name);
""", noresult=True)
    db.execute("""
CREATE TABLE IF NOT EXISTS compiler (
    id integer primary key autoincrement,
    name blob not null
    );
    """, noresult=True)
    db.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS unique_compiler_name ON compiler(name);
""", noresult=True)
    db.execute("""
CREATE TABLE IF NOT EXISTS test (
    id integer primary key autoincrement,
    name text not null);
    """, noresult=True)
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS test_name ON test(name);",
        noresult=True)
    db.execute("""CREATE TABLE IF NOT EXISTS test_result (
        build int,
        test int,
        result int
        );""", noresult=True)
    db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS build_test_result ON test_result(build, test);""", noresult=True)


def memory_store():
    db = create_database("sqlite:")
    store = Store(db)
    setup_schema(store)
    return store
