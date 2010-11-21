#!/usr/bin/python

from buildfarm.data import build_status_from_logs, LogFileMissing

from buildfarm.sqldb import StormCachingBuildFarm, StormBuild

x = StormCachingBuildFarm()

store = x._get_store()
for build in store.find(StormBuild, StormBuild.status_str == None):
    try:
        log = build.read_log()
    except LogFileMissing:
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
