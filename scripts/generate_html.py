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

별풍선(BALLOON_METRIC)/방송시간(BROADCAST_METRIC)/누적시청자(VIEWER_METRIC) 페이지는
레이아웃이 동일하지만, 방송시간 페이지만 수장/전력외 직책도 합계·평균 집계에 포함한다는
점이 다르다(Metric.exclude_roles 값으로 제어; 별풍선·누적시청자는 제외) - 이에 따라
하단 범례의 "수장/전력외" 항목도 지표를 바꿀 때마다 자바스크립트로 보였다 숨겨졌다 한다.

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
OUTPUT_PROFILE_PATH = ROOT / "docs" / "profile.html"
LOGOS_DIR = ROOT / "docs" / "logos"

EXCLUDED_ROLES = {"수장", "전력외"}
# FA/휴면인 사람은 나중에 개인 프로필용으로 members.json에 미리 등록해두는
# 것뿐, 실제 팀 소속이 아니므로 팀 카드/팀 페이지 집계 대상에서 완전히 뺀다.
NON_TEAM_LABELS = {"FA", "휴면"}
DEFAULT_TOPBAR_COLOR = "#4a5ce0"
_topbar_color_cache: dict = {}
_json_file_cache: dict = {}


def _load_json_cached(path: Path) -> dict:
    """같은 아카이브 파일을 여러 팀/지표에서 반복해서 읽지 않도록 캐싱한다.
    이번 실행 중에는 archive json 내용이 바뀔 일이 없으므로 안전하다."""
    key = str(path)
    if key not in _json_file_cache:
        with open(path, "r", encoding="utf-8") as f:
            _json_file_cache[key] = json.load(f)
    return _json_file_cache[key]


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
    """balloons/broadcast_seconds/cumulative_viewers 값이 문자열 등으로 저장돼있어도
    항상 int로 안전하게 맞춰준다 (크롤링 스크립트가 정수로 저장해도, 예전 데이터 파일이
    남아있는 경우 대비)."""
    for m in members:
        for field in ("balloons", "broadcast_seconds", "cumulative_viewers"):
            raw = m.get(field, 0)
            if not isinstance(raw, int):
                try:
                    m[field] = int(str(raw).replace(",", "").strip() or 0)
                except (ValueError, TypeError):
                    m[field] = 0
    return members


# 모든 페이지가 공유하는 스타일. f-string이 아니라 일반 문자열이라 중괄호를 그대로 쓴다.
PAGE_CSS = """
  html { scrollbar-gutter: stable; }
  * { box-sizing: border-box; }

  body {
    font-family: 'Pretendard Variable', 'Pretendard', -apple-system, BlinkMacSystemFont,
      system-ui, "Malgun Gothic", sans-serif;
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
    min-height: 64px;
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
  .back-link {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    font-size: 10px;
    font-weight: 600;
    color: #8a8d97;
    text-decoration: none;
  }
  .back-link:hover { color: #4a5ce0; }
  .top-meta-group {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  .top-meta-sep { color: #c2c5cc; }
  .top-meta {
    font-size: 10px;
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
    font-size: 10px;
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
    min-height: 28px;
  }
  .member-row.tier1 { border-left-color: #4a5ce0; background: #f4f6fe; }
  .member-row.tier5 { border-left-color: #1c9e6e; background: #effbf5; }
  .member-row.tier10 { border-left-color: #d9a71b; background: #fdf6e0; }
  .member-row.excluded { border-left-color: #d64545; background: #fdeaea; }
  .member-name {
    font-size: 12px;
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
  .member-name-link { display: flex; align-items: center; gap: 6px; min-width: 0; color: inherit; text-decoration: none; }
  .member-name-link:hover { text-decoration: underline; }
  .member-row.tier1 .member-name,
  .member-row.tier5 .member-name,
  .member-row.tier10 .member-name,
  .member-row.excluded .member-name { font-weight: 700; color: #1a1d29; }
  .bday-mark { font-size: 8px; opacity: 0.75; flex-shrink: 0; }
  .member-value {
    font-size: 12px;
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
    padding: 14px 8px;
    border-radius: 16px;
    background: #fff;
    border: 1px solid #eef0f2;
    min-width: 0;
  }
  .stat-card-header { display: flex; align-items: center; justify-content: center; gap: 4px; margin-bottom: 5px; margin-left: -6px; }
  .stat-card-header.no-icon { margin-left: 0; }
  .stat-label { font-size: 12px; color: #1a1d29; font-weight: 600; }
  .stat-value { font-size: 14px; font-weight: 800; color: #1a1d29; font-variant-numeric: tabular-nums; }
  .stat-icon { color: #1a1d29; flex-shrink: 0; }
  .stat-card.female-avg { background: #eaf7f5; border: none; }
  .stat-card.female-avg .stat-value { color: #085041; }
  .stat-card.total-avg { background: #f1eefb; border: none; }
  .stat-card.total-avg .stat-value { color: #26215c; }

  .profile-photo-img {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    object-fit: cover;
    background: #f2f3f5;
    flex-shrink: 0;
  }
  .profile-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 16px;
    font-size: 12px;
    border-bottom: 1px solid #f2f3f5;
  }
  .profile-row-label { color: #6b6f79; font-weight: 600; }
  .profile-row-value { font-weight: 700; color: #1a1d29; }
  .profile-station-icon { width: 20px; height: 20px; border-radius: 5px; display: block; }

  .legend {
    max-width: 1080px;
    margin: 16px auto 0;
    font-size: 10px;
    color: #6b6f79;
    text-align: center;
  }
  .legend span { margin: 0 6px; }
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
    .top-bar { border-radius: 10px; padding: 8px 10px; gap: 4px; min-height: 34px; }
    .month-select-group { gap: 2px; }
    .top-date-select { font-size: 10px; }
    .nav-chevron { font-size: 7px; margin: 0 2px; }
    .top-meta { font-size: 5px; white-space: normal; }
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
    .team-count { font-size: 5px; }
    .rank-change { font-size: 6px; padding: 2px 6px; border-radius: 10px; }
    .member-col-label { font-size: 6px; padding: 5px 8px 4px; }
    .member-col-label .col-label-text, .member-col-label .unit-label { font-size: 6px; }
    .member-row { padding: 4px 8px; min-height: 14px; border-left-width: 2px; }
    .member-name { font-size: 6px; gap: 3px; }
    .member-name-link { gap: 3px; }
    .bday-mark { font-size: 4px; }
    .member-value { font-size: 6px; padding-left: 4px; }
    .team-footer { padding: 6px 5px 7px; gap: 3px; }
    .stat-card { padding: 7px 4px; border-radius: 8px; }
    .stat-card-header { gap: 2px; margin-bottom: 2px; margin-left: -3px; }
    .stat-icon { width: 6px; height: 6px; }
    .stat-label { font-size: 6px; }
    .stat-value { font-size: 7px; }
    .legend { font-size: 5px; margin-top: 8px; }
    .legend span { margin: 0 3px; }
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
# 방송시간 페이지: 수장/전력외도 집계에 포함
BROADCAST_METRIC = Metric(key="broadcast", field="broadcast_seconds", exclude_roles=False,
                           format_fn=format_broadcast_time, unit_label="방송시간")
# 누적시청자 페이지(신규): 별풍선과 동일하게 수장/전력외 직책은 집계에서 제외
VIEWER_METRIC = Metric(key="viewer", field="cumulative_viewers", exclude_roles=True,
                        format_fn=fmt, unit_label="누적시청자")
METRICS = [BALLOON_METRIC, BROADCAST_METRIC, VIEWER_METRIC]

# 팀 카드 하단 요약 카드(전체 합계/여자 평균/전체 평균)용 아이콘. 외부 아이콘
# 폰트 CDN을 새로 추가하지 않고(폰트도 self-host해서 로딩 지연을 없앴는데
# 아이콘 때문에 다시 외부 CDN을 걸면 그 노력이 무의미해짐) 가벼운 인라인 SVG로
# 직접 그린다. stroke="currentColor"라 .stat-icon의 color 값을 그대로 따라간다.
_ICON_ATTRS = 'viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
STAT_ICON_SUM = f'<svg class="stat-icon" {_ICON_ATTRS}><ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v5c0 1.66 3.13 3 7 3s7-1.34 7-3V6"/><path d="M5 11v5c0 1.66 3.13 3 7 3s7-1.34 7-3v-5"/></svg>'
STAT_ICON_FEMALE = f'<svg class="stat-icon" {_ICON_ATTRS}><circle cx="12" cy="9" r="5"/><path d="M12 14v7M9 18h6"/></svg>'
STAT_ICON_AVG = f'<svg class="stat-icon" {_ICON_ATTRS}><path d="M4 20V10M12 20V4M20 20v-7"/></svg>'

# 개인 프로필 페이지(profile.html?id=...)에서 쓰는 SOOP 프로필사진/방송국 URL.
# {id} 자리를 실제 SOOP 아이디로 그대로 바꿔치기한다.
# {id}는 SOOP 아이디, {prefix}는 그 아이디의 첫 두 글자(폴더 샤딩용) -
# JS에서 targetId.substring(0, 2)로 계산해서 넣는다.
SOOP_PROFILE_IMG_TEMPLATE = "https://profile.img.sooplive.com/LOGO/{prefix}/{id}/{id}.jpg"
SOOP_STATION_TEMPLATE = "https://www.sooplive.com/station/{id}"

# 방송국 링크 아이콘(SOOP 로고) - 레포에 별도 이미지 파일을 안 두고 base64로
# HTML에 직접 박아넣는다. 파일 배치를 깜빡하거나 경로가 어긋나서 아이콘이
# 깨지는 일 자체를 원천적으로 없애기 위함.
SOOP_LOGO_ICON_DATA_URI = "data:image/png;base64,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"


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
        team = m.get("team", "미분류")
        if team in NON_TEAM_LABELS:
            continue
        teams.setdefault(team, []).append(m)
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
    prev_data = _load_json_cached(path)
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
        member_id = m.get("id")
        name_inner = f"{m['nickname']}{bday_html}"
        name_content = (
            f"<a class='member-name-link' href='{logo_prefix}profile.html?id={member_id}'>{name_inner}</a>"
            if member_id else name_inner
        )
        return (
            f"<div class='member-row {row_class}'>"
            f"<span class='member-name'>{name_content}</span>"
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
          <div class="stat-card-header">{STAT_ICON_SUM}<span class="stat-label">전체 합계</span></div>
          <div class="stat-value">{metric.format_fn(total_sum)}</div>
        </div>
        <div class="stat-card female-avg">
          <div class="stat-card-header">{STAT_ICON_FEMALE}<span class="stat-label">여자 평균</span></div>
          <div class="stat-value">{metric.format_fn(female_avg)}</div>
        </div>
        <div class="stat-card total-avg">
          <div class="stat-card-header">{STAT_ICON_AVG}<span class="stat-label">전체 평균</span></div>
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


def compute_panel_context(all_data: list, metrics: list) -> dict:
    """(연,월,지표)별 tiers/전체순위/전달순위를 미리 한 번씩만 계산해서 캐싱한다.
    이 값들은 어느 팀 페이지를 만드는지와 무관(항상 전체 멤버 기준)하므로,
    전체 페이지 1개 + 팀별 단독 페이지 N개가 전부 이 결과를 그대로 재사용한다.
    -> 팀 수만큼 반복되던 정렬/집계/아카이브 파일 읽기를 (연,월,지표) 조합 수만큼으로 줄인다."""
    context = {}
    for data in all_data:
        y, m = data["year"], data["month"]
        for metric in metrics:
            tiers = compute_percentile_tiers(data["members"], metric)
            current_ranks = compute_team_ranks(data["members"], metric)
            prev_ranks = load_previous_ranks(y, m, metric)
            context[(y, m, metric.key)] = (tiers, current_ranks, prev_ranks)
    return context


def build_grid_panel(data: dict, metric: Metric, logo_prefix: str, context: dict) -> str:
    """전체 팀 그리드 패널 (모든 팀 카드, 전체 평균 내림차순 정렬). 팀 이름을 누르면
    현재 보고 있던 연/월/지표를 그대로 유지한 채 그 팀의 단독 페이지로 이동한다."""
    members = data["members"]
    teams = group_teams(members)
    tiers, current_ranks, prev_ranks = context[(data["year"], data["month"], metric.key)]

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


def build_single_team_panel(data: dict, team_name: str, metric: Metric, logo_prefix: str, context: dict) -> str:
    """특정 팀 하나만 담은 패널. 그 달에 팀이 없으면 안내 문구만 표시."""
    teams = group_teams(data["members"])
    team_members = teams.get(team_name)
    if team_members is None:
        return (
            '<div class="grid single-team"><div class="team-card" '
            'style="padding:24px;text-align:center;color:#999;font-size:13px;">'
            '이 달에는 팀 정보가 없습니다.</div></div>'
        )

    tiers, current_ranks, prev_ranks = context[(data["year"], data["month"], metric.key)]
    badge = rank_change_badge(current_ranks[team_name], prev_ranks, team_name)
    _, card_html = build_team_card(team_name, team_members, data["month"], tiers, logo_prefix, badge, metric)
    return f'<div class="grid single-team">{card_html}</div>'


def page_shell(*, top_bar_html: str, body_html: str, include_mobile_css: bool = True,
               title: str, extra_script: str, logo_prefix: str = "", show_legend: bool = True) -> str:
    """모든 페이지 공통 뼈대. 팀 단독 페이지는 카드 1개뿐이라 모바일 압축 스타일이
    필요없어서 include_mobile_css=False로 뺄 수 있음. '수장/전력외' 범례 항목은
    id로 표시해두고, 지표 전환 시 자바스크립트가 보였다/숨겼다 한다. 프로필
    페이지처럼 상위%/수장·전력외 개념 자체가 없는 페이지는 show_legend=False로
    범례 자체를 뺄 수 있음.

    Pretendard 폰트는 CDN에서 실시간으로 불러오지 않고 docs/fonts/에 self-host해서
    쓴다 (scripts/download_font.py가 최초 1회 받아둠) - 로드시 폰트가 늦게 적용되며
    깜빡이는 현상(FOUT)을 최소화하기 위함. logo_prefix로 로고와 동일하게 상대경로를
    맞춘다 (전체 페이지는 "", 팀 단독 페이지는 "../")."""
    style = PAGE_CSS + (MOBILE_CSS if include_mobile_css else "")
    font_url = f"{logo_prefix}fonts/PretendardVariable.woff2"

    # 팀 단독 페이지의 뒤로가기 링크(top_bar_html 안에 이미 조건부로 포함됨)는
    # "이 페이지에 어떻게 들어왔는지"로 보임/숨김을 자동 판단한다.
    # - 최상위 문서(iframe 아님, 브라우저에서 직접 team URL로 들어온 경우): 그냥 보임
    # - iframe 안 + referrer가 우리 사이트의 index.html(=전체 페이지 임베드
    #   안에서 팀 이름을 눌러 같은 iframe 안에서 넘어온 경우): 보임
    # - iframe 안 + 그 외(=게시글이 이 team 페이지 URL을 iframe src로 직접
    #   박아놓은 단독 임베드인 경우): 숨김
    # getElementById가 못 찾으면(=전체 페이지) 아무 일도 안 하고 지나간다.
    iframe_hide_script = """<script>
(function () {
  var backLink = document.getElementById('back-to-full-link');
  if (!backLink) return;
  if (window.self === window.top) return;
  var cameFromFullPage = false;
  try {
    var ref = new URL(document.referrer);
    cameFromFullPage = ref.origin === window.location.origin && /\\/(index\\.html)?$/.test(ref.pathname);
  } catch (e) {}
  if (!cameFromFullPage) {
    backLink.style.display = 'none';
  }
})();
</script>"""

    legend_html = ""
    if show_legend:
        legend_html = """<div class="legend">
    <span><span class="sw" style="background:#d6e9fb;"></span>상위 1%</span>
    <span><span class="sw" style="background:#dcefdd;"></span>상위 5%</span>
    <span><span class="sw" style="background:#fbf3cf;"></span>상위 10%</span>
    <span id="role-legend-item"><span class="sw" style="background:#fadada;"></span>수장/전력외</span>
    <span>🎂 생일</span>
  </div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="preload" href="{font_url}" as="font" type="font/woff2" crossorigin>
<style>
@font-face {{
  font-family: 'Pretendard Variable';
  font-weight: 45 920;
  font-style: normal;
  font-display: block;
  src: url('{font_url}') format('woff2-variations');
}}
{style}
</style>
</head>
<body>
  {top_bar_html}
  {body_html}
  {legend_html}
{extra_script}
{iframe_hide_script}
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
        d = _load_json_cached(path)
        d["members"] = normalize_balloons(d["members"])
        all_data.append(d)

    return current_data, all_data


def assemble_single_page(all_data: list, current_year: int, current_month: int,
                          panel_builder, logo_prefix: str, include_mobile_css: bool,
                          page_title_base: str, context: dict) -> str:
    """
    all_data의 모든 (연,월) x (별풍선/방송시간) 조합을 패널로 미리 렌더링해서
    하나의 페이지에 담고, 연도/월/지표 select 3개 + 자바스크립트로 전환하게 만든다.
    panel_builder(data, metric, logo_prefix, context) -> 패널 안쪽 HTML (grid div)
    context는 compute_panel_context()에서 미리 계산해둔 tiers/순위 - 어느 페이지를
    만들든(전체든 팀별 단독이든) 같은 값을 재사용해 중복 계산을 없앤다.
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
            panel_inner = panel_builder(data, metric, logo_prefix, context)
            style_attr = "" if key == default_key else " style=\"display:none;\""
            panels_html.append(f"<div class='page-panel' data-key='{key}'{style_attr}>{panel_inner}</div>")

            teams_for_meta = group_teams(data["members"])
            metadata[key] = {
                "teamCount": len(teams_for_meta),
                "memberCount": sum(len(v) for v in teams_for_meta.values()),
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

    default_meta = metadata[default_key]
    default_meta_html = (
        f"{default_meta['teamCount']}팀 · {default_meta['memberCount']}명 · "
        f"업데이트 {default_meta['updatedAt']} · 출처: "
        f"<a href='https://poonggo.com' target='_blank' rel='noopener' class='source-link'>풍고</a>"
    )

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

    # 팀 단독 페이지(logo_prefix="../")에서만 뒤로가기 링크를 둔다. "연도/월/지표"
    # 부분(nav_html)은 절대 건드리지 않고, 카드 오른쪽 메타 텍스트 아래에 작게
    # 쌓아서 카드 높이가 늘어나지 않게 한다(카드 바깥에 새 줄을 만들면 그만큼
    # 페이지 전체가 밀려 내려가서 이 방식으로 바꿈).
    back_link_html = ""
    if logo_prefix:
        back_link_html = (
            f'<a href="{logo_prefix}index.html" id="back-to-full-link" class="back-link">'
            f'← 전체페이지</a>'
        )

    top_bar_html = f"""
  <div class="top-bar">
    {nav_html}
    <span class="top-meta-group">
      {back_link_html}
      {'<span class="top-meta-sep">·</span>' if back_link_html else ''}
      <span class="top-meta" id="top-meta-text">{default_meta_html}</span>
    </span>
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

    // 팀 단독 페이지에서만 존재하는 뒤로가기 링크 - 지금 보고 있던 연/월/지표를
    // 그대로 유지한 채 전체 페이지로 돌아가도록 쿼리파라미터를 갱신해둔다.
    var backLink = document.getElementById('back-to-full-link');
    if (backLink) {{
      backLink.href = '../index.html?y=' + yearSel.value + '&m=' + pad(monthSel.value) + '&metric=' + metricSel.value;
    }}
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
    if (qmetric && (qmetric === 'balloon' || qmetric === 'broadcast' || qmetric === 'viewer')) {{
      metricSel.value = qmetric;
    }}
  }})();

  apply();
}})();
</script>"""

    return page_shell(
        top_bar_html=top_bar_html, body_html=body_html, include_mobile_css=include_mobile_css,
        title=f"{page_title_base} {BALLOON_METRIC.unit_label}", extra_script=extra_script,
        logo_prefix=logo_prefix,
    )


def build_profile_page(all_data: list) -> str:
    """
    개인 프로필 페이지(docs/profile.html) - 팀 페이지처럼 사람마다 파일을 만드는
    대신 이 파일 하나로 전부 대응한다. URL에 ?id=SOOP아이디 를 붙여서 접근하면
    자바스크립트가 그 아이디에 맞는 데이터를 찾아 렌더링한다 (GitHub Pages는
    서버 라우팅이 없어서 클라이언트에서 처리).

    한 번도 members.json에 등록된 적 없는 아이디로 들어오면 그냥 빈 화면으로
    남긴다(요청사항). 등록은 됐지만 특정 달에 데이터가 없는 경우(그 달엔 아직
    팀이 아니었다거나)는 그 달을 선택하면 카드 자체가 숨겨진다.

    이번 달 별풍선/방송시간/누적시청자만 보여주고(팀 내 순위는 표시 안 함),
    연/월 select로 과거 데이터도 조회 가능. 스폰전적(eloboard.com)은 아직
    크롤링 허가를 못 받아서 "준비중"으로 자리만 잡아둔다.
    """
    current_year, current_month = all_data[0]["year"], all_data[0]["month"]

    years_months = {}  # {연도: {월, 월, ...}}
    profiles_by_key = {}  # {"YYYY-MM": {"membersById": {...}, "updatedAt": ...}}
    all_ids = set()
    all_team_names = set()

    for data in all_data:
        y, m = data["year"], data["month"]
        years_months.setdefault(y, set()).add(m)
        key = f"{y:04d}-{m:02d}"

        members_by_id = {}
        for mem in data["members"]:
            mid = mem.get("id")
            if not mid:
                continue
            all_ids.add(mid)
            if mem.get("team"):
                all_team_names.add(mem["team"])
            members_by_id[mid] = {
                "nickname": mem.get("nickname"),
                "gender": mem.get("gender"),
                "birthdate": mem.get("birthdate"),
                "team": mem.get("team"),
                "role": mem.get("role"),
                "race": mem.get("race"),
                "tier": mem.get("tier"),
                "balloons": mem.get("balloons", 0),
                "broadcast_seconds": mem.get("broadcast_seconds", 0),
                "cumulative_viewers": mem.get("cumulative_viewers", 0),
            }
        profiles_by_key[key] = {"membersById": members_by_id, "updatedAt": data["updated_at"]}

    # 팀 카드/팀 페이지랑 동일한 로고 색상 추출 로직을 그대로 재사용해서, 프로필
    # 카드 상단 바도 그 사람 소속팀 색으로 맞춘다. 로고가 없는 팀이나 team이
    # 아예 없는 경우(탈퇴 등)는 기본 파란색(DEFAULT_TOPBAR_COLOR)으로 빠진다.
    team_colors = {team: get_team_topbar_color(team) for team in all_team_names}
    team_colors_json = json.dumps(team_colors, ensure_ascii=False)

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
    months_by_year_json = json.dumps({str(y): sorted(ms, reverse=True) for y, ms in years_months.items()})
    profiles_json = json.dumps(profiles_by_key, ensure_ascii=False)
    all_ids_json = json.dumps(sorted(all_ids))

    nav_html = f"""
  <span class="month-select-group">
    <select class="top-date-select" id="ms-year-select">{year_options}</select>
    <span class="nav-chevron">⌄</span>
    <select class="top-date-select" id="ms-month-select">{month_options}</select>
    <span class="nav-chevron">⌄</span>
  </span>
    """

    top_bar_html = f"""
  <div class="top-bar">
    {nav_html}
    <span class="top-meta-group">
      <a href="#" id="profile-back-link" class="back-link" style="display:none;">← 뒤로가기</a>
      <span class="top-meta-sep" id="profile-back-sep" style="display:none;">·</span>
      <span class="top-meta" id="top-meta-text"></span>
    </span>
  </div>
    """

    body_html = f"""
  <div style="max-width:480px;margin:0 auto;">
  <div class="team-card" id="profile-card" style="display:none;">
    <div class="team-card-topbar" id="profile-topbar"></div>
    <div class="team-header">
      <div class="team-header-left">
        <img class="profile-photo-img" id="profile-photo" alt="">
        <span class="team-name" id="profile-nickname"></span>
      </div>
    </div>
    <div class="profile-info">
      <div class="profile-row"><span class="profile-row-label">성별</span><span class="profile-row-value" id="profile-gender"></span></div>
      <div class="profile-row"><span class="profile-row-label">생년월일</span><span class="profile-row-value" id="profile-birthdate"></span></div>
      <div class="profile-row"><span class="profile-row-label">소속</span><span class="profile-row-value" id="profile-team"></span></div>
      <div class="profile-row"><span class="profile-row-label">직책</span><span class="profile-row-value" id="profile-role"></span></div>
      <div class="profile-row"><span class="profile-row-label">종족</span><span class="profile-row-value" id="profile-race"></span></div>
      <div class="profile-row"><span class="profile-row-label">티어</span><span class="profile-row-value" id="profile-tier"></span></div>
      <div class="profile-row">
        <span class="profile-row-label">방송국</span>
        <a id="profile-station-link" href="#" target="_blank" rel="noopener">
          <img class="profile-station-icon" src="{SOOP_LOGO_ICON_DATA_URI}" alt="방송국 바로가기">
        </a>
      </div>
    </div>
    <div class="team-footer">
      <div class="stat-card">
        <div class="stat-card-header no-icon"><span class="stat-label">별풍선</span></div>
        <div class="stat-value" id="profile-balloons"></div>
      </div>
      <div class="stat-card">
        <div class="stat-card-header no-icon"><span class="stat-label">방송시간</span></div>
        <div class="stat-value" id="profile-broadcast"></div>
      </div>
      <div class="stat-card">
        <div class="stat-card-header no-icon"><span class="stat-label">누적시청자</span></div>
        <div class="stat-value" id="profile-viewers"></div>
      </div>
      <div class="stat-card">
        <div class="stat-card-header no-icon"><span class="stat-label">스폰전적</span></div>
        <div class="stat-value" style="font-size:11px;color:#a4a8b2;">준비중</div>
      </div>
    </div>
  </div>
  </div>
    """

    extra_script = f"""<script>
(function () {{
  var profiles = {profiles_json};
  var teamColors = {team_colors_json};
  var monthsByYear = {months_by_year_json};
  var allIds = {all_ids_json};
  var targetId = new URLSearchParams(window.location.search).get('id');

  // 등록된 적이 한 번도 없는 아이디면 그냥 빈 화면으로 남긴다.
  if (!targetId || allIds.indexOf(targetId) === -1) {{
    return;
  }}

  // 뒤로가기: 전체페이지에서 눌러서 왔으면 전체페이지로, 팀페이지에서 눌러서
  // 왔으면 그 팀페이지로 - referrer(직전 페이지 주소)를 그대로 목적지로 쓴다.
  // 이러면 전체페이지/팀페이지가 그때 보고 있던 연/월/지표 상태까지 그대로
  // 유지된 채로 돌아간다. referrer가 없거나(직접 URL 입력 등) 다른 사이트에서
  // 온 경우는 뒤로 갈 곳이 마땅치 않으므로 버튼 자체를 숨긴다.
  (function () {{
    var backLink = document.getElementById('profile-back-link');
    var backSep = document.getElementById('profile-back-sep');
    if (!document.referrer) return;
    try {{
      var ref = new URL(document.referrer);
      if (ref.origin !== window.location.origin) return;
      backLink.href = document.referrer;
      backLink.style.display = '';
      backSep.style.display = '';
    }} catch (e) {{}}
  }})();

  var yearSel = document.getElementById('ms-year-select');
  var monthSel = document.getElementById('ms-month-select');
  var metaSpan = document.getElementById('top-meta-text');
  var card = document.getElementById('profile-card');

  function pad(n) {{ n = parseInt(n, 10); return (n < 10 ? '0' : '') + n; }}
  function fmt(n) {{ return (n || 0).toLocaleString('ko-KR'); }}
  function fmtBroadcast(sec) {{
    sec = sec || 0;
    var h = Math.floor(sec / 3600);
    var m = Math.floor((sec % 3600) / 60);
    var s = Math.floor(sec % 60);
    var pad2 = function (n) {{ return (n < 10 ? '0' : '') + n; }};
    return pad2(h) + ':' + pad2(m) + ':' + pad2(s);
  }}

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

  function apply() {{
    var key = yearSel.value + '-' + pad(monthSel.value);
    var monthData = profiles[key];
    var member = monthData ? monthData.membersById[targetId] : null;

    if (!member) {{
      // 등록은 됐지만 이 달엔 데이터가 없는 경우 - 카드만 숨긴다.
      card.style.display = 'none';
      metaSpan.textContent = '';
      return;
    }}

    card.style.display = '';
    var photoImg = document.getElementById('profile-photo');
    photoImg.onerror = function () {{ this.style.visibility = 'hidden'; }};
    photoImg.onload = function () {{ this.style.visibility = ''; }};
    var idPrefix = targetId.substring(0, 2);
    photoImg.src = '{SOOP_PROFILE_IMG_TEMPLATE}'.split('{{prefix}}').join(idPrefix).split('{{id}}').join(targetId);
    document.getElementById('profile-topbar').style.background = teamColors[member.team] || '{DEFAULT_TOPBAR_COLOR}';
    document.getElementById('profile-nickname').textContent = member.nickname || '';
    document.getElementById('profile-gender').textContent = member.gender === 'f' ? '여' : '남';
    document.getElementById('profile-birthdate').textContent = member.birthdate || '-';
    document.getElementById('profile-team').textContent = member.team || '-';
    document.getElementById('profile-role').textContent = member.role || '-';
    document.getElementById('profile-race').textContent = member.race || '-';
    document.getElementById('profile-tier').textContent = member.tier || '-';
    document.getElementById('profile-station-link').href = '{SOOP_STATION_TEMPLATE}'.split('{{id}}').join(targetId);
    document.getElementById('profile-balloons').textContent = fmt(member.balloons);
    document.getElementById('profile-broadcast').textContent = fmtBroadcast(member.broadcast_seconds);
    document.getElementById('profile-viewers').textContent = fmt(member.cumulative_viewers);

    document.title = (member.nickname || targetId) + ' 프로필';
    metaSpan.innerHTML = '업데이트 ' + monthData.updatedAt +
      ' · 출처: <a href="https://poonggo.com" target="_blank" rel="noopener" class="source-link">풍고</a>';
  }}

  yearSel.addEventListener('change', function () {{
    var year = yearSel.value;
    var monthsInYear = monthsByYear[year] || [];
    populateMonths(year, monthsInYear.length ? monthsInYear[0] : null);
    apply();
  }});
  monthSel.addEventListener('change', apply);

  apply();
}})();
</script>"""

    return page_shell(
        top_bar_html=top_bar_html, body_html=body_html, include_mobile_css=False,
        title="프로필", extra_script=extra_script, logo_prefix="", show_legend=False,
    )


def main():
    current_data, all_data = load_all_month_data()
    current_year, current_month = current_data["year"], current_data["month"]

    # (연,월,지표)별 tiers/순위를 한 번만 계산 - 아래 전체 페이지 + 팀별 단독 페이지
    # N개가 전부 이 결과를 재사용한다 (팀 수만큼 반복 계산하던 걸 없앰)
    context = compute_panel_context(all_data, METRICS)

    # 전체 페이지 (모든 팀)
    html = assemble_single_page(
        all_data, current_year, current_month,
        panel_builder=build_grid_panel, logo_prefix="",
        include_mobile_css=True, page_title_base="팀별", context=context,
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
            def _panel_builder(data, metric, logo_prefix, context, _team=team_name):
                return build_single_team_panel(data, _team, metric, logo_prefix, context)

            team_html = assemble_single_page(
                all_data, current_year, current_month,
                panel_builder=_panel_builder, logo_prefix="../",
                include_mobile_css=False, page_title_base=team_name, context=context,
            )
            out_path = OUTPUT_TEAMS_DIR / f"{team_name}.html"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(team_html)
            print(f"완료: {out_path} 생성됨")

    # 개인 프로필 페이지 - profile.html?id=SOOP아이디 로 전 인원 대응
    profile_html = build_profile_page(all_data)
    with open(OUTPUT_PROFILE_PATH, "w", encoding="utf-8") as f:
        f.write(profile_html)
    print(f"완료: {OUTPUT_PROFILE_PATH} 생성됨")


if __name__ == "__main__":
    main()
