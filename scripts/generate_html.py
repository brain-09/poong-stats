"""
data/latest.json 을 읽어서 docs/index.html 로 렌더링하는 스크립트.

이번 수정 사항:
1. 이름 텍스트 볼드 처리
2. 빈 칸(인원수 안 맞는 경우) '-' 대신 완전히 빈 칸으로
3. '인원' 라벨 칸도 옅은 회색 배경
4. 팀 이름 옆 '전체평균 000' 표시 제거
5. 표 전체 너비를 좁게 (패딩/폰트 축소)

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
      <div class="team-title">{team_name}</div>
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
  .header {{
    display: flex;
    justify-content: center;
    gap: 24px;
    max-width: 1080px;
    margin: 0 auto 16px;
    font-size: 13px;
    color: #888;
    text-align: center;
  }}
  .birthday-box {{
    max-width: 1080px;
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
  .team-title {{
    font-weight: 700;
    text-align: center;
    background: #25528F;
    color: #fff;
    padding: 8px;
    margin: -10px -10px 8px -10px;
    border-radius: 10px 10px 0 0;
    font-size: 15px;
    letter-spacing: 0.3px;
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
    .team-title {{
      font-size: 11px;
      padding: 5px;
      margin: -5px -5px 5px -5px;
      border-radius: 7px 7px 0 0;
    }}
    table {{ font-size: 8px; }}
    th, td {{ padding: 2px 1px; }}
    tr.summary-row td {{ font-size: 8px; padding: 2px 1px; }}
    .name-left {{ font-size: 8px; }}
    .bday-mark {{ font-size: 8px; }}
    .header {{ font-size: 10px; gap: 8px; flex-wrap: wrap; }}
    .legend {{ font-size: 9px; }}
  }}
</style>
</head>
<body>
  <div class="header">
    <span>업데이트: {data['updated_at']} (KST)</span>
    <span>{data['year']}년 {data['month']}월 기준</span>
    <span>총 {team_count}개 팀 · 총 {member_count}명</span>
    <span>출처: 풍투데이(poong.today)</span>
  </div>
  <div class="grid">
    {cards_html}
  </div>
  <div class="legend">
    <span><span class="sw" style="background:#d6e9fb;"></span>상위 1%</span>
    <span><span class="sw" style="background:#dcefdd;"></span>상위 5%</span>
    <span><span class="sw" style="background:#fbf3cf;"></span>상위 10%</span>
    <span><span class="sw" style="background:#fadada;"></span>수장/전력외</span>
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
