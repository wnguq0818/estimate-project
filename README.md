# estimate-project

`estimate.html` — 감정평가 견적서 작성기 (브라우저에서 열어 사용, Ctrl+P로 A4 인쇄)

- 평가수수료: 감정평가 보수기준 요율표 (하한 0.8 / 기준 1.0 / 상한 1.2), 천원 미만 절사
- 여비: 2024년 서울지회 여비 기준 — 교통비(왕복) + (현지교통비+일비+식비)×일수 + 숙박비×박수
- 공급가액 = 평가수수료 + 여비 + 실비 (백원 단위 절사), 부가세 10%

`make_estimate.mjs` — 하이테크 양식 견적서 PDF를 명령줄로 생성 (`output/`의 PDF와 같은 모양)

```
mkdir -p fonts && for w in Regular Bold; do curl -sSLo fonts/NanumGothic-$w.ttf https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic/NanumGothic-$w.ttf; done
node make_estimate.mjs estimates/신림동1431-20_18.1억.json output/견적서_신림동1431-20_18.1억.pdf
```

- 입력: `estimates/*.json` (소재지, 예상감정평가액, 물건별 구분·면적, 여비·실비, 요율)
- Playwright가 필요합니다. 브라우저 경로를 지정하려면 `CHROME_PATH` 환경 변수를 씁니다.
