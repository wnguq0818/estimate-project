# 감정평가사사무소 경율 — 감정평가서 생성기

데이터(JSON)를 채우고 실행하면 경율 양식의 감정평가서(HTML + A4 PDF)가 만들어집니다.

```bash
python3 build.py data/sample_commercial.json   # 집합상가(구분건물) 예시
python3 build.py data/sample_apartment.json    # 아파트(구분건물) 예시
# 결과: output/<감정서번호>.pdf
```
필요한 것: Python 3 + `jinja2`, Node + `playwright`(Chromium), 한글 글꼴(나눔스퀘어/나눔고딕).

## 구성
표지 → 감정평가표 → 감정평가명세표 → 산출근거 및 결정의견(Ⅰ 개요 · Ⅱ 대상 개황 · Ⅲ 감정평가방법의 적용 · Ⅳ 결정의견) → 감정평가요항표 → 광역/상세 위치도 → 사진첨부용지

## 자동 계산 항목
| 항목 | 계산 |
|---|---|
| 시점수정치 | `time.method`가 `"index"`면 기준시점 지수 ÷ 거래시점 지수(아파트 매매가격지수), 아니면 분기별 자본수익률을 일수 안분해 누적(상가) |
| 가치형성요인 비교치 | 격차율 곱 (소수 셋째 자리) |
| 비준단가 | 사례단가 × 사정보정 × 시점수정 × 지역요인(있을 때) × 개별요인 → `unit_round` 단위 반올림 |
| 시산가액 | 비준단가 × 전유면적 → `value_round` 미만 절사 |
| 수익가액 | PGI − 공실손실 → EGI − 영업경비 → NOI ÷ 환원율 (`income`이 `null`이면 수익환원법 생략, 생략 사유 문구 자동 삽입) |
| 감정평가액 한글 | 150,000,000 → 일억오천만원정 |

## 새 감정서를 만들 때
1. `data/` 의 예시 중 비슷한 유형을 복사해 새 JSON을 만듭니다.
2. `report.received_date`(접수일, `YYYY-MM-DD`)와 `report.seq`(그날 접수 순번)를 넣으면 감정서번호가 `GY접수연도-접수월일-순번` 형식으로 자동으로 붙습니다. 예) 2025-09-18 첫 번째 접수 → `GY2025-0918-001`. 결과 파일 이름도 이 번호로 저장됩니다.
3. `office`의 감정평가사 이름·전화·팩스·주소를 실제 값으로 바꾸고, 서명·인장 이미지가 있으면 `signature_image`, `seal_image`에 경로를 넣습니다 (없으면 날인란이 비어 있음).
4. 위치도는 `maps.wide`, `maps.detail`, 사진은 `photos[].file`에 이미지 경로를 넣습니다 (`images/` 폴더 권장). `photos_per_page`는 2(세로 2장) 또는 4(2×2).
5. 아파트 형식 전용 항목: `units[].dong`, `units[].shared_area`(주거공용면적), `complex.facilities`(설비표), `sales_comparison.region_factor`(지역요인), `sales_comparison.factor_items`(개별요인 비교항목표).
