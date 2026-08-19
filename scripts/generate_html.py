"""
data/latest.json (이번 달) 과 data/archive/*.json (과거 달)을 읽어서
docs/index.html (이번 달) + docs/archive/YYYY-MM.html (과거 달) 로 렌더링하는 스크립트.

과거 달 데이터는 fetch_data.py가 달이 바뀔 때 latest.json을 통째로 복사해서
data/archive/에 보관해둔 것 - 그 시점의 team/gender/role이 멤버마다 그대로 들어있어서
팀 구성이 바뀌어도 "그 당시 배정" 그대로 재현된다.

팀별 표: 표 1개, [남자 멤버 | 별풍선 | 여자 멤버 | 별풍선] 4열, 각각 별풍선 내림차순 정렬.
하단에 합계/평균/인원 행 포함. 별풍선 0이거나 직책이 수장/전력외인 사람은 집계·상위% 계산에서 제외
(수장/전력외는 표에 빨간 배경으로 표시, 0인 사람은 빈 칸으로 표시).
이름 옆에는 그 달의 생일이면 🎂 표시.
모든 페이지 상단에 "이번 달 / 과거 달들" 이동 링크가 붙는다.

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

EXCLUDED_ROLES = {"수장", "전력외"}


def fmt(n: int) -> str:
    return f"{n:,}"


def parse_birthdate(bd):
    if not bd:
        return None
    try:
        parts = bd.split("-")
        return int(parts[1]), int(parts[2])
    except (IndexError, ValueError):
        return None


def is_counted(m):
    return m.get("role") not in EXCLUDED_ROLES and m["balloons"] != 0


def compute_percentile_tiers(members: list):
    pool = [m for m in members if is_counted(m)]
    ranked = sorted(pool, key=lambda m: -m["balloons"])
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


def name_cell(m, current_month):
    bday = parse_birthdate(m.get("birthdate"))
    bday_html = "<span class='bday-mark'>🎂</span>" if bday and bday[0] == current_month else ""
    return (
        f"<div class='name-cell'>"
        f"<span class='name-left'>{m['nickname']}</span>"
        f"{bday_html}"
        f"</div>"
    )


def value_class(m, tiers):
    classes = []
    if m.get("role") in EXCLUDED_ROLES:
        classes.append("excluded")
    tier = tiers.get((m["nickname"], m["team"]))
    if tier:
        classes.append(tier)
    return " ".join(classes)


def value_text(m):
    return fmt(m["balloons"]) if m["balloons"] != 0 else ""


def build_team_card(team_name: str, members: list, current_month: int, tiers: dict):
    counted = [m for m in members if is_counted(m)]
    males_counted = [m for m in counted if m["gender"] == "m"]
    females_counted = [m for m in counted if m["gender"] == "f"]

    male_sum = sum(m["balloons"] for m in males_counted)
    female_sum = sum(m["balloons"] for m in females_counted)
    total_sum = male_sum + female_sum
    male_avg = round(male_sum / len(males_counted)) if males_counted else 0
    female_avg = round(female_sum / len(females_counted)) if females_counted else 0
    total_avg = round(total_sum / len(counted)) if counted else 0

    males_all = sorted([m for m in members if m["gender"] == "m"], key=lambda x: -x["balloons"])
    females_all = sorted([m for m in members if m["gender"] == "f"], key=lambda x: -x["balloons"])

    max_rows = max(len(males_all), len(females_all), 1)

    body_rows = []
    for i in range(max_rows):
        if i < len(males_all):
            m = males_all[i]
            m_name = f"<td class='name-td'>{name_cell(m, current_month)}</td>"
            m_val = f"<td class='num {value_class(m, tiers)}'>{value_text(m)}</td>"
        else:
            m_name = "<td class='name-td empty'></td>"
            m_val = "<td class='num empty'></td>"

        if i < len(females_all):
            f_ = females_all[i]
            f_name = f"<td class='name-td'>{name_cell(f_, current_month)}</td>"
            f_val = f"<td class='num {value_class(f_, tiers)}'>{value_text(f_)}</td>"
        else:
            f_name = "<td class='name-td empty'></td>"
            f_val = "<td class='num empty'></td>"

        body_rows.append(f"<tr>{m_name}{m_val}{f_name}{f_val}</tr>")

    body_html = "".join(body_rows)

    male_n, female_n = len(males_all), len(females_all)
    total_n = male_n + female_n

    summary_html = f"""
      <tr class="summary-row">
        <td>남자 합계</td><td class="num">{fmt(male_sum)}</td>
        <td>여자 합계</td><td class="num">{fmt(female_sum)}</td>
      </tr>
      <tr class="summary-row">
        <td>남자 평균</td><td class="num">{fmt(male_avg)}</td>
        <td>여자 평균</td><td class="num female-avg">{fmt(female_avg)}</td>
      </tr>
      <tr class="summary-row">
        <td>전체 합계</td><td class="num total-sum">{fmt(total_sum)}</td>
        <td>전체 평균</td><td class="num total-avg">{fmt(total_avg)}</td>
      </tr>
      <tr class="summary-row personnel-row">
        <td class="personnel-label">인원</td>
        <td colspan="3" class="personnel-value">총 {total_n}명 / 남자 {male_n}명 / 여자 {female_n}명</td>
      </tr>
    """

    return total_avg, f"""
    <div class="team-card">
      <table>
        <thead>
          <tr><th colspan="4" class="team-name-row">{team_name}</th></tr>
          <tr><th class="col-header">남자 멤버</th><th class="col-header">별풍선</th><th class="col-header">여자 멤버</th><th class="col-header">별풍선</th></tr>
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


def build_month_select(archive_slugs: list, current_year: int, current_month: int,
                        active_slug: str, is_archive_page: bool) -> str:
    """
    상단 왼쪽 '2026년 08월' 큰 글씨 자리를 대신하는 월 선택 드롭다운.
    선택하면 해당 달 페이지로 바로 이동한다 (option value = 상대경로).
    """
    current_slug = f"{current_year:04d}-{current_month:02d}"
    options = []

    label = f"{current_year}년 {current_month:02d}월"
    href = "../index.html" if is_archive_page else "index.html"
    selected = " selected" if active_slug == current_slug else ""
    options.append(f"<option value='{href}'{selected}>{label}</option>")

    for slug in archive_slugs:
        year, month = slug.split("-")
        label = f"{year}년 {int(month):02d}월"
        href = f"{slug}.html" if is_archive_page else f"archive/{slug}.html"
        selected = " selected" if slug == active_slug else ""
        options.append(f"<option value='{href}'{selected}>{label}</option>")

    options_html = "".join(options)
    return (
        "<select class='top-date-select' "
        "onchange=\"if(this.value) window.location.href=this.value;\">"
        f"{options_html}</select>"
    )


def render_page(data: dict, archive_slugs: list, current_year: int, current_month: int,
                 is_archive: bool = False) -> str:
    active_slug = f"{data['year']:04d}-{data['month']:02d}"
    month_select_html = build_month_select(archive_slugs, current_year, current_month, active_slug, is_archive)

    members = data["members"]

    teams = OrderedDict()
    for m in members:
        teams.setdefault(m.get("team", "미분류"), []).append(m)

    tiers = compute_percentile_tiers(members)

    team_cards = []
    for team_name, team_members in teams.items():
        avg, html = build_team_card(team_name, team_members, data["month"], tiers)
        team_cards.append((avg, html))

    team_cards.sort(key=lambda x: -x[0])
    cards_html = "".join(html for _, html in team_cards)

    team_count = len(teams)
    member_count = len(members)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>팀별 별풍선 랭킹</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');

  * {{ box-sizing: border-box; }}

  body {{
    font-family: 'Noto Sans KR', -apple-system, "Malgun Gothic", sans-serif;
    background: #f2f3f5;
    margin: 0;
    padding: 24px 16px;
    color: #222;
  }}
  .top-bar {{
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
  }}
  .top-date-select {{
    font-size: 18px;
    font-weight: 700;
    color: #222;
    border: none;
    background: transparent;
    cursor: pointer;
    font-family: inherit;
    padding: 2px 0;
  }}
  .top-date-select:hover {{ color: #25528F; }}
  .top-meta {{
    font-size: 13px;
    color: #888;
  }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 14px;
    max-width: 1080px;
    margin: 0 auto;
  }}
  .team-card {{
    background: #fff;
    border: 1px solid #e5e6ea;
    border-radius: 10px;
    padding: 10px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  th.team-name-row {{
    background: #f7f8fa;
    color: #222;
    font-weight: 700;
  }}
  th.col-header {{
    background: #25528F;
    color: #fff;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
    table-layout: fixed;
  }}
  th, td {{
    border: 1px solid #eceef1;
    padding: 3px 4px;
    text-align: center;
  }}
  th {{
    background: #f7f8fa;
    font-weight: 700;
    color: #555;
  }}
  td.name-td {{
    text-align: center;
    background: #f7f8fa;
  }}
  .name-cell {{
    position: relative;
    text-align: center;
    min-height: 14px;
  }}
  .name-left {{ white-space: nowrap; font-weight: 700; }}
  .bday-mark {{
    position: absolute;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    font-size: 10px;
  }}

  td.num {{
    text-align: center;
    font-variant-numeric: tabular-nums;
    font-weight: 500;
  }}
  td.empty {{ background: #fff; }}

  td.excluded {{
    background: #fadada !important;
    color: #222;
    font-weight: 700;
  }}
  td.tier1, td.tier5, td.tier10 {{ font-weight: 700; }}
  td.tier1 {{ background: #d6e9fb; }}
  td.tier5 {{ background: #dcefdd; }}
  td.tier10 {{ background: #fbf3cf; }}
  td.excluded.tier1, td.excluded.tier5, td.excluded.tier10 {{
    background: #fadada !important;
  }}

  tr.summary-row td {{ font-size: 11px; background: #fafbfc; font-weight: 600; text-align: center; }}
  td.total-sum, td.total-avg {{ background: #CDD7F5 !important; font-weight: 700; }}
  td.female-avg {{ background: #CDE1E1 !important; font-weight: 700; }}
  td.personnel-label {{ background: #f7f8fa !important; }}
  td.personnel-value {{ background: #ffffff !important; }}

  .legend {{
    max-width: 1080px;
    margin: 14px auto 0;
    font-size: 11px;
    color: #888;
    text-align: center;
  }}
  .legend span {{ margin: 0 8px; }}
  .legend .sw {{
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 2px;
    margin-right: 3px;
    vertical-align: middle;
  }}

  .archive-banner {{
    max-width: 1080px;
    margin: 0 auto 14px;
    text-align: center;
    font-size: 12px;
    color: #a15c1f;
    background: #fff3e0;
    border: 1px solid #f0cf9a;
    border-radius: 8px;
    padding: 6px;
  }}

  /* 모바일: 한 줄에 2팀씩 보이도록 강제 2열 + 여백/폰트 축소 */
  @media (max-width: 600px) {{
    body {{ padding: 12px 6px; }}
    .grid {{
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }}
    .team-card {{
      padding: 5px;
      border-radius: 7px;
    }}
    table {{ font-size: 8px; }}
    th, td {{ padding: 2px 1px; }}
    tr.summary-row td {{ font-size: 8px; padding: 2px 1px; }}
    .name-left {{ font-size: 8px; }}
    .bday-mark {{ font-size: 8px; }}
    .top-bar {{ padding: 10px 14px; }}
    .top-date-select {{ font-size: 14px; }}
    .top-meta {{ font-size: 10px; }}
    .legend {{ font-size: 9px; }}
  }}
</style>
</head>
<body>
  {"<div class='archive-banner'>📁 이 페이지는 지난 기록입니다 (당시 팀 구성 기준)</div>" if is_archive else ""}
  <div class="top-bar">
    {month_select_html}
    <span class="top-meta">총인원 {member_count} / 팀 {team_count} / 업데이트 {data['updated_at']} / 출처: 풍투데이</span>
  </div>
  <div class="grid">
    {cards_html}
  </div>
  <div class="legend">
    <span><span class="sw" style="background:#d6e9fb;"></span>상위 1%</span>
    <span><span class="sw" style="background:#dcefdd;"></span>상위 5%</span>
    <span><span class="sw" style="background:#fbf3cf;"></span>상위 10%</span>
    <span><span class="sw" style="background:#fadada;"></span>수장/전력외</span>
    <span>🎂 그 달의 생일</span>
  </div>
</body>
</html>
"""
    return html


def main():
    archive_slugs = list_archive_slugs()

    # 이번 달 페이지
    if not DATA_PATH.exists():
        raise SystemExit(f"[오류] {DATA_PATH} 가 없습니다. 먼저 fetch_data.py를 실행하세요.")

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        current_data = json.load(f)

    current_year, current_month = current_data["year"], current_data["month"]

    html = render_page(current_data, archive_slugs, current_year, current_month, is_archive=False)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"완료: {OUTPUT_PATH} 생성됨")

    # 과거 달 페이지들
    if archive_slugs:
        OUTPUT_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        for slug in archive_slugs:
            archive_json_path = ARCHIVE_DIR / f"{slug}.json"
            with open(archive_json_path, "r", encoding="utf-8") as f:
                archive_data = json.load(f)

            a_html = render_page(archive_data, archive_slugs, current_year, current_month, is_archive=True)

            out_path = OUTPUT_ARCHIVE_DIR / f"{slug}.html"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(a_html)
            print(f"완료: {out_path} 생성됨")


if __name__ == "__main__":
    main()
