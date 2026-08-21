"""
data/latest.json (이번 달) 과 data/archive/*.json (과거 달)을 읽어서, 지표별(별풍선/방송시간)로
docs/index.html·docs/broadcast.html (이번 달) + docs/archive/YYYY-MM.html·
docs/archive-broadcast/YYYY-MM.html (과거 달) 로 렌더링하는 스크립트.
추가로 SINGLE_TEAM_PAGES에 지정된 팀만 docs/teams/{팀이름}[-broadcast].html (이번 달) +
docs/teams/{팀이름}[-broadcast]__YYYY-MM.html (과거 달) 단독 페이지로도 생성한다.

별풍선(BALLOON_METRIC)과 방송시간(BROADCAST_METRIC) 페이지는 레이아웃이 동일하지만,
방송시간 페이지는 수장/전력외 직책도 합계·평균 집계에 포함한다는 점만 다르다
(Metric.exclude_roles 값으로 제어).

과거 달 데이터는 fetch_data.py가 달이 바뀔 때 그 달 기준으로 API를 한 번 더 호출해
확정된 별풍선 값으로 갱신한 뒤 data/archive/에 보관해둔 것 - 그 시점의 team/gender/role이
멤버마다 그대로 들어있어서 팀 구성이 바뀌어도 "그 당시 배정" 그대로 재현된다.

팀별 표: 표 1개, [남자 멤버 | 별풍선 | 여자 멤버 | 별풍선] 4열, 각각 별풍선 내림차순 정렬.
하단에 합계/평균/인원 행 포함. 별풍선 0이거나 직책이 수장/전력외인 사람은 집계·상위% 계산에서 제외
(수장/전력외는 표에 빨간 배경으로 표시, 0인 사람은 빈 칸으로 표시).
이름 옆에는 그 달의 생일이면 🎂 표시.
상단 왼쪽의 "YYYY년 MM월" 글씨가 드롭다운 역할을 해서 다른 달로 바로 이동 가능.

실행: python scripts/generate_html.py
"""

import json
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "latest.json"
ARCHIVE_DIR = ROOT / "data" / "archive"
OUTPUT_PATH = ROOT / "docs" / "index.html"
OUTPUT_ARCHIVE_DIR = ROOT / "docs" / "archive"
OUTPUT_BROADCAST_PATH = ROOT / "docs" / "broadcast.html"
OUTPUT_ARCHIVE_BROADCAST_DIR = ROOT / "docs" / "archive-broadcast"
OUTPUT_TEAMS_DIR = ROOT / "docs" / "teams"
LOGOS_DIR = ROOT / "docs" / "logos"

EXCLUDED_ROLES = {"수장", "전력외"}

# 팀별 단독 페이지(docs/teams/)를 만들 팀 목록. 필요한 팀 이름만 여기 추가하면 됨.
SINGLE_TEAM_PAGES = ["캄몬스타즈"]

ARCHIVE_BANNER_HTML = "<div class='archive-banner'>📁 이 페이지는 지난 기록입니다 (당시 팀 구성 기준)</div>"


def normalize_balloons(members: list) -> list:
    """balloons/broadcast_seconds 값이 문자열 등으로 저장돼있어도 항상 int로 안전하게
    맞춰준다 (크롤링 스크립트가 정수로 저장해도, 예전 데이터 파일이 남아있는 경우 대비)."""
    for m in members:
        for field in ("balloons", "broadcast_seconds"):
            raw = m.get(field, 0)
            if not isinstance(raw, int):
                try:
                    m[field] = int(str(raw).replace(",", "").strip() or 0)
                except (ValueError, TypeError):
                    m[field] = 0
    return members

# 모든 페이지가 공유하는 스타일. f-string이 아니라 일반 문자열이라 중괄호를 그대로 쓴다.
PAGE_CSS = """
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');

  * { box-sizing: border-box; }

  body {
    font-family: 'Noto Sans KR', -apple-system, "Malgun Gothic", sans-serif;
    background: #f2f3f5;
    margin: 0;
    padding: 24px 16px;
    color: #222;
  }
  .top-bar {
    max-width: 1080px;
    margin: 0 auto 18px;
    background: #fff;
    border: 1px solid #e2e4e9;
    border-left: 5px solid #25528F;
    border-radius: 8px;
    padding: 14px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }
  .top-date-select {
    font-size: 18px;
    font-weight: 700;
    color: #222;
    border: none;
    background: transparent;
    cursor: pointer;
    font-family: inherit;
    padding: 2px 0;
  }
  .top-date-select:hover { color: #25528F; }
  .top-meta {
    font-size: 10px;
    color: #888;
  }
  .source-link {
    color: #888;
    text-decoration: underline;
  }
  .source-link:hover { color: #25528F; }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 14px;
    max-width: 1080px;
    margin: 0 auto;
  }
  .grid.single-team {
    grid-template-columns: 1fr;
    max-width: 480px;
  }
  .team-card {
    background: #fff;
    border: 1px solid #e5e6ea;
    border-radius: 10px;
    padding: 10px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }
  th.team-name-row {
    background: #f7f8fa;
    color: #222;
    font-weight: 700;
  }
  .team-name-inner {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    overflow: hidden;
    min-width: 0;
  }
  .team-name-flex {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
    flex-wrap: nowrap;
    overflow: hidden;
  }
  .rank-change {
    font-size: 11px;
    font-weight: 700;
    padding: 1px 7px;
    border-radius: 10px;
    white-space: nowrap;
  }
  .rank-change.up { color: #1a7f37; background: #e6f4ea; }
  .rank-change.down { color: #c0392b; background: #fdeaea; }
  .rank-change.same { color: #888; background: #eceef1; }
  .rank-change.new { color: #25528F; background: #e3e7fb; }
  .team-logo {
    height: 14px;
    width: 14px;
    object-fit: contain;
    vertical-align: middle;
  }
  th.col-header {
    background: #25528F;
    color: #fff;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
    table-layout: fixed;
  }
  th, td {
    border: 1px solid #eceef1;
    padding: 3px 4px;
    text-align: center;
    vertical-align: middle;
    height: 25px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  th {
    background: #f7f8fa;
    font-weight: 700;
    color: #555;
  }
  td.name-td {
    text-align: center;
    background: #f7f8fa;
  }
  .name-cell {
    position: relative;
    text-align: center;
    min-height: 14px;
  }
  .name-left { white-space: nowrap; font-weight: 700; }
  .bday-mark {
    position: absolute;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    font-size: 9px;
  }

  td.num {
    text-align: center;
    font-variant-numeric: tabular-nums;
    font-weight: 500;
  }
  td.empty { background: #fff; }

  td.excluded {
    background: #fadada !important;
    color: #222;
    font-weight: 700;
  }
  td.tier1, td.tier5, td.tier10 { font-weight: 700; }
  td.tier1 { background: #d6e9fb; }
  td.tier5 { background: #dcefdd; }
  td.tier10 { background: #fbf3cf; }
  td.excluded.tier1, td.excluded.tier5, td.excluded.tier10 {
    background: #fadada !important;
  }

  tr.summary-row td {
    font-size: 11px;
    background: #fafbfc;
    font-weight: 600;
    text-align: center;
    height: 25px;
    vertical-align: middle;
  }
  td.total-sum, td.total-avg { background: #CDD7F5 !important; font-weight: 700; }
  td.female-avg { background: #CDE1E1 !important; font-weight: 700; }
  td.personnel-label { background: #f7f8fa !important; }
  td.personnel-value { background: #ffffff !important; }

  .legend {
    max-width: 1080px;
    margin: 14px auto 0;
    font-size: 9px;
    color: #888;
    text-align: center;
  }
  .legend span { margin: 0 5px; }
  .legend .sw {
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 2px;
    margin-right: 3px;
    vertical-align: middle;
  }

  .archive-banner {
    max-width: 1080px;
    margin: 0 auto 14px;
    text-align: center;
    font-size: 12px;
    color: #a15c1f;
    background: #fff3e0;
    border: 1px solid #f0cf9a;
    border-radius: 8px;
    padding: 6px;
  }

  /* 팀 단독 페이지에는 이 블록을 넣지 않음 (모바일에서도 PC와 동일한 크기로 표시) */
"""

MOBILE_CSS = """
  /* 모바일: 한 줄에 2팀씩 보이도록 강제 2열 + 여백/폰트 축소 */
  @media (max-width: 600px) {
    body { padding: 12px 6px; }
    .grid {
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }
    .team-card {
      padding: 5px;
      border-radius: 7px;
    }
    table { font-size: 6px; }
    th, td { padding: 1px 1px; height: 14px; }
    tr.summary-row td { font-size: 6px; padding: 1px 1px; height: 14px; }
    .name-cell { min-height: 8px; }
    .name-left { font-size: 6px; }
    .bday-mark { font-size: 5px; }
    .team-logo { height: 8px; width: 8px; }
    .rank-change { font-size: 6px; padding: 1px 4px; }
    .top-bar { padding: 10px 14px; }
    .top-date-select { font-size: 10px; }
    .top-meta { font-size: 5px; }
    .legend { font-size: 4px; }
  }
"""


def fmt(n: int) -> str:
    return f"{n:,}"


def format_broadcast_time(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class Metric:
    """페이지가 다루는 지표(별풍선/방송시간)를 표현. 값 필드명, 집계시 직책 제외 여부,
    표시용 포맷터, 표에 쓸 이름을 갖는다. 새 지표를 추가하고 싶으면 이 클래스의
    인스턴스를 하나 더 만들면 된다."""

    def __init__(self, field: str, exclude_roles: bool, format_fn, unit_label: str):
        self.field = field
        self.exclude_roles = exclude_roles
        self.format_fn = format_fn
        self.unit_label = unit_label

    def raw_value(self, m) -> int:
        return m.get(self.field, 0) or 0

    def text(self, m) -> str:
        v = self.raw_value(m)
        return self.format_fn(v) if v else ""


# 별풍선 페이지(기존): 수장/전력외 직책은 집계에서 제외
BALLOON_METRIC = Metric(field="balloons", exclude_roles=True, format_fn=fmt, unit_label="별풍선")
# 방송시간 페이지(신규): 수장/전력외도 집계에 포함
BROADCAST_METRIC = Metric(field="broadcast_seconds", exclude_roles=False, format_fn=format_broadcast_time, unit_label="방송시간")


def parse_birthdate(bd):
    if not bd:
        return None
    try:
        parts = bd.split("-")
        return int(parts[1]), int(parts[2])
    except (IndexError, ValueError):
        return None


def is_counted(m, metric: Metric = BALLOON_METRIC):
    if metric.exclude_roles and m.get("role") in EXCLUDED_ROLES:
        return False
    return metric.raw_value(m) != 0


def compute_percentile_tiers(members: list, metric: Metric = BALLOON_METRIC):
    pool = [m for m in members if is_counted(m, metric)]
    ranked = sorted(pool, key=lambda m: -metric.raw_value(m))
    n = len(ranked)
    if n == 0:
        return {}

    top1_n = max(1, round(n * 0.01))
    top5_n = max(1, round(n * 0.05))
    top10_n = max(1, round(n * 0.10))

    tiers = {}
    for idx, m in enumerate(ranked):
        key = (m["nickname"], m["team"])
        if idx < top1_n:
            tiers[key] = "tier1"
        elif idx < top5_n:
            tiers[key] = "tier5"
        elif idx < top10_n:
            tiers[key] = "tier10"
    return tiers


def group_teams(members: list) -> OrderedDict:
    teams = OrderedDict()
    for m in members:
        teams.setdefault(m.get("team", "미분류"), []).append(m)
    return teams


def team_total_avg(team_members: list, metric: Metric = BALLOON_METRIC) -> int:
    """전체 평균 계산 - build_team_card와 동일 로직(지표별 집계 규칙 적용)"""
    counted = [m for m in team_members if is_counted(m, metric)]
    total_sum = sum(metric.raw_value(m) for m in counted)
    return round(total_sum / len(counted)) if counted else 0


def compute_team_ranks(members: list, metric: Metric = BALLOON_METRIC) -> dict:
    """팀별 전체 평균 기준 순위 (1위가 가장 높음)"""
    teams = group_teams(members)
    avgs = [(team_name, team_total_avg(team_members, metric)) for team_name, team_members in teams.items()]
    avgs.sort(key=lambda x: -x[1])
    return {team_name: idx + 1 for idx, (team_name, _) in enumerate(avgs)}


def previous_month_slug(year: int, month: int) -> str:
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def load_previous_ranks(year: int, month: int, metric: Metric = BALLOON_METRIC):
    """해당 연/월의 '전달'에 해당하는 보관 데이터를 찾아 팀 순위를 계산. 없으면 None."""
    slug = previous_month_slug(year, month)
    path = ARCHIVE_DIR / f"{slug}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        prev_data = json.load(f)
    return compute_team_ranks(normalize_balloons(prev_data["members"]), metric)


def rank_change_badge(current_rank: int, prev_ranks, team_name: str) -> str:
    """전달 대비 순위 변동 뱃지 HTML. 비교 불가능하면 빈 문자열."""
    if prev_ranks is None:
        return ""
    if team_name not in prev_ranks:
        return "<span class='rank-change new'>NEW</span>"
    prev_rank = prev_ranks[team_name]
    if current_rank < prev_rank:
        return f"<span class='rank-change up'>▲{prev_rank - current_rank}</span>"
    elif current_rank > prev_rank:
        return f"<span class='rank-change down'>▼{current_rank - prev_rank}</span>"
    return "<span class='rank-change same'>-</span>"


def name_cell(m, current_month):
    bday = parse_birthdate(m.get("birthdate"))
    bday_html = "<span class='bday-mark'>🎂</span>" if bday and bday[0] == current_month else ""
    return (
        f"<div class='name-cell'>"
        f"<span class='name-left'>{m['nickname']}</span>"
        f"{bday_html}"
        f"</div>"
    )


def value_class(m, tiers, metric: Metric = BALLOON_METRIC):
    """metric.exclude_roles가 True인 페이지(별풍선)에서만 수장/전력외를 빨간 배경으로
    강조한다 - 방송시간 페이지는 집계에 포함되므로 굳이 예외처럼 표시하지 않는다."""
    classes = []
    if metric.exclude_roles and m.get("role") in EXCLUDED_ROLES:
        classes.append("excluded")
    tier = tiers.get((m["nickname"], m["team"]))
    if tier:
        classes.append(tier)
    return " ".join(classes)


def team_logo_html(team_name: str, logo_prefix: str) -> str:
    """docs/logos/{팀이름}.webp 파일이 실제로 있으면 <img> 태그를, 없으면 빈 문자열을 반환"""
    logo_path = LOGOS_DIR / f"{team_name}.webp"
    if not logo_path.exists():
        return ""
    src = f"{logo_prefix}logos/{team_name}.webp"
    return f"<img src='{src}' class='team-logo' alt=''>"


def build_team_card(team_name: str, members: list, current_month: int, tiers: dict,
                     logo_prefix: str = "", rank_badge: str = "", metric: Metric = BALLOON_METRIC):
    males_all = sorted([m for m in members if m["gender"] == "m"], key=lambda x: -metric.raw_value(x))
    females_all = sorted([m for m in members if m["gender"] == "f"], key=lambda x: -metric.raw_value(x))

    males_counted = [m for m in males_all if is_counted(m, metric)]
    females_counted = [m for m in females_all if is_counted(m, metric)]

    male_sum = sum(metric.raw_value(m) for m in males_counted)
    female_sum = sum(metric.raw_value(m) for m in females_counted)
    total_sum = male_sum + female_sum
    male_avg = round(male_sum / len(males_counted)) if males_counted else 0
    female_avg = round(female_sum / len(females_counted)) if females_counted else 0
    total_avg = team_total_avg(members, metric)  # 순위 계산과 동일한 공식(team_total_avg)을 그대로 재사용

    max_rows = max(len(males_all), len(females_all), 1)

    body_rows = []
    for i in range(max_rows):
        if i < len(males_all):
            m = males_all[i]
            m_name = f"<td class='name-td'>{name_cell(m, current_month)}</td>"
            m_val = f"<td class='num {value_class(m, tiers, metric)}'>{metric.text(m)}</td>"
        else:
            m_name = "<td class='name-td empty'></td>"
            m_val = "<td class='num empty'></td>"

        if i < len(females_all):
            f_ = females_all[i]
            f_name = f"<td class='name-td'>{name_cell(f_, current_month)}</td>"
            f_val = f"<td class='num {value_class(f_, tiers, metric)}'>{metric.text(f_)}</td>"
        else:
            f_name = "<td class='name-td empty'></td>"
            f_val = "<td class='num empty'></td>"

        body_rows.append(f"<tr>{m_name}{m_val}{f_name}{f_val}</tr>")

    body_html = "".join(body_rows)

    male_n, female_n = len(males_all), len(females_all)
    total_n = male_n + female_n

    summary_html = f"""
      <tr class="summary-row">
        <td>남자 합계</td><td class="num">{metric.format_fn(male_sum)}</td>
        <td>여자 합계</td><td class="num">{metric.format_fn(female_sum)}</td>
      </tr>
      <tr class="summary-row">
        <td>남자 평균</td><td class="num">{metric.format_fn(male_avg)}</td>
        <td>여자 평균</td><td class="num female-avg">{metric.format_fn(female_avg)}</td>
      </tr>
      <tr class="summary-row">
        <td>전체 합계</td><td class="num total-sum">{metric.format_fn(total_sum)}</td>
        <td>전체 평균</td><td class="num total-avg">{metric.format_fn(total_avg)}</td>
      </tr>
      <tr class="summary-row">
        <td class="personnel-label">인원</td>
        <td colspan="3" class="personnel-value">총 {total_n}명 / 남자 {male_n}명 / 여자 {female_n}명</td>
      </tr>
    """

    logo_html = team_logo_html(team_name, logo_prefix)

    if rank_badge:
        name_row_inner = (
            f"<div class='team-name-flex'>"
            f"<span class='team-name-inner'>{logo_html}{team_name}</span>"
            f"{rank_badge}"
            f"</div>"
        )
    else:
        name_row_inner = f"<span class='team-name-inner'>{logo_html}{team_name}</span>"

    return total_avg, f"""
    <div class="team-card">
      <table>
        <thead>
          <tr><th colspan="4" class="team-name-row">{name_row_inner}</th></tr>
          <tr><th class="col-header">남자 멤버</th><th class="col-header">{metric.unit_label}</th><th class="col-header">여자 멤버</th><th class="col-header">{metric.unit_label}</th></tr>
        </thead>
        <tbody>
          {body_html}
          {summary_html}
        </tbody>
      </table>
    </div>
    """


def list_archive_slugs() -> list:
    """data/archive/YYYY-MM.json 파일들에서 'YYYY-MM' 슬러그 목록을 최신순으로 반환"""
    if not ARCHIVE_DIR.exists():
        return []
    slugs = [p.stem for p in ARCHIVE_DIR.glob("*.json")]
    return sorted(slugs, reverse=True)


def _build_select_html(archive_slugs: list, current_year: int, current_month: int,
                        active_slug: str, current_href_fn, archive_href_fn) -> str:
    """
    'YYYY년 MM월' 드롭다운 공통 로직. current_href_fn()/archive_href_fn(slug)로
    페이지 종류(전체/팀별)에 따라 다른 링크 계산 방식만 바꿔 끼운다.
    """
    current_slug = f"{current_year:04d}-{current_month:02d}"
    options = []

    label = f"{current_year}년 {current_month:02d}월"
    selected = " selected" if active_slug == current_slug else ""
    options.append(f"<option value='{current_href_fn()}'{selected}>{label}</option>")

    for slug in archive_slugs:
        year, month = slug.split("-")
        label = f"{year}년 {int(month):02d}월"
        selected = " selected" if slug == active_slug else ""
        options.append(f"<option value='{archive_href_fn(slug)}'{selected}>{label}</option>")

    options_html = "".join(options)
    return (
        "<select class='top-date-select' "
        "onchange=\"if(this.value) window.location.href=this.value;\">"
        f"{options_html}</select>"
    )


def build_month_select(archive_slugs: list, current_year: int, current_month: int,
                        active_slug: str, is_archive_page: bool,
                        base_name: str = "index", archive_dir: str = "archive") -> str:
    """상단 왼쪽 'YYYY년 MM월' 자리를 대신하는 전체 페이지용 월 선택 드롭다운.
    base_name/archive_dir로 별풍선(index/archive) vs 방송시간(broadcast/archive-broadcast)
    페이지 세트를 구분한다."""
    return _build_select_html(
        archive_slugs, current_year, current_month, active_slug,
        current_href_fn=lambda: f"../{base_name}.html" if is_archive_page else f"{base_name}.html",
        archive_href_fn=lambda slug: f"{slug}.html" if is_archive_page else f"{archive_dir}/{slug}.html",
    )


def page_shell(*, top_bar_html: str, body_html: str, extra_banner: str = "",
               include_mobile_css: bool = True, title: str = "팀별 별풍선 랭킹",
               show_role_legend: bool = True) -> str:
    """모든 페이지 공통 뼈대 (head/style/legend). 팀 단독 페이지는 카드 1개뿐이라
    모바일 압축 스타일이 필요없어서 include_mobile_css=False로 뺄 수 있음.
    show_role_legend=False면 '수장/전력외' 범례 항목을 빼는데, 방송시간 페이지처럼
    해당 강조 표시 자체가 없는 페이지에 쓴다."""
    style = PAGE_CSS + (MOBILE_CSS if include_mobile_css else "")
    role_legend = '<span><span class="sw" style="background:#fadada;"></span>수장/전력외</span>' if show_role_legend else ""
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
{style}
</style>
</head>
<body>
  {extra_banner}
  {top_bar_html}
  {body_html}
  <div class="legend">
    <span><span class="sw" style="background:#d6e9fb;"></span>상위 1%</span>
    <span><span class="sw" style="background:#dcefdd;"></span>상위 5%</span>
    <span><span class="sw" style="background:#fbf3cf;"></span>상위 10%</span>
    {role_legend}
    <span>🎂 이달의 생일</span>
  </div>
</body>
</html>
"""


def render_page(data: dict, archive_slugs: list, current_year: int, current_month: int,
                 is_archive: bool = False, metric: Metric = BALLOON_METRIC,
                 base_name: str = "index", archive_dir: str = "archive") -> str:
    active_slug = f"{data['year']:04d}-{data['month']:02d}"
    month_select_html = build_month_select(archive_slugs, current_year, current_month, active_slug, is_archive,
                                            base_name=base_name, archive_dir=archive_dir)

    members = data["members"]
    teams = group_teams(members)
    tiers = compute_percentile_tiers(members, metric)

    logo_prefix = "../" if is_archive else ""

    current_ranks = compute_team_ranks(members, metric)
    prev_ranks = load_previous_ranks(data["year"], data["month"], metric)

    team_cards = []
    for team_name, team_members in teams.items():
        badge = rank_change_badge(current_ranks[team_name], prev_ranks, team_name)
        avg, html = build_team_card(team_name, team_members, data["month"], tiers, logo_prefix, badge, metric)
        team_cards.append((avg, html))

    team_cards.sort(key=lambda x: -x[0])
    cards_html = "".join(html for _, html in team_cards)

    team_count = len(teams)
    member_count = len(members)

    top_bar_html = f"""
  <div class="top-bar">
    {month_select_html}
    <span class="top-meta">{team_count}팀 / {member_count}명 / 업데이트 {data['updated_at']} / 출처: <a href="https://poonggo.com" target="_blank" rel="noopener" class="source-link">풍고</a></span>
  </div>
    """

    body_html = f"""
  <div class="grid">
    {cards_html}
  </div>
    """

    banner = ARCHIVE_BANNER_HTML if is_archive else ""

    return page_shell(top_bar_html=top_bar_html, body_html=body_html, extra_banner=banner,
                       title=f"팀별 {metric.unit_label} 랭킹", show_role_legend=metric.exclude_roles)


def build_team_month_select(team_name: str, archive_slugs: list, current_year: int, current_month: int,
                             active_slug: str) -> str:
    """
    팀 단독 페이지용 월 선택 드롭다운. 같은 docs/teams/ 폴더 안에 파일명으로만
    구분해서 저장하므로(이번달: {팀}.html, 과거달: {팀}__YYYY-MM.html) 상대경로 계산이 필요없다.
    """
def build_team_month_select(team_name: str, archive_slugs: list, current_year: int, current_month: int,
                             active_slug: str, file_suffix: str = "") -> str:
    """
    팀 단독 페이지용 월 선택 드롭다운. 같은 docs/teams/ 폴더 안에 파일명으로만
    구분해서 저장하므로(이번달: {팀}{suffix}.html, 과거달: {팀}{suffix}__YYYY-MM.html)
    상대경로 계산이 필요없다. file_suffix로 별풍선("")/방송시간("-broadcast") 페이지를 구분한다.
    """
    return _build_select_html(
        archive_slugs, current_year, current_month, active_slug,
        current_href_fn=lambda: f"{team_name}{file_suffix}.html",
        archive_href_fn=lambda slug: f"{team_name}{file_suffix}__{slug}.html",
    )


def render_team_page(data: dict, team_name: str, team_members: list, tiers: dict,
                      archive_slugs: list, current_year: int, current_month: int,
                      is_archive: bool = False, metric: Metric = BALLOON_METRIC,
                      file_suffix: str = "") -> str:
    """특정 팀 하나만 담은 단독 페이지. iframe으로 그 팀만 따로 게시할 때 사용."""
    active_slug = f"{data['year']:04d}-{data['month']:02d}"
    month_select_html = build_team_month_select(team_name, archive_slugs, current_year, current_month, active_slug,
                                                 file_suffix=file_suffix)

    current_ranks = compute_team_ranks(data["members"], metric)
    prev_ranks = load_previous_ranks(data["year"], data["month"], metric)
    badge = rank_change_badge(current_ranks[team_name], prev_ranks, team_name)

    _, card_html = build_team_card(team_name, team_members, data["month"], tiers, logo_prefix="../",
                                    rank_badge=badge, metric=metric)

    top_bar_html = f"""
  <div class="top-bar">
    {month_select_html}
    <span class="top-meta">{team_name} / {len(team_members)}명 / 업데이트 {data['updated_at']} / 출처: <a href="https://poonggo.com" target="_blank" rel="noopener" class="source-link">풍고</a></span>
  </div>
    """

    body_html = f"""
  <div class="grid single-team">
    {card_html}
  </div>
    """

    banner = ARCHIVE_BANNER_HTML if is_archive else ""

    return page_shell(top_bar_html=top_bar_html, body_html=body_html, extra_banner=banner,
                       include_mobile_css=False, title=f"{team_name} {metric.unit_label}",
                       show_role_legend=metric.exclude_roles)


def generate_team_pages(data: dict, is_archive: bool, archive_slugs: list,
                         current_year: int, current_month: int,
                         metric: Metric = BALLOON_METRIC, file_suffix: str = ""):
    """SINGLE_TEAM_PAGES에 지정된 팀들만 docs/teams/ 에 단독 페이지로 생성"""
    if not SINGLE_TEAM_PAGES:
        return

    members = data["members"]
    teams = group_teams(members)
    tiers = compute_percentile_tiers(members, metric)
    slug = f"{data['year']:04d}-{data['month']:02d}"

    OUTPUT_TEAMS_DIR.mkdir(parents=True, exist_ok=True)

    for team_name in SINGLE_TEAM_PAGES:
        team_members = teams.get(team_name)
        if team_members is None:
            continue  # 그 달에 해당 팀이 없으면 건너뜀

        html = render_team_page(
            data, team_name, team_members, tiers,
            archive_slugs, current_year, current_month, is_archive=is_archive,
            metric=metric, file_suffix=file_suffix,
        )
        filename = f"{team_name}{file_suffix}.html" if not is_archive else f"{team_name}{file_suffix}__{slug}.html"
        out_path = OUTPUT_TEAMS_DIR / filename
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"완료: {out_path} 생성됨")


def main():
    archive_slugs = list_archive_slugs()

    # 이번 달 데이터 로드
    if not DATA_PATH.exists():
        raise SystemExit(f"[오류] {DATA_PATH} 가 없습니다. 먼저 fetch_data.py를 실행하세요.")

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        current_data = json.load(f)
    current_data["members"] = normalize_balloons(current_data["members"])

    current_year, current_month = current_data["year"], current_data["month"]

    # 지표별로 (전체 페이지 출력경로, 과거달 폴더, 파일명 베이스, 과거달 폴더명, 팀페이지 파일명 접미사)
    page_sets = [
        (BALLOON_METRIC, OUTPUT_PATH, OUTPUT_ARCHIVE_DIR, "index", "archive", ""),
        (BROADCAST_METRIC, OUTPUT_BROADCAST_PATH, OUTPUT_ARCHIVE_BROADCAST_DIR, "broadcast", "archive-broadcast", "-broadcast"),
    ]

    for metric, output_path, output_archive_dir, base_name, archive_dir_name, file_suffix in page_sets:
        # 이번 달 전체 페이지
        html = render_page(current_data, archive_slugs, current_year, current_month, is_archive=False,
                            metric=metric, base_name=base_name, archive_dir=archive_dir_name)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"완료: {output_path} 생성됨")

        # 팀별 단독 페이지 (이번 달)
        generate_team_pages(current_data, is_archive=False, archive_slugs=archive_slugs,
                             current_year=current_year, current_month=current_month,
                             metric=metric, file_suffix=file_suffix)

        # 과거 달 페이지들 (전체 페이지 + 팀별 단독 페이지)
        if archive_slugs:
            output_archive_dir.mkdir(parents=True, exist_ok=True)
            for slug in archive_slugs:
                archive_json_path = ARCHIVE_DIR / f"{slug}.json"
                with open(archive_json_path, "r", encoding="utf-8") as f:
                    archive_data = json.load(f)
                archive_data["members"] = normalize_balloons(archive_data["members"])

                a_html = render_page(archive_data, archive_slugs, current_year, current_month, is_archive=True,
                                      metric=metric, base_name=base_name, archive_dir=archive_dir_name)

                out_path = output_archive_dir / f"{slug}.html"
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(a_html)
                print(f"완료: {out_path} 생성됨")

                generate_team_pages(archive_data, is_archive=True, archive_slugs=archive_slugs,
                                     current_year=current_year, current_month=current_month,
                                     metric=metric, file_suffix=file_suffix)


if __name__ == "__main__":
    main()
