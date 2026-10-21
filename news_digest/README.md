# 상속·증여·부동산 세금 뉴스 브리핑

매일 아침 8시 45분(KST)에 네이버 뉴스에서 상속세·증여세·종부세·양도세·부동산 정책 기사를 모아
3~5건을 골라 GitHub 이슈로 올립니다. 이슈 본문의 메시지를 복사해 카카오톡 오픈채팅방에 붙여넣으면 됩니다.

## 설정 (처음 한 번)

1. **네이버 API 키 발급**
   - https://developers.naver.com/apps/#/register 에서 애플리케이션 등록
   - 사용 API: **검색**, 환경: **WEB 설정**(URL은 아무 주소, 예: `https://github.com`)
   - 발급된 Client ID, Client Secret 복사 (무료, 하루 25,000회)
2. **(선택) Anthropic API 키** — https://console.anthropic.com 에서 발급.
   있으면 Claude가 기사를 골라 한 줄 요약을 써 주고, 없으면 키워드 점수로 고르고 기사 요약문을 그대로 씁니다.
   하루 1회 호출이라 비용은 하루 몇십 원 수준입니다.
3. **GitHub 저장소에 Secret 등록** — Settings → Secrets and variables → Actions → New repository secret
   - `NAVER_CLIENT_ID`
   - `NAVER_CLIENT_SECRET`
   - `ANTHROPIC_API_KEY` (선택)
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
| 검색어 | `digest.py`의 `QUERIES` |
| 제외할 광고성 단어 | `digest.py`의 `EXCLUDE_WORDS` |
| 기사 수 | `digest.py`의 `MAX_ITEMS`, `MIN_ITEMS` |

로컬 실행: `NAVER_CLIENT_ID=... NAVER_CLIENT_SECRET=... python news_digest/digest.py`
