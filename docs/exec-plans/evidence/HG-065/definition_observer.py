"""Observe actual pytest collection/start/phase identities for this author study."""
import json
import os
from pathlib import Path
STATE={'collections':[],'started':[],'reports':[],'errors':[],'exit_code':None}


def pytest_collection_finish(session):
    STATE['collections']=[i.nodeid for i in session.items]


def pytest_runtest_logstart(nodeid,location):
    STATE['started'].append(nodeid)


def pytest_runtest_logreport(report):
    STATE['reports'].append({'nodeid':report.nodeid,'when':report.when,'outcome':report.outcome,
                             'wasxfail':getattr(report,'wasxfail',None)})


def pytest_collectreport(report):
    if report.failed:STATE['errors'].append(str(report.longrepr))


def pytest_sessionfinish(session,exitstatus):
    STATE['exit_code']=int(exitstatus)
    Path(os.environ['CUSTODY_STUDY_OBSERVER']).write_text(json.dumps(STATE,separators=(',',':'))+'\n')
