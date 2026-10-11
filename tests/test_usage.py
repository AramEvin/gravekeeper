"""View counting: the regex must match exactly one line per dashboard visit.

The log lines below are real request logs from Grafana 12.1.1 (router_logging = true)
for one browser visit to a dashboard, plus Gravekeeper's own service-account requests.
"""

import re

from gravekeeper.usage import UID_REGEX, build_query

PREFIX = "logger=context userId=1 orgId=1 uname=admin t=2026-10-11T14:35:00Z level=info "
SA = "logger=context userId=3 orgId=1 uname=sa-1-gravekeeper t=2026-10-11T14:31:02Z level=info "
SUFFIX = " status=200 remote_addr=172.18.0.1 time_ms=5 duration=5ms size=900 referer= handler=/x status_source=server"

ONE_BROWSER_VISIT = [
    "/d/gk-legacy",
    "/api/dashboards/uid/gk-legacy",
    "/api/user/orgs",
    "/api/folders/sandbox",
    "/api/dashboards/uid/gk-legacy/public-dashboards",
    "/api/annotations",
]


def _uids(lines, user_prefix=PREFIX):
    rx = re.compile(UID_REGEX)
    found = []
    for path in lines:
        line = f'{user_prefix}msg="Request Completed" method=GET path={path}{SUFFIX}'
        m = rx.search(line)
        if m:
            found.append(m.group("uid"))
    return found


def test_one_visit_counts_once():
    assert _uids(ONE_BROWSER_VISIT) == ["gk-legacy"]


def test_app_platform_api_path_is_counted():
    path = "/apis/dashboard.grafana.app/v1beta1/namespaces/default/dashboards/gk-new/dto"
    assert _uids([path]) == ["gk-new"]


def test_sub_resources_are_not_views():
    paths = ["/api/dashboards/uid/abc/versions", "/api/dashboards/uid/abc/permissions"]
    assert _uids(paths) == []


def test_query_excludes_service_accounts():
    q = build_query('{job="grafana"}', "sa-.*", 30)
    assert q.startswith("sum by (uid) (count_over_time(")
    assert 'uname!~"sa-.*"' in q and "[30d]" in q
