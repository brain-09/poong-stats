"""
data/latest.json 을 읽어서 docs/index.html 로 렌더링하는 스크립트.
상단에 "이달의 생일" 섹션을 추가하고, 팀별 별풍선 표를 렌더링한다.

실행: python scripts/generate_html.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "latest.json"
OUTPUT_PATH = ROOT / "docs" / "index.html"


def fmt(n: int) -> str:
    return f"{n:,}"


def build_birthday_section(all_members: list, month: int) -> str:
    born_this_month = []
    for m in all_members:
        bd = m.get("birthdate")
        if not bd:
            continue
        try:
            bd_month = int(bd.split("-")[1])
            bd_day = int(bd.split("-")[2])
        except (IndexError, ValueError):
            continue
        if bd_month == month:
            born_this_month.append((bd_day, m["nickname"], m.get("team", "")))

    if not born_this_month:
        return ""

    born_this_month.sort(key=lambda x: x[0])
    items = "".join(
        f"<span class='bday-item'><b>{day}일</b> {nick} <small>({team})</small></span>"
        for day, nick, team in born_this_month
    )
    return f"""
    <div class="birthday-box">
      <div class="birthday-title">🎂 이달의 생일</div>
      <div class="birthday-list">{items}</div>
    </div>
    """


def build_team_card(team: dict) -> str:
    members = team["members"]
    males = sorted([m for m in members if m["gender"] == "m"], key=lambda x: -x["balloons"])
    females = sorted([m for m in members if m["gender"] == "f"], key=lambda x: -x["balloons"])

    male_sum = sum(m["balloons"] for m in males)
    female_sum = sum(m["balloons"] for m in females)
    total_sum = male_sum + female_sum
    male_avg = round(male_sum / len(males)) if males else 0
    female_avg = round(female_sum / len(females)) if females else 0
    total_avg = round(total_sum / len(members)) if members else 0

    def label(m):
        role = m.get("role")
        return f"{m['nickname']} <span class='role'>{role}</span>" if role else m["nickname"]

    def rows(lst):
        if not lst:
            return "<tr><td colspan='2' class='empty'>-</td></tr>"
        return "".join(
            f"<tr><td>{label(m)}</td><td class='num'>{fmt(m['balloons'])}</td></tr>"
            for m in lst
        )

    return f"""
    <div class="team-card">
      <div class="team-title">{team['name']}</div>
      <div class="table-pair">
        <table>
          <thead><tr><th>남 멤버</th><th>별풍선</th></tr></thead>
          <tbody>{rows(males)}</tbody>
        </table>
        <table>
          <thead><tr><th>여 멤버</th><th>별풍선</th></tr></thead>
          <tbody>{rows(females)}</tbody>
        </table>
      </div>
      <table class="summary">
        <tr><td>남자 합계</td><td class="num">{fmt(male_sum)}</td><td>여자 합계</td><td class="num">{fmt(female_sum)}</td></tr>
        <tr><td>남자 평균</td><td class="num">{fmt(male_avg)}</td><td>여자 평균</td><td class="num">{fmt(female_avg)}</td></tr>
        <tr><td>전체 합계</td><td class="num total">{fmt(total_sum)}</td><td>전체 평균</td><td class="num total">{fmt(total_avg)}</td></tr>
        <tr><td>인원</td><td colspan="3">총 {len(members)}명 (남 {len(males)}명 / 여 {len(females)}명)</td></tr>
      </table>
    </div>
    """


def main():
    if not DATA_PATH.exists():
        raise SystemExit(f"[오류] {DATA_PATH} 가 없습니다. 먼저 fetch_data.py를 실행하세요.")

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    teams_sorted = sorted(
        data["teams"],
        key=lambda t: -sum(m["balloons"] for m in t["members"]),
    )

    all_members = []
    for t in data["teams"]:
        for m in t["members"]:
            m2 = dict(m)
            m2["team"] = t["name"]
            all_members.append(m2)

    birthday_html = build_birthday_section(all_members, data["month"])
    cards_html = "".join(build_team_card(t) for t in teams_sorted)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>팀별 별풍선 랭킹</title>
<style>
  body {{
    font-family: -apple-system, "Malgun Gothic", sans-serif;
    background: #f5f5f7;
    margin: 0;
    padding: 20px;
    color: #222;
  }}
  .header {{
    display: flex;
    justify-content: space-between;
    max-width: 1200px;
    margin: 0 auto 16px;
    font-size: 13px;
    color: #666;
  }}
  .birthday-box {{
    max-width: 1200px;
    margin: 0 auto 16px;
    background: #fff8e6;
    border: 1px solid #f0dca0;
    border-radius: 6px;
    padding: 10px 14px;
  }}
  .birthday-title {{
    font-weight: bold;
    margin-bottom: 6px;
    font-size: 14px;
  }}
  .birthday-list {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px 16px;
    font-size: 13px;
  }}
  .bday-item small {{
    color: #888;
  }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
    gap: 16px;
    max-width: 1200px;
    margin: 0 auto;
  }}
  .team-card {{
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 6px;
    padding: 12px;
  }}
  .team-title {{
    font-weight: bold;
    text-align: center;
    background: #eee;
    padding: 8px;
    margin: -12px -12px 8px -12px;
    border-radius: 6px 6px 0 0;
    font-size: 15px;
  }}
  .table-pair {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }}
  th, td {{
    border: 1px solid #e5e5e5;
    padding: 4px 6px;
    text-align: left;
  }}
  th {{
    background: #fafafa;
  }}
  td.num {{
    text-align: right;
    font-variant-numeric: tabular-nums;
  }}
  td.empty {{
    text-align: center;
    color: #aaa;
  }}
  .role {{
    font-size: 10px;
    color: #b8860b;
    border: 1px solid #e0c060;
    border-radius: 3px;
    padding: 0 3px;
    margin-left: 3px;
  }}
  table.summary {{
    margin-top: 8px;
  }}
  table.summary td {{
    font-size: 12px;
  }}
  table.summary td.total {{
    font-weight: bold;
    background: #f0f4ff;
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
</body>
</html>
"""

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"완료: {OUTPUT_PATH} 생성됨")


if __name__ == "__main__":
    main()
