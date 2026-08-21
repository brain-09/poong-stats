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

import colorsys
import json
from collections import OrderedDict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "latest.json"
ARCHIVE_DIR = ROOT / "data" / "archive"
OUTPUT_PATH = ROOT / "docs" / "index.html"
OUTPUT_TEAMS_DIR = ROOT / "docs" / "teams"
LOGOS_DIR = ROOT / "docs" / "logos"

EXCLUDED_ROLES = {"수장", "전력외"}
DEFAULT_TOPBAR_COLOR = "#4a5ce0"
_topbar_color_cache: dict = {}


def get_team_topbar_color(team_name: str) -> str:
    """팀 로고(docs/logos/{팀}.webp)에서 대표 색을 뽑아 카드 상단 바 색으로 쓴다.
    로고가 없거나 읽기에 실패하면 기존 파란색(DEFAULT_TOPBAR_COLOR)을 그대로 쓴다.
    흰색/검은색(배경·테두리로 흔함)은 후보에서 제외하고, 자주 등장하는 색상들 중
    채도가 가장 높은 색을 '브랜드 색'으로 간주해 고른다. 팀당 한 번만 계산하고 캐시."""
    if team_name in _topbar_color_cache:
        return _topbar_color_cache[team_name]

    color = DEFAULT_TOPBAR_COLOR
    logo_path = LOGOS_DIR / f"{team_name}.webp"
    if logo_path.exists():
        try:
            img = Image.open(logo_path).convert("RGBA").resize((40, 40))
            buckets: dict = {}  # 양자화된 RGB -> [등장횟수, 채도 합]
            for r, g, b, a in img.getdata():
                if a < 128:
                    continue
                if (r > 235 and g > 235 and b > 235) or (r < 20 and g < 20 and b < 20):
                    continue
                h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                key = (r // 20 * 20, g // 20 * 20, b // 20 * 20)
                bucket = buckets.setdefault(key, [0, 0.0])
                bucket[0] += 1
                bucket[1] += s

            if buckets:
                top_buckets = sorted(buckets.items(), key=lambda kv: -kv[1][0])[:6]
                best_key = max(top_buckets, key=lambda kv: kv[1][1] / kv[1][0])[0]
                color = f"#{best_key[0]:02x}{best_key[1]:02x}{best_key[2]:02x}"
        except Exception:
            color = DEFAULT_TOPBAR_COLOR

    _topbar_color_cache[team_name] = color
    return color


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
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;800;900&display=swap');

  * { box-sizing: border-box; }

  body {
    font-family: 'Noto Sans KR', -apple-system, "Malgun Gothic", sans-serif;
    background: #f4f5f7;
    margin: 0;
    padding: 20px 10px;
    color: #1a1d29;
  }
  .top-bar {
    max-width: 1080px;
    margin: 0 auto 16px;
    background: #fff;
    border-radius: 20px;
    padding: 16px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    box-shadow: 0 1px 2px rgba(20,20,30,0.04), 0 4px 12px rgba(20,20,30,0.05);
  }
  .month-select-group {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .top-date-select {
    font-size: 20px;
    font-weight: 800;
    color: #141821;
    letter-spacing: 0px;
    border: none;
    background: transparent;
    cursor: pointer;
    font-family: inherit;
    padding: 2px 0;
    appearance: none;
    -webkit-appearance: none;
    -moz-appearance: none;
  }
  .top-date-select:hover { color: #4a5ce0; }
  .nav-chevron {
    font-size: 14px;
    color: #c2c5cc;
    margin: 0 4px;
    user-select: none;
  }
  .top-meta {
    font-size: 12px;
    color: #a4a8b2;
    white-space: nowrap;
  }
  .source-link {
    color: #4a5ce0;
    font-weight: 600;
    text-decoration: none;
  }
  .source-link:hover { text-decoration: underline; }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    align-items: start;
    gap: 16px;
    max-width: 1080px;
    margin: 0 auto;
  }
  .grid.single-team {
    grid-template-columns: 1fr;
    max-width: 480px;
  }
  .team-card {
    background: #fff;
    border-radius: 20px;
    overflow: hidden;
    box-shadow: 0 1px 2px rgba(20,20,30,0.04), 0 8px 24px rgba(20,20,30,0.06);
  }
  .team-card-topbar { height: 6px; background: #4a5ce0; }
  .team-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid #f2f3f5;
    gap: 8px;
    flex-wrap: wrap;
  }
  .team-header-left {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }
  .team-link {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
    color: inherit;
    text-decoration: none;
  }
  .team-link:hover .team-name { text-decoration: underline; }
  .team-logo {
    width: 28px;
    height: 28px;
    border-radius: 10px;
    object-fit: contain;
    flex-shrink: 0;
  }
  .team-name {
    font-size: 16px;
    font-weight: 800;
    color: #141821;
    letter-spacing: 0px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .team-count {
    font-size: 12px;
    color: #a4a8b2;
    font-weight: 500;
    white-space: nowrap;
  }
  .rank-change {
    font-size: 12px;
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 20px;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .rank-change.up { color: #0f8a4c; background: #e6f8ee; }
  .rank-change.down { color: #c0392b; background: #fdeaea; }
  .rank-change.same { color: #888; background: #eceef1; }
  .rank-change.new { color: #4a5ce0; background: #e6e9fb; }

  .member-columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }
  .member-col:first-child { border-right: 1px solid #f2f3f5; }
  .member-col-label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    font-weight: 700;
    color: #a4a8b2;
    letter-spacing: 0px;
    padding: 10px 16px 8px;
    background: #fafbfc;
  }
  .member-col-label .col-label-text { font-size: 12px; font-weight: 700; line-height: 1; }
  .member-col-label .unit-label { font-size: 12px; font-weight: 700; line-height: 1; text-align: right; }
  .member-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 16px;
    border-left: 4px solid transparent;
    min-height: 30px;
  }
  .member-row.tier1 { border-left-color: #4a5ce0; background: #f4f6fe; }
  .member-row.tier5 { border-left-color: #1c9e6e; background: #effbf5; }
  .member-row.tier10 { border-left-color: #d9a71b; background: #fdf6e0; }
  .member-row.excluded { border-left-color: #d64545; background: #fdeaea; }
  .member-name {
    font-size: 14px;
    color: #3a3d47;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .member-row.tier1 .member-name,
  .member-row.tier5 .member-name,
  .member-row.tier10 .member-name,
  .member-row.excluded .member-name { font-weight: 700; color: #1a1d29; }
  .bday-mark { font-size: 10px; opacity: 0.75; flex-shrink: 0; }
  .member-value {
    font-size: 14px;
    color: #6b6f79;
    font-weight: 700;
    text-align: right;
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
    padding-left: 8px;
  }
  .member-row.tier1 .member-value { color: #4a5ce0; font-weight: 700; }
  .member-row.tier5 .member-value { color: #0f8a5c; font-weight: 700; }
  .member-row.tier10 .member-value { color: #8a6d1a; font-weight: 700; }
  .member-row.excluded .member-value { color: #1a1d29; font-weight: 700; }
  .member-row.empty .member-name, .member-row.empty .member-value { color: #ccc; }

  .team-footer {
    display: flex;
    gap: 6px;
    padding: 12px 10px 14px;
    background: #fafbfc;
    border-top: 1px solid #f2f3f5;
  }
  .stat-card {
    flex: 1;
    text-align: center;
    padding: 12px 8px;
    border-radius: 16px;
    background: #fff;
    border: 1px solid #eef0f2;
    min-width: 0;
  }
  .stat-label { font-size: 12px; color: #a4a8b2; margin-bottom: 4px; font-weight: 600; }
  .stat-value { font-size: 16px; font-weight: 800; color: #1a1d29; font-variant-numeric: tabular-nums; }
  .stat-card.female-avg { background: #d9f2f2; border: none; }
  .stat-card.female-avg .stat-label { color: #0e6b6b; }
  .stat-card.female-avg .stat-value { color: #0a4d4d; }
  .stat-card.total-avg { background: #efe9fc; border: none; }
  .stat-card.total-avg .stat-label { color: #6a3fb0; }
  .stat-card.total-avg .stat-value { color: #4a2984; }

  .legend {
    max-width: 1080px;
    margin: 16px auto 0;
    font-size: 12px;
    color: #a4a8b2;
    text-align: center;
  }
  .legend span { margin: 0 8px; }
  .legend .sw {
    display: inline-block;
    width: 12px; height: 12px;
    border-radius: 2px;
    margin-right: 4px;
    vertical-align: middle;
  }
"""

MOBILE_CSS = """
  /* 모바일: 한 줄에 2팀씩 보이도록 강제 2열 + 여백/폰트 축소.
     PC(PAGE_CSS)는 이 값들을 전부 정확히 x2 한 것 - 크기를 바꿀 땐 여기부터 고치고
     PAGE_CSS 쪽을 2배로 맞추면 된다. */
  @media (max-width: 600px) {
    body { padding: 12px 6px; }
    .top-bar { border-radius: 10px; padding: 8px 10px; gap: 4px; }
    .month-select-group { gap: 2px; }
    .top-date-select { font-size: 10px; }
    .nav-chevron { font-size: 7px; margin: 0 2px; }
    .top-meta { font-size: 6px; white-space: normal; }
    .grid {
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .team-card { border-radius: 10px; }
    .team-card-topbar { height: 3px; }
    .team-header { padding: 6px 8px; gap: 4px; }
    .team-header-left, .team-link { gap: 5px; }
    .team-logo { width: 14px; height: 14px; border-radius: 5px; }
    .team-name { font-size: 8px; }
    .team-count { font-size: 6px; }
    .rank-change { font-size: 6px; padding: 2px 6px; border-radius: 10px; }
    .member-col-label { font-size: 6px; padding: 5px 8px 4px; }
    .member-col-label .col-label-text, .member-col-label .unit-label { font-size: 6px; }
    .member-row { padding: 4px 8px; min-height: 15px; border-left-width: 2px; }
    .member-name { font-size: 7px; gap: 3px; }
    .bday-mark { font-size: 5px; }
    .member-value { font-size: 7px; padding-left: 4px; }
    .team-footer { padding: 6px 5px 7px; gap: 3px; }
    .stat-card { padding: 6px 4px; border-radius: 8px; }
    .stat-label { font-size: 6px; margin-bottom: 2px; }
    .stat-value { font-size: 8px; }
    .legend { font-size: 6px; margin-top: 8px; }
    .legend span { margin: 0 4px; }
    .legend .sw { width: 6px; height: 6px; margin-right: 2px; }
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
    female_avg = round(female_sum / len(females_counted)) if females_counted else 0
    total_avg = team_total_avg(members, metric)  # 순위 계산과 동일한 공식(team_total_avg)을 그대로 재사용

    male_n, female_n = len(males_all), len(females_all)

    def member_row(m):
        bday = parse_birthdate(m.get("birthdate"))
        bday_html = "<span class='bday-mark'>🎂</span>" if bday and bday[0] == current_month else ""
        row_class = value_class(m, tiers, metric)
        return (
            f"<div class='member-row {row_class}'>"
            f"<span class='member-name'>{m['nickname']}{bday_html}</span>"
            f"<span class='member-value'>{metric.text(m)}</span>"
            f"</div>"
        )

    def member_col(name_list, other_len):
        rows = [member_row(m) for m in name_list]
        # 남녀 인원수가 다르면, 적은 쪽에 빈 줄을 채워서 줄 높이를 맞춘다
        for _ in range(max(0, other_len - len(name_list))):
            rows.append("<div class='member-row empty'><span class='member-name'></span><span class='member-value'></span></div>")
        return "".join(rows)

    males_html = member_col(males_all, female_n)
    females_html = member_col(females_all, male_n)

    logo_html = team_logo_html(team_name, logo_prefix)
    header_left_content = f"{logo_html}<span class='team-name'>{team_name}</span><span class='team-count'>총 {male_n + female_n}명 · 남 {male_n} · 여 {female_n}</span>"
    if team_link:
        header_left = f"<a class='team-link' href='{team_link}'>{header_left_content}</a>"
    else:
        header_left = f"<div class='team-header-left'>{header_left_content}</div>"

    topbar_color = get_team_topbar_color(team_name)

    return total_avg, f"""
    <div class="team-card">
      <div class="team-card-topbar" style="background:{topbar_color};"></div>
      <div class="team-header">
        {header_left}
        {rank_badge}
      </div>
      <div class="member-columns">
        <div class="member-col">
          <div class="member-col-label"><span class="col-label-text">남자 멤버</span><span class="unit-label">{metric.unit_label}</span></div>
          {males_html}
        </div>
        <div class="member-col">
          <div class="member-col-label"><span class="col-label-text">여자 멤버</span><span class="unit-label">{metric.unit_label}</span></div>
          {females_html}
        </div>
      </div>
      <div class="team-footer">
        <div class="stat-card">
          <div class="stat-label">전체 합계</div>
          <div class="stat-value">{metric.format_fn(total_sum)}</div>
        </div>
        <div class="stat-card female-avg">
          <div class="stat-label">여자 평균</div>
          <div class="stat-value">{metric.format_fn(female_avg)}</div>
        </div>
        <div class="stat-card total-avg">
          <div class="stat-label">전체 평균</div>
          <div class="stat-value">{metric.format_fn(total_avg)}</div>
        </div>
      </div>
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
    <span>🎂 생일</span>
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

    nav_html = f"""
  <span class="month-select-group">
    <select class="top-date-select" id="ms-year-select">{year_options}</select>
    <span class="nav-chevron">⌄</span>
    <select class="top-date-select" id="ms-month-select">{month_options}</select>
    <span class="nav-chevron">⌄</span>
    <select class="top-date-select" id="ms-metric-select">{metric_options}</select>
    <span class="nav-chevron">⌄</span>
  </span>
    """

    top_bar_html = f"""
  <div class="top-bar">
    {nav_html}
    <span class="top-meta" id="top-meta-text"></span>
  </div>
    """

    body_html = f"""
  {"".join(panels_html)}
    """

    extra_script = f"""<script>
(function () {{
  var meta = {metadata_json};
  var monthsByYear = {months_by_year_json};
  var yearSel = document.getElementById('ms-year-select');
  var monthSel = document.getElementById('ms-month-select');
  var metricSel = document.getElementById('ms-metric-select');
  var metaSpan = document.getElementById('top-meta-text');
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

    metaSpan.textContent = m.teamCount + '팀 · ' + m.memberCount + '명 · 업데이트 ' + m.updatedAt + ' · 출처: ';
    var link = document.createElement('a');
    link.href = 'https://poonggo.com';
    link.target = '_blank';
    link.rel = 'noopener';
    link.className = 'source-link';
    link.textContent = '풍고';
    metaSpan.appendChild(link);

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
