#!/usr/bin/python
# Simple database query script for the buildfarm
#
# Copyright (C) Jelmer Vernooij <jelmer@samba.org>	   2010
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
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

from buildfarm import (
    BuildFarm,
    util,
    )
from buildfarm.data import (
    Build,
    BuildResultStore,
    BuildStageResult,
    BuildStatus,
    NoSuchBuildError,
    UploadBuildResultStore,
    check_dir_exists,
    )

import os


class CachingBuild(Build):
    """Build subclass that caches some of the results that are expensive
    to calculate."""

    def __init__(self, store, *args, **kwargs):
        self._store = store
        super(CachingBuild, self).__init__(*args, **kwargs)
        if self.revision:
            self.cache_basename = self._store.cache_fname(self.tree, self.host, self.compiler, self.revision)
        else:
            self.cache_basename = self._store.cache_fname(self.tree, self.host, self.compiler)

    def revision_details(self):
        st1 = os.stat("%s.log" % self.basename)

        try:
            st2 = os.stat("%s.revision" % self.cache_basename)
        except OSError:
            # File does not exist
            st2 = None

        # the ctime/mtime asymmetry is needed so we don't get fooled by
        # the mtime update from rsync
        if st2 and st1.st_ctime <= st2.st_mtime:
            (revid, timestamp) = util.FileLoad("%s.revision" % self.cache_basename).split(":", 2)
            if timestamp == "":
                timestamp = None
            if revid == "":
                revid = None
            return (revid, timestamp)
        (revid, timestamp) = super(CachingBuild, self).revision_details()
        if not self._store.readonly:
            util.FileSave("%s.revision" % self.cache_basename, "%s:%s" % (revid, timestamp or ""))
        return (revid, timestamp)

    def err_count(self):
        st1 = os.stat("%s.err" % self.basename)

        try:
            st2 = os.stat("%s.errcount" % self.cache_basename)
        except OSError:
            # File does not exist
            st2 = None

        if st2 and st1.st_ctime <= st2.st_mtime:
            return util.FileLoad("%s.errcount" % self.cache_basename)

        ret = super(CachingBuild, self).err_count()

        if not self._store.readonly:
            util.FileSave("%s.errcount" % self.cache_basename, str(ret))

        return ret

    def status(self):
        cachefile = self.cache_basename + ".status"

        st1 = os.stat("%s.log" % self.basename)

        try:
            st2 = os.stat(cachefile)
        except OSError:
            # No such file
            st2 = None

        if st2 and st1.st_ctime <= st2.st_mtime:
            return eval(util.FileLoad(cachefile))

        ret = super(CachingBuild, self).status()

        if not self._store.readonly:
            util.FileSave(cachefile, repr(ret))

        return ret


class CachingUploadBuildResultStore(UploadBuildResultStore):

    def __init__(self, basedir, cachedir, readonly=False):
        """Open the database.

        :param readonly: Whether to avoid saving cache files
        """
        super(CachingUploadBuildResultStore, self).__init__(basedir)
        self.cachedir = cachedir
        self.readonly = readonly

    def cache_fname(self, tree, host, compiler):
        return os.path.join(self.cachedir, "build.%s.%s.%s" % (tree, host, compiler))

    def get_build(self, tree, host, compiler):
        basename = self.build_fname(tree, host, compiler)
        logf = "%s.log" % basename
        if not os.path.exists(logf):
            raise NoSuchBuildError(tree, host, compiler)
        return CachingBuild(self, basename, tree, host, compiler)


class CachingBuildResultStore(BuildResultStore):

    def __init__(self, basedir, cachedir, readonly=False):
        super(CachingBuildResultStore, self).__init__(basedir)

        self.cachedir = cachedir
        check_dir_exists("cache", self.cachedir)

        self.readonly = readonly

    def get_build(self, tree, host, compiler, rev):
        basename = self.build_fname(tree, host, compiler, rev)
        logf = "%s.log" % basename
        if not os.path.exists(logf):
            raise NoSuchBuildError(tree, host, compiler, rev)
        return CachingBuild(self, basename, tree, host, compiler, rev)

    def cache_fname(self, tree, host, compiler, rev):
        return os.path.join(self.cachedir, "build.%s.%s.%s-%s" % (tree, host, compiler, rev))


class CachingBuildFarm(BuildFarm):

    def __init__(self, path=None, readonly=False, cachedirname=None):
        self._cachedirname = cachedirname
        self.readonly = readonly
        super(CachingBuildFarm, self).__init__(path)

    def _get_cachedir(self):
        if self._cachedirname is not None:
            return os.path.join(self.path, self._cachedirname)
        else:
            return os.path.join(self.path, "cache")

    def _open_build_results(self):
        return CachingBuildResultStore(os.path.join(self.path, "data", "oldrevs"),
                self._get_cachedir(), readonly=self.readonly)

    def _open_upload_build_results(self):
        return CachingUploadBuildResultStore(os.path.join(self.path, "data", "upload"),
                self._get_cachedir(), readonly=self.readonly)

    def lcov_status(self, tree):
        """get status of build"""
        cachefile = os.path.join(self._get_cachedir(),
                                    "lcov.%s.%s.status" % (self.LCOVHOST, tree))
        file = os.path.join(self.lcovdir, self.LCOVHOST, tree, "index.html")
        try:
            st1 = os.stat(file)
        except OSError:
            # File does not exist
            raise NoSuchBuildError(tree, self.LCOVHOST, "lcov")
        try:
            st2 = os.stat(cachefile)
        except OSError:
            # file does not exist
            st2 = None

        if st2 and st1.st_ctime <= st2.st_mtime:
            ret = util.FileLoad(cachefile)
            if ret == "":
                return None
            return ret

        perc = super(CachingBuildFarm, self).lcov_status(tree)
        if not self.readonly:
            util.FileSave(cachefile, perc)
        return perc
