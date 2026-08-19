# poong-stats

풍투데이(poong.today)에서 팀별 멤버들의 이번달 별풍선 데이터를 12시간마다 자동으로
가져와서 표 페이지(`docs/index.html`)를 갱신하는 프로젝트입니다.

## 폴더 구조

```
poong-stats/
├── data/
│   └── members.json     ← 팀-멤버 목록 (직접 관리하는 파일)
├── scripts/
│   ├── fetch_data.py     ← poong.today API 호출해서 data/latest.json 생성
│   └── generate_html.py  ← latest.json으로 docs/index.html 생성
├── docs/
│   └── index.html        ← 최종 결과 페이지 (GitHub Pages가 이 폴더를 서빙)
└── .github/workflows/
    └── update.yml         ← 12시간마다 자동 실행 설정
```

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

`data/members.json` 파일을 직접 수정하면 됩니다.

```json
{
  "teams": [
    {
      "name": "팀이름",
      "members": [
        {
          "id": "poong.today의 SOOP ID",
          "nickname": "표시할 닉네임",
          "gender": "m 또는 f",
          "birthdate": "YYYY-MM-DD (모르면 null)",
          "role": "수장 등 직책 (없으면 이 줄 자체를 생략 가능)"
        }
      ]
    }
  ]
}
```

- `id`는 `https://poong.today/broadcast/여기부분` 의 마지막 부분(SOOP ID)입니다.
- `birthdate`는 상단 페이지의 "이달의 생일" 섹션에 쓰입니다. 모르면 `null`로 두면 생일란에서 자동 제외됩니다.
- 수정 후 GitHub에 커밋/푸시하면, 다음 자동 실행(또는 수동 실행) 때부터 반영됩니다.
- 현재 14팀 243명이 이미 채워져 있습니다. 팀/인원 변동 시 이 파일에서 직접 추가·삭제·수정하세요.

## 수동으로 즉시 갱신하고 싶을 때

저장소 → **Actions** 탭 → **Update poong stats** 워크플로우 선택 → **Run workflow** 버튼

## 와이고수 게시글에 넣는 법

게시글 작성 시 (에디터가 HTML 삽입을 지원하는 경우) 아래처럼 iframe을 넣으면 됩니다.

```html
<iframe src="https://본인아이디.github.io/poong-stats/" width="100%" height="2000" frameborder="0"></iframe>
```

높이는 팀 개수/레이아웃에 맞게 조절하세요.

## 로컬 테스트

```bash
pip install --break-system-packages requests  # 없어도 동작하지만 있으면 편함
python scripts/fetch_data.py
python scripts/generate_html.py
# docs/index.html 을 브라우저로 열어서 확인
```

## 참고

- 데이터 출처: poong.today (`static.poong.today/bj/detail/get` API)
- 요청 간 0.5초 간격을 두어 대상 서버에 부담을 최소화하도록 설정되어 있습니다.
- 242명 기준 전체 수집에 약 2~3분 정도 소요될 수 있습니다.
