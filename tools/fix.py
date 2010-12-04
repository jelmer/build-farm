#!/usr/bin/python

import bz2
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from buildfarm.build import (
    build_status_from_logs,
    LogFileMissing,
    MissingRevisionInfo,
    NoTestOutput,
    revision_from_log,
    extract_test_output,
    )
from buildfarm.hostdb import NoSuchHost

from buildfarm import BuildFarm, StormBuild

buildfarm = BuildFarm()

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
        revision = revision_from_log(log)
    except MissingRevisionInfo:
        continue
    assert revision
    build.revision = revision
    print "Updating revision for %r" % build

for build in store.find(StormBuild, StormBuild.host_id == None):
    try:
        build.host_id = buildfarm.hostdb[build.host].id
    except NoSuchHost, e:
        print "Unable to find host %s" % e.name


for build in store.find(StormBuild, StormBuild.basename != None):
    subunit_path = build.basename + ".subunit"
    if os.path.exists(subunit_path) or os.path.exists(subunit_path+".bz2"):
        continue
    try:
        test_output = "".join(extract_test_output(build.read_log()))
    except (LogFileMissing, NoTestOutput):
        continue
    print "Writing subunit file for %r" % build
    f = bz2.BZ2File(subunit_path+".bz2", 'w')
    try:
        f.write(test_output)
    finally:
        f.close()

buildfarm.commit()
