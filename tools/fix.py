#!/usr/bin/python

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from buildfarm.data import (
    build_status_from_logs,
    LogFileMissing,
    MissingRevisionInfo,
    revision_from_log,
    )

from buildfarm.sqldb import StormCachingBuildFarm, StormBuild

buildfarm = StormCachingBuildFarm()

store = buildfarm._get_store()

for build in store.find(StormBuild, StormBuild.status_str == None):
    try:
        log = build.read_log()
    except LogFileMissing:
        print "Killing build %r without status string or log." % build
        log.remove()
        continue
    try:
        err = build.read_err()
        try:
            status = build_status_from_logs(log, err)
        finally:
            err.close()
    finally:
        log.close()
    build.status_str = status.__serialize__()
    print "Updating status for %r" % build

for build in store.find(StormBuild, StormBuild.revision == None):
    try:
        log = build.read_log()
    except LogFileMissing:
        print "Killing build %r without revision or log." % build
        build.remove()
        continue
    try:
        (revision, revision_time) = revision_from_log(log)
    except MissingRevisionInfo:
        continue
    assert revision
    build.revision = revision
    print "Updating revision for %r" % build

buildfarm.commit()
