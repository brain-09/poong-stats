# poong-stats

풍투데이(poong.today)에서 팀별 멤버들의 이번 달 별풍선 데이터를 12시간마다 자동으로
가져와서 표 페이지(`docs/index.html`)를 갱신하는 프로젝트입니다. 달이 바뀌면 그 이전
달 데이터는 자동으로 보관되어 `docs/archive/YYYY-MM.html`에서 볼 수 있습니다.

## 폴더 구조

```
poong-stats/
├── data/
│   ├── members.json      ← 팀-멤버 목록 (직접 관리하는 파일)
│   ├── latest.json        ← 이번 달 크롤링 결과 (자동 생성)
│   └── archive/
│       └── YYYY-MM.json   ← 지난 달들의 스냅샷 (자동 생성, 그 당시 팀 구성 그대로 보존)
├── scripts/
│   ├── fetch_data.py      ← poong.today API 호출 + 월 전환 시 자동 보관
│   └── generate_html.py   ← latest.json/archive → docs/index.html + docs/archive/*.html 생성
├── docs/
│   ├── index.html         ← 이번 달 표 (GitHub Pages가 이 폴더를 서빙)
│   └── archive/
│       └── YYYY-MM.html   ← 지난 달 표
└── .github/workflows/
    └── update.yml          ← 12시간마다 자동 실행 설정
```

## 과거 데이터는 어떻게 보존되나요

`members.json`은 팀/인원이 계속 바뀌는 파일이라, 단순히 "그때의 별풍선 숫자"만 저장하면
나중에 "그때는 누가 어느 팀이었는지"를 알 수 없게 됩니다. 그래서 `fetch_data.py`는
매번 실행될 때 이번 달 멤버 각각의 **팀/성별/직책/생일까지 통째로** `data/latest.json`에
같이 저장합니다.

달이 바뀌는 시점(예: 8월→9월로 넘어가는 첫 실행)에는, 새 데이터를 받기 직전에
그 전 `latest.json`(8월의 마지막 스냅샷)을 `data/archive/2026-08.json`으로 그대로
복사해둡니다. 그래서 나중에 팀 구성이 바뀌어도, 과거 페이지에는 항상 "그 당시의 팀 배정"
그대로 보여집니다. 참고로 자동 실행이 하루 2번(9시/21시)이라, 보관되는 시점은 월말
23:59 정각이 아니라 그 달의 마지막 실행 시점(최대 약 12시간 전) 기준입니다.

## 최초 설정 (한 번만 하면 됨)

### 1. 이 폴더 전체를 GitHub 저장소(poong-stats)에 업로드

로컬에 git이 있다면:
```bash
cd poong-stats
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin https://github.com/본인아이디/poong-stats.git
git push -u origin main
```

또는 GitHub 웹사이트에서 "Add file → Upload files"로 폴더 내용을 그대로 드래그해서 올려도 됩니다.
(`.github` 폴더는 숨김 폴더라 드래그 업로드 시 누락되기 쉬우니, GitHub 웹의
"Create new file"에서 `.github/workflows/update.yml` 경로로 직접 만드는 것도 방법입니다.)

### 2. GitHub Pages 활성화

1. 저장소 → **Settings** → **Pages**
2. **Source**를 `Deploy from a branch`로 설정
3. Branch: `main`, 폴더: `/docs` 선택 후 저장
4. 몇 분 후 `https://본인아이디.github.io/poong-stats/` 로 접속 가능

### 3. 워크플로우 쓰기 권한 확인

1. 저장소 → **Settings** → **Actions** → **General**
2. 맨 아래 **Workflow permissions**에서 **Read and write permissions** 선택 후 저장
   (이게 없으면 Actions가 자동으로 커밋/푸시를 못 합니다)

## 멤버 관리 (팀/인원이 바뀔 때)

`data/members.json`은 flat 구조입니다. 멤버 한 명이 배열의 항목 하나이고,
그 안에 `team` 필드로 소속을 표시합니다.

```json
{
  "members": [
    {
      "id": "poong.today의 SOOP ID",
      "nickname": "표시할 닉네임",
      "gender": "m 또는 f",
      "birthdate": "YYYY-MM-DD (모르면 null)",
      "role": "수장 / 전력외 (없으면 이 줄 자체를 생략 가능)",
      "team": "소속 팀 이름"
    }
  ]
}
```

- `id`는 `https://poong.today/broadcast/여기부분` 의 마지막 부분(SOOP ID)입니다.
- `role`이 `수장` 또는 `전력외`인 사람은 표에서 빨간 배경으로 표시되고, 팀 합계/평균/상위% 계산에서 제외됩니다.
- `birthdate`는 이름 옆 🎂 표시에 쓰입니다. 모르면 `null`.
- 수정 후 GitHub에 커밋/푸시하면 다음 자동 실행(또는 수동 실행) 때부터 반영됩니다.
- **이미 지나간 과거 달의 페이지(`docs/archive/*.html`)는 이 파일을 고쳐도 영향받지 않습니다** — 과거 데이터는 각 시점의 스냅샷(`data/archive/*.json`)에서만 읽어오기 때문입니다.

## 수동으로 즉시 갱신하고 싶을 때

저장소 → **Actions** 탭 → **Update poong stats** 워크플로우 선택 → **Run workflow** 버튼

## 와이고수 게시글에 넣는 법

와이고수 에디터가 `<iframe>` 태그를 그대로 두면:
```html
<iframe src="https://본인아이디.github.io/poong-stats/" width="100%" height="2000" frameborder="0"></iframe>
```

에디터가 iframe을 필터링해서 지워버리는 경우, `srcdoc` + meta refresh로 우회할 수 있습니다:
```html
<div style="max-width:1000px;margin:20px auto;">
  <iframe width="100%" height="1000" frameborder="0" scrolling="yes" srcdoc="&lt;meta http-equiv='refresh' content='0;url=https://본인아이디.github.io/poong-stats/'&gt;"></iframe>
</div>
```

높이는 팀 개수/레이아웃에 맞게 조절하세요.

## 로컬 테스트

```bash
python scripts/fetch_data.py
python scripts/generate_html.py
# docs/index.html, docs/archive/*.html 을 브라우저로 열어서 확인
```

## 참고

- 데이터 출처: poong.today (`static.poong.today/chart/get` 월간 전체 랭킹 API, 1회 호출로 전체 멤버 처리)
- 별풍선 값이 0이거나 직책이 수장/전력외인 멤버는 팀 합계·평균·상위 1%/5%/10% 계산에서 제외됩니다.
