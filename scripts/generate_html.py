"""
data/latest.json 을 읽어서 docs/index.html 로 렌더링하는 스크립트.

팀별 표 구성: 표 1개, 열은 [남자 멤버 | 별풍선 | 여자 멤버 | 별풍선] 4열로 나란히 배치.
남/여 각각 별풍선 내림차순 정렬. 하단에는 합계/평균/인원 행 포함.

기타 반영 사항:
- 상위 1% 파랑 / 5% 초록 / 10% 노랑 하이라이트
- Noto Sans KR 폰트, 별풍선 값 가운데 정렬
- 생일 표시는 이름 칸 오른쪽 끝에 작게
- 여자 평균 행 청록 하이라이트
- 수장/전력외는 집계 제외 + 빨간 배경

실행: python scripts/generate_html.py
"""

import json
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "latest.json"
OUTPUT_PATH = ROOT / "docs" / "index.html"

EXCLUDED_ROLES = {"수장", "전력외"}


def fmt(n: int) -> str:
    return f"{n:,}"


def kst_today():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date()


def parse_birthdate(bd):
    if not bd:
        return None
    try:
        parts = bd.split("-")
        return int(parts[1]), int(parts[2])
    except (IndexError, ValueError):
        return None


def compute_percentile_tiers(members: list):
    ranked = sorted(members, key=lambda m: -m["balloons"])
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


def build_today_birthday_section(members: list, today):
    todays = [m for m in members if parse_birthdate(m.get("birthdate")) == (today.month, today.day)]
    if not todays:
        return ""
    items = "".join(
        f"<span class='bday-item'>🎉 <b>{m['nickname']}</b> <small>({m['team']})</small></span>"
        for m in todays
    )
    return f"""
    <div class="birthday-box">
      <div class="birthday-title">🎂 오늘 생일</div>
      <div class="birthday-list">{items}</div>
    </div>
    """


def name_cell(m, current_month):
    role = m.get("role")
    role_html = f"<span class='role'>{role}</span>" if role else ""
    bday = parse_birthdate(m.get("birthdate"))
    bday_html = "<span class='bday-mark'>🎂</span>" if bday and bday[0] == current_month else ""
    return (
        f"<div class='name-cell'>"
        f"<span class='name-left'>{m['nickname']} {role_html}</span>"
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


def build_team_card(team_name: str, members: list, current_month: int, tiers: dict):
    counted = [m for m in members if m.get("role") not in EXCLUDED_ROLES]
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
            m_val = f"<td class='num {value_class(m, tiers)}'>{fmt(m['balloons'])}</td>"
        else:
            m_name = "<td class='name-td empty'>-</td>"
            m_val = "<td class='num empty'>-</td>"

        if i < len(females_all):
            f_ = females_all[i]
            f_name = f"<td class='name-td'>{name_cell(f_, current_month)}</td>"
            f_val = f"<td class='num {value_class(f_, tiers)}'>{fmt(f_['balloons'])}</td>"
        else:
            f_name = "<td class='name-td empty'>-</td>"
            f_val = "<td class='num empty'>-</td>"

        body_rows.append(f"<tr>{m_name}{m_val}{f_name}{f_val}</tr>")

    body_html = "".join(body_rows)

    summary_html = f"""
      <tr class="summary-row"><td colspan="2">남자 합계 {fmt(male_sum)}</td><td colspan="2">여자 합계 {fmt(female_sum)}</td></tr>
      <tr class="summary-row"><td colspan="2">남자 평균 {fmt(male_avg)}</td><td colspan="2" class="female-avg">여자 평균 {fmt(female_avg)}</td></tr>
      <tr class="summary-row total"><td colspan="2">전체 합계 {fmt(total_sum)}</td><td colspan="2">전체 평균 {fmt(total_avg)}</td></tr>
      <tr class="summary-row"><td colspan="4">인원 총 {len(members)}명 (집계 {len(counted)}명 · 남 {len(males_all)} / 여 {len(females_all)})</td></tr>
    """

    return total_avg, f"""
    <div class="team-card">
      <div class="team-title">{team_name} <span class="team-avg">전체평균 {fmt(total_avg)}</span></div>
      <table>
        <thead><tr><th>남자 멤버</th><th>별풍선</th><th>여자 멤버</th><th>별풍선</th></tr></thead>
        <tbody>
          {body_html}
          {summary_html}
        </tbody>
      </table>
    </div>
    """


def main():
    if not DATA_PATH.exists():
        raise SystemExit(f"[오류] {DATA_PATH} 가 없습니다. 먼저 fetch_data.py를 실행하세요.")

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    members = data["members"]
    today = kst_today()

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

    birthday_html = build_today_birthday_section(members, today)

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
  .header {{
    display: flex;
    justify-content: center;
    gap: 24px;
    max-width: 1240px;
    margin: 0 auto 16px;
    font-size: 13px;
    color: #888;
    text-align: center;
  }}
  .birthday-box {{
    max-width: 1240px;
    margin: 0 auto 20px;
    background: linear-gradient(135deg, #fff4d6, #ffe9ec);
    border: 1px solid #f2cf8a;
    border-radius: 10px;
    padding: 12px 18px;
    text-align: center;
  }}
  .birthday-title {{
    font-weight: 700;
    margin-bottom: 6px;
    font-size: 15px;
  }}
  .birthday-list {{
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 6px 18px;
    font-size: 13px;
  }}
  .bday-item small {{ color: #999; }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
    gap: 18px;
    max-width: 1240px;
    margin: 0 auto;
  }}
  .team-card {{
    background: #fff;
    border: 1px solid #e5e6ea;
    border-radius: 12px;
    padding: 14px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  .team-title {{
    font-weight: 700;
    text-align: center;
    background: #2f3542;
    color: #fff;
    padding: 10px;
    margin: -14px -14px 10px -14px;
    border-radius: 12px 12px 0 0;
    font-size: 16px;
    letter-spacing: 0.3px;
  }}
  .team-avg {{
    font-weight: 400;
    font-size: 12px;
    color: #cfd3e0;
    margin-left: 6px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12.5px;
    table-layout: fixed;
  }}
  th, td {{
    border: 1px solid #eceef1;
    padding: 5px 6px;
    text-align: center;
  }}
  th {{
    background: #f7f8fa;
    font-weight: 700;
    color: #555;
  }}
  td.name-td {{ text-align: left; }}
  .name-cell {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 4px;
  }}
  .name-left {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .bday-mark {{ font-size: 11px; flex-shrink: 0; }}

  td.num {{
    text-align: center;
    font-variant-numeric: tabular-nums;
    font-weight: 500;
  }}
  td.empty {{ color: #ccc; }}

  .role {{
    font-size: 10px;
    color: #d34c4c;
    border: 1px solid #f0a8a8;
    border-radius: 3px;
    padding: 0 3px;
    margin-left: 2px;
  }}

  td.excluded {{
    background: #fdeaea !important;
    color: #c0392b;
    font-weight: 700;
  }}
  td.tier1 {{ background: #90caf9; }}
  td.tier5 {{ background: #a5d6a7; }}
  td.tier10 {{ background: #fff59d; }}
  td.excluded.tier1, td.excluded.tier5, td.excluded.tier10 {{
    background: #fdeaea !important;
  }}

  tr.summary-row td {{ font-size: 12px; background: #fafbfc; font-weight: 600; text-align: center; }}
  tr.summary-row.total td {{ font-weight: 700; background: #e3e7fb; }}
  tr.summary-row td.female-avg {{ background: #b2ebe4; }}

  .legend {{
    max-width: 1240px;
    margin: 14px auto 0;
    font-size: 11.5px;
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
</style>
</head>
<body>
  <div class="header">
    <span>업데이트: {data['updated_at']} (KST)</span>
    <span>{data['year']}년 {data['month']}월 기준</span>
  </div>
  {birthday_html}
  <div class="grid">
    {cards_html}
  </div>
  <div class="legend">
    <span><span class="sw" style="background:#90caf9;"></span>상위 1%</span>
    <span><span class="sw" style="background:#a5d6a7;"></span>상위 5%</span>
    <span><span class="sw" style="background:#fff59d;"></span>상위 10%</span>
    <span><span class="sw" style="background:#fdeaea;"></span>수장/전력외 (집계 제외)</span>
    <span><span class="sw" style="background:#b2ebe4;"></span>여자 평균</span>
    <span>🎂 이번 달 생일</span>
  </div>
</body>
</html>
"""

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"완료: {OUTPUT_PATH} 생성됨")


if __name__ == "__main__":
    main()
