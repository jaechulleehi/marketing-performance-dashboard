# raw/ — 원천 데이터 드롭존

매일 전날 데이터를 **소스별 하위폴더**에 **`YYYY-MM-DD.csv`** 형식으로 추가한다.
파일을 넣고 대시보드를 새로고침하면 자동 반영된다 (스케줄러 불필요).

```
raw/
├── channel/      YYYY-MM-DD.csv   ← 매일 추가 (노출/클릭/비용 + 자가보고 전환)
├── appsflyer/    YYYY-MM-DD.csv   ← 매일 추가 (MMP 어트리뷰션 전환)
└── braze/        CRM 데이터 (별도 grain — 현재 조인 파이프라인 대상 아님)
    ├── users_YYYY-MM-DD.csv       (유저 스냅샷)
    ├── purchases_YYYY-QN.csv      (거래 단위)
    └── campaigns/                 (월별 푸시 발송 이벤트)
```

## 규칙
- 파일명 = 해당 일자 (예: `2025-04-01.csv`). 파일 안의 `일` 컬럼과 일치해야 함.
- 같은 날짜를 다시 넣으면 **마지막 파일이 우선**(dedup). 누적 아님.
- 스키마는 `docs/data-dictionary.md`, 네이밍은 `docs/naming-convention.md` 준수.
- 인코딩 UTF-8(BOM 허용).

## 새 채널이 생기면
`docs/naming-convention.md` §3 매핑표와 `data_pipeline.py`의
`MEDIA_SOURCE_TO_CHANNEL` 에 한 줄씩 추가한다.
