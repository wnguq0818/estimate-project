# 상속·증여·부동산 세금 뉴스 브리핑

매일 아침 8시 45분(KST)에 네이버 뉴스에서 기사를 모아 주제가 고루 섞이도록 5건을 골라 GitHub 이슈로 올립니다.

- 부동산 정책 2건: 공급 대책, 대출 규제, 규제지역 등
- 세금 정책 2건: 상속세·증여세·종부세·양도세·세법 개정 등
- 세무 칼럼 1건: 세무사 칼럼, 절세 정보 (최근 3일)

어떤 분류에 알맞은 기사가 없으면 다른 분류의 기사로 채웁니다. 이슈 본문의 메시지를 복사해 카카오톡 오픈채팅방에 붙여넣으면 됩니다.

네이버 키가 없거나 네이버 검색이 모두 실패하면 Google 뉴스 RSS로 대신합니다
(Google 링크는 길게 나옵니다). 둘 다 실패하면 빈 브리핑 대신 워크플로가 실패로 끝나고
GitHub가 실패 알림을 보냅니다.

## 설정 (처음 한 번)

1. **네이버 API 키 발급 (NAVER API HUB)** — 없으면 Google 뉴스로 동작합니다.
   - 네이버 개발자센터(developers.naver.com)의 검색 API는 2026-07-31부터 신규 발급이 끝나서,
     새 키는 네이버 클라우드 플랫폼의 **NAVER API HUB**에서 받아야 합니다.
     (개발자센터 "사용 API" 목록에 "검색"이 없는 이유입니다.)
   - https://console.ncloud.com 로그인(네이버 아이디 가능) → Services → Application Service → **NAVER API HUB** → 이용 신청
   - Application 등록 → API 목록에서 **뉴스** 체크 → 저장
   - 발급된 Client ID, Client Secret 복사 (요금·무료 한도는 콘솔 안내를 확인하세요)
   - 개발자센터에서 받은 예전 키는 이 방식에 쓸 수 없습니다.
2. **(선택) Anthropic API 키** — https://console.anthropic.com 에서 발급.
   있으면 Claude가 기사를 골라 한 줄 요약을 써 주고, 없으면 키워드 점수로 고릅니다.
   Google 뉴스는 기사 요약문을 주지 않아서, 키가 없으면 "제목 + 언론사 + 링크"만 나옵니다.
   하루 1회 호출이라 비용은 하루 몇십 원 수준입니다.
3. **GitHub 저장소에 Secret 등록** — Settings → Secrets and variables → Actions → New repository secret
   - `ANTHROPIC_API_KEY` (선택)
   - `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`
4. **main 브랜치에 병합** — GitHub의 예약 실행(schedule)은 기본 브랜치(main)에 있는 워크플로만 동작합니다.
5. **테스트** — Actions 탭 → "부동산 세금 뉴스 브리핑" → Run workflow. 몇 분 뒤 Issues 탭에 브리핑이 올라옵니다.

## 매일 받는 방법

- 브리핑 이슈는 저장소 주인에게 할당되므로 GitHub 앱/메일로 알림이 옵니다.
- GitHub 모바일 앱에서 이슈를 열고 메시지를 길게 눌러 복사 → 오픈채팅방에 붙여넣기.
- 지난 브리핑 이슈는 새 브리핑이 올라올 때 자동으로 닫힙니다.

## 바꾸고 싶을 때

| 바꿀 것 | 위치 |
|---|---|
| 실행 시각 | `.github/workflows/news-digest.yml`의 `cron` (UTC 기준, KST −9시간) |
| 분류·검색어·분류별 기사 수 | `digest.py`의 `CATEGORIES` |
| 제외할 광고성 단어 | `digest.py`의 `EXCLUDE_WORDS` |

로컬 실행: `python news_digest/digest.py` (네이버를 쓰려면 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` 지정)
