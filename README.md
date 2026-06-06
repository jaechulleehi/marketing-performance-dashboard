# 마케팅 성과 EDA 대시보드

채널 데이터 + 앱스플라이어 데이터를 자동으로 병합·전처리하고 시각화하는 Streamlit 대시보드.

## 실행

```bash
python3 -m streamlit run streamlit_app.py
```

브라우저에서 http://localhost:8501 자동 오픈.

## 매일 데이터 추가하기

`raw/` 의 소스별 하위폴더에 `YYYY-MM-DD.csv` 만 떨어뜨리면 됩니다 (스케줄러 불필요):

- 채널: `raw/channel/2025-04-01.csv`
- 앱스플라이어: `raw/appsflyer/2025-04-01.csv`

대시보드를 새로고침하면 `raw/` 의 모든 날짜 데이터를 자동으로 다시 읽어 반영합니다.
(파일 수정시각이 바뀌면 캐시가 자동 무효화됨). 자세한 규칙은 [raw/README.md](raw/README.md).

## 폴더 구조

```
raw/{channel,appsflyer,braze}/   원천 데이터 드롭존
processed/                       전처리 산출물 캐시
insights/                        일자별 인사이트 리포트
archive/                         원본 zip·구버전 보관
docs/                            정의 문서 (data-dictionary 등)
data_pipeline.py                 raw 스캔→매핑→조인→파생지표
streamlit_app.py                 대시보드 UI
```

## 조인 규칙

- 키: 일 · 채널 · 캠페인 · 그룹 · 소재
- 채널 표기 매핑 (`data_pipeline.py`의 `MEDIA_SOURCE_TO_CHANNEL`):
  - `googleadwords_int` → 구글
  - `Facebook Ads` → 메타
  - `naver_search` → 네이버
  - 새 채널은 이 딕셔너리에 한 줄만 추가
- 노출/클릭/비용 및 파생지표(CTR·CPC·CPA·CVR·ROAS)는 **채널 데이터 기준**
- 전환(구매/매출)은 채널 vs 앱스플라이어 비교용으로 `_앱스플라이어` 접미사 컬럼 병행
