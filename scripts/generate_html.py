"""
data/latest.json (이번 달) 과 data/archive/*.json (과거 달)을 전부 읽어서, 지표별(별풍선/방송시간)
로 렌더링한 결과를 "하나의 HTML 파일" 안에 전부 넣어두고, 자바스크립트로 연도/월/지표를
선택하면 해당 부분만 보여주는(나머지는 숨김) 방식으로 만드는 스크립트.

예전에는 이번 달/과거 달/별풍선/방송시간 조합마다 별도 파일(docs/index.html,
docs/archive/YYYY-MM.html, docs/broadcast.html, docs/archive-broadcast/YYYY-MM.html ...)을
만들었지만, 이제는 docs/index.html 하나(그리고 등장하는 모든 팀마다 docs/teams/{팀}.html
하나씩)에 모든 조합을 "패널"로 미리 렌더링해서 넣어두고, 상단의 연도/월/지표 select
3개가 자바스크립트로 어느 패널을 보여줄지 전환한다. 페이지 이동(새로고침) 없이 즉시 바뀐다.
전체 페이지에서 팀 이름을 누르면, 보고 있던 연/월/지표를 쿼리 파라미터로 이어받아
그 팀의 단독 페이지가 같은 상태로 열린다.

별풍선(BALLOON_METRIC)과 방송시간(BROADCAST_METRIC) 페이지는 레이아웃이 동일하지만,
방송시간 페이지는 수장/전력외 직책도 합계·평균 집계에 포함한다는 점만 다르다
(Metric.exclude_roles 값으로 제어) - 이에 따라 하단 범례의 "수장/전력외" 항목도
지표를 바꿀 때마다 자바스크립트로 보였다 숨겨졌다 한다.

과거 달 데이터는 fetch_data.py가 달이 바뀔 때 그 달 기준으로 API를 한 번 더 호출해
확정된 별풍선 값으로 갱신한 뒤 data/archive/에 보관해둔 것 - 그 시점의 team/gender/role이
멤버마다 그대로 들어있어서 팀 구성이 바뀌어도 "그 당시 배정" 그대로 재현된다.

팀별 표: 표 1개, [남자 멤버 | 값 | 여자 멤버 | 값] 4열, 각각 내림차순 정렬.
하단에 합계/평균/인원 행 포함. 값이 0이거나(방송시간 페이지는 추가로 수장/전력외까지)
집계·상위% 계산에서 제외되며, 수장/전력외는 표에 빨간 배경으로 표시(방송시간 페이지는
집계에 포함되므로 이 강조 표시를 하지 않음), 0인 사람은 빈 칸으로 표시.
이름 옆에는 그 달의 생일이면 🎂 표시.

실행: python scripts/generate_html.py
"""

import json
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "latest.json"
ARCHIVE_DIR = ROOT / "data" / "archive"
OUTPUT_PATH = ROOT / "docs" / "index.html"
OUTPUT_TEAMS_DIR = ROOT / "docs" / "teams"
LOGOS_DIR = ROOT / "docs" / "logos"

EXCLUDED_ROLES = {"수장", "전력외"}

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
  .month-select-group {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .top-date-select {
    font-size: 18px;
    font-weight: 700;
    color: #222;
    border: none;
    background: transparent;
    cursor: pointer;
    font-family: inherit;
    padding: 2px 16px 2px 0;
    appearance: none;
    -webkit-appearance: none;
    -moz-appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%23888' stroke-width='2' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right center;
    background-size: 10px 7px;
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
  .team-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: inherit;
    text-decoration: none;
  }
  .team-link:hover { text-decoration: underline; }
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
    .month-select-group { gap: 3px; }
    .top-date-select { font-size: 10px; min-width: 0; padding: 2px 12px 2px 2px; background-size: 8px 6px; }
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

    def __init__(self, key: str, field: str, exclude_roles: bool, format_fn, unit_label: str):
        self.key = key  # JS에서 쓰는 짧은 식별자 ("balloon" / "broadcast")
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
BALLOON_METRIC = Metric(key="balloon", field="balloons", exclude_roles=True, format_fn=fmt, unit_label="별풍선")
# 방송시간 페이지(신규): 수장/전력외도 집계에 포함
BROADCAST_METRIC = Metric(key="broadcast", field="broadcast_seconds", exclude_roles=False,
                           format_fn=format_broadcast_time, unit_label="방송시간")
METRICS = [BALLOON_METRIC, BROADCAST_METRIC]


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
                     logo_prefix: str = "", rank_badge: str = "", metric: Metric = BALLOON_METRIC,
                     team_link: str = ""):
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

    logo_html = team_logo_html(team_name, logo_prefix)
    name_content = f"<a class='team-link' href='{team_link}'>{logo_html}{team_name}</a>" if team_link else f"{logo_html}{team_name}"

    if rank_badge:
        name_row_inner = (
            f"<div class='team-name-flex'>"
            f"<span class='team-name-inner'>{name_content}</span>"
            f"{rank_badge}"
            f"</div>"
        )
    else:
        name_row_inner = f"<span class='team-name-inner'>{name_content}</span>"

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


def build_grid_panel(data: dict, metric: Metric, logo_prefix: str) -> str:
    """전체 팀 그리드 패널 (모든 팀 카드, 전체 평균 내림차순 정렬). 팀 이름을 누르면
    현재 보고 있던 연/월/지표를 그대로 유지한 채 그 팀의 단독 페이지로 이동한다."""
    members = data["members"]
    teams = group_teams(members)
    tiers = compute_percentile_tiers(members, metric)
    current_ranks = compute_team_ranks(members, metric)
    prev_ranks = load_previous_ranks(data["year"], data["month"], metric)

    team_cards = []
    for team_name, team_members in teams.items():
        badge = rank_change_badge(current_ranks[team_name], prev_ranks, team_name)
        link = f"teams/{team_name}.html?y={data['year']}&m={data['month']}&metric={metric.key}"
        avg, html = build_team_card(team_name, team_members, data["month"], tiers, logo_prefix, badge, metric,
                                     team_link=link)
        team_cards.append((avg, html))

    team_cards.sort(key=lambda x: -x[0])
    cards_html = "".join(html for _, html in team_cards)
    return f'<div class="grid">{cards_html}</div>'


def build_single_team_panel(data: dict, team_name: str, metric: Metric, logo_prefix: str) -> str:
    """특정 팀 하나만 담은 패널. 그 달에 팀이 없으면 안내 문구만 표시."""
    teams = group_teams(data["members"])
    team_members = teams.get(team_name)
    if team_members is None:
        return (
            '<div class="grid single-team"><div class="team-card" '
            'style="padding:24px;text-align:center;color:#999;font-size:13px;">'
            '이 달에는 팀 정보가 없습니다.</div></div>'
        )

    tiers = compute_percentile_tiers(data["members"], metric)
    current_ranks = compute_team_ranks(data["members"], metric)
    prev_ranks = load_previous_ranks(data["year"], data["month"], metric)
    badge = rank_change_badge(current_ranks[team_name], prev_ranks, team_name)
    _, card_html = build_team_card(team_name, team_members, data["month"], tiers, logo_prefix, badge, metric)
    return f'<div class="grid single-team">{card_html}</div>'


def page_shell(*, top_bar_html: str, body_html: str, include_mobile_css: bool = True,
               title: str, extra_script: str) -> str:
    """모든 페이지 공통 뼈대. 팀 단독 페이지는 카드 1개뿐이라 모바일 압축 스타일이
    필요없어서 include_mobile_css=False로 뺄 수 있음. '수장/전력외' 범례 항목은
    id로 표시해두고, 지표 전환 시 자바스크립트가 보였다/숨겼다 한다."""
    style = PAGE_CSS + (MOBILE_CSS if include_mobile_css else "")
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
  {top_bar_html}
  {body_html}
  <div class="legend">
    <span><span class="sw" style="background:#d6e9fb;"></span>상위 1%</span>
    <span><span class="sw" style="background:#dcefdd;"></span>상위 5%</span>
    <span><span class="sw" style="background:#fbf3cf;"></span>상위 10%</span>
    <span id="role-legend-item"><span class="sw" style="background:#fadada;"></span>수장/전력외</span>
    <span>🎂 이달의 생일</span>
  </div>
{extra_script}
</body>
</html>
"""


def load_all_month_data():
    """이번 달 + 과거 모든 달의 데이터를 리스트로 로드 (이번 달이 맨 앞)"""
    if not DATA_PATH.exists():
        raise SystemExit(f"[오류] {DATA_PATH} 가 없습니다. 먼저 fetch_data.py를 실행하세요.")

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        current_data = json.load(f)
    current_data["members"] = normalize_balloons(current_data["members"])

    all_data = [current_data]
    for slug in list_archive_slugs():
        path = ARCHIVE_DIR / f"{slug}.json"
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        d["members"] = normalize_balloons(d["members"])
        all_data.append(d)

    return current_data, all_data


def assemble_single_page(all_data: list, current_year: int, current_month: int,
                          panel_builder, logo_prefix: str, include_mobile_css: bool,
                          page_title_base: str) -> str:
    """
    all_data의 모든 (연,월) x (별풍선/방송시간) 조합을 패널로 미리 렌더링해서
    하나의 페이지에 담고, 연도/월/지표 select 3개 + 자바스크립트로 전환하게 만든다.
    panel_builder(data, metric, logo_prefix) -> 패널 안쪽 HTML (grid div)
    """
    default_key = f"{current_year:04d}-{current_month:02d}-{BALLOON_METRIC.key}"

    metadata = {}
    panels_html = []
    years_months = {}  # {연도: {월, 월, ...}}

    for data in all_data:
        y, m = data["year"], data["month"]
        is_archive = not (y == current_year and m == current_month)
        years_months.setdefault(y, set()).add(m)

        for metric in METRICS:
            key = f"{y:04d}-{m:02d}-{metric.key}"
            panel_inner = panel_builder(data, metric, logo_prefix)
            style_attr = "" if key == default_key else " style=\"display:none;\""
            panels_html.append(f"<div class='page-panel' data-key='{key}'{style_attr}>{panel_inner}</div>")

            metadata[key] = {
                "teamCount": len(group_teams(data["members"])),
                "memberCount": len(data["members"]),
                "updatedAt": data["updated_at"],
                "isArchive": is_archive,
                "excludeRoles": metric.exclude_roles,
                "title": f"{page_title_base} {metric.unit_label}",
            }

    years_sorted = sorted(years_months.keys(), reverse=True)
    year_options = "".join(
        f"<option value='{y}'{' selected' if y == current_year else ''}>{y}년</option>"
        for y in years_sorted
    )
    months_for_current_year = sorted(years_months[current_year], reverse=True)
    month_options = "".join(
        f"<option value='{m}'{' selected' if m == current_month else ''}>{m:02d}월</option>"
        for m in months_for_current_year
    )
    metric_options = "".join(
        f"<option value='{metric.key}'{' selected' if metric is BALLOON_METRIC else ''}>{metric.unit_label}</option>"
        for metric in METRICS
    )

    months_by_year_json = json.dumps({str(y): sorted(ms, reverse=True) for y, ms in years_months.items()})
    metadata_json = json.dumps(metadata, ensure_ascii=False)
    archive_banner_json = json.dumps(ARCHIVE_BANNER_HTML)

    nav_html = f"""
  <span class="month-select-group">
    <select class="top-date-select" id="ms-year-select">{year_options}</select>
    <select class="top-date-select" id="ms-month-select">{month_options}</select>
    <select class="top-date-select" id="ms-metric-select">{metric_options}</select>
  </span>
    """

    top_bar_html = f"""
  <div class="top-bar">
    {nav_html}
    <span class="top-meta" id="top-meta-text"></span>
  </div>
    """

    body_html = f"""
  <div id="archive-banner-slot"></div>
  {"".join(panels_html)}
    """

    extra_script = f"""<script>
(function () {{
  var meta = {metadata_json};
  var monthsByYear = {months_by_year_json};
  var archiveBannerHtml = {archive_banner_json};

  var yearSel = document.getElementById('ms-year-select');
  var monthSel = document.getElementById('ms-month-select');
  var metricSel = document.getElementById('ms-metric-select');
  var metaSpan = document.getElementById('top-meta-text');
  var bannerSlot = document.getElementById('archive-banner-slot');
  var roleLegendItem = document.getElementById('role-legend-item');

  function pad(n) {{ n = parseInt(n, 10); return (n < 10 ? '0' : '') + n; }}

  function populateMonths(year, preselectMonth) {{
    monthSel.innerHTML = '';
    (monthsByYear[year] || []).forEach(function (m) {{
      var opt = document.createElement('option');
      opt.value = m;
      opt.textContent = pad(m) + '월';
      if (m === preselectMonth) opt.selected = true;
      monthSel.appendChild(opt);
    }});
  }}

  function currentKey() {{
    return yearSel.value + '-' + pad(monthSel.value) + '-' + metricSel.value;
  }}

  function apply() {{
    var key = currentKey();
    var panels = document.querySelectorAll('.page-panel');
    for (var i = 0; i < panels.length; i++) {{
      panels[i].style.display = (panels[i].getAttribute('data-key') === key) ? '' : 'none';
    }}
    var m = meta[key];
    if (!m) return;

    metaSpan.textContent = m.teamCount + '팀 / ' + m.memberCount + '명 / 업데이트 ' + m.updatedAt + ' / 출처: ';
    var link = document.createElement('a');
    link.href = 'https://poonggo.com';
    link.target = '_blank';
    link.rel = 'noopener';
    link.className = 'source-link';
    link.textContent = '풍고';
    metaSpan.appendChild(link);

    bannerSlot.innerHTML = m.isArchive ? archiveBannerHtml : '';
    if (roleLegendItem) roleLegendItem.style.display = m.excludeRoles ? '' : 'none';
    document.title = m.title;
  }}

  yearSel.addEventListener('change', function () {{
    var year = yearSel.value;
    var monthsInYear = monthsByYear[year] || [];
    populateMonths(year, monthsInYear.length ? monthsInYear[0] : null);
    apply();
  }});
  monthSel.addEventListener('change', apply);
  metricSel.addEventListener('change', apply);

  // 전체 페이지에서 팀 이름을 눌러 넘어온 경우, 그때 보고 있던 연/월/지표를
  // 쿼리 파라미터(?y=&m=&metric=)로 이어받아 초기 선택 상태를 맞춘다.
  (function applyQueryParams() {{
    var params = new URLSearchParams(window.location.search);
    var qy = params.get('y');
    var qm = params.get('m');
    var qmetric = params.get('metric');

    if (qy && yearSel.querySelector("option[value='" + qy + "']")) {{
      yearSel.value = qy;
      var monthsInYear = monthsByYear[qy] || [];
      var preselect = qm && monthsInYear.indexOf(parseInt(qm, 10)) !== -1
        ? parseInt(qm, 10)
        : (monthsInYear.length ? monthsInYear[0] : null);
      populateMonths(qy, preselect);
    }}
    if (qmetric && (qmetric === 'balloon' || qmetric === 'broadcast')) {{
      metricSel.value = qmetric;
    }}
  }})();

  apply();
}})();
</script>"""

    return page_shell(
        top_bar_html=top_bar_html, body_html=body_html, include_mobile_css=include_mobile_css,
        title=f"{page_title_base} {BALLOON_METRIC.unit_label}", extra_script=extra_script,
    )


def main():
    current_data, all_data = load_all_month_data()
    current_year, current_month = current_data["year"], current_data["month"]

    # 전체 페이지 (모든 팀)
    html = assemble_single_page(
        all_data, current_year, current_month,
        panel_builder=build_grid_panel, logo_prefix="",
        include_mobile_css=True, page_title_base="팀별",
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"완료: {OUTPUT_PATH} 생성됨")

    # 팀별 단독 페이지 - 이번 달이든 과거 달이든, 한 번이라도 등장한 팀은 전부 생성
    all_team_names = set()
    for data in all_data:
        all_team_names.update(group_teams(data["members"]).keys())

    if all_team_names:
        OUTPUT_TEAMS_DIR.mkdir(parents=True, exist_ok=True)
        for team_name in sorted(all_team_names):
            def _panel_builder(data, metric, logo_prefix, _team=team_name):
                return build_single_team_panel(data, _team, metric, logo_prefix)

            team_html = assemble_single_page(
                all_data, current_year, current_month,
                panel_builder=_panel_builder, logo_prefix="../",
                include_mobile_css=False, page_title_base=team_name,
            )
            out_path = OUTPUT_TEAMS_DIR / f"{team_name}.html"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(team_html)
            print(f"완료: {out_path} 생성됨")


if __name__ == "__main__":
    main()
