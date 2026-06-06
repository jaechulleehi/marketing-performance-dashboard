# 퍼포먼스 마케팅 데이터 분석 — 프로젝트 규칙

매일 **채널 데이터**와 **앱스플라이어(AppsFlyer) 데이터**를 업로드해 조인·전처리하고
인사이트를 뽑는 작업을 한다. 아래 규칙과 `docs/`의 정의 문서를 **항상 따른다**.

## 폴더 구조

```
raw/                  원천 데이터 드롭존 (소스별 하위폴더, YYYY-MM-DD.csv)
  channel/            매일 추가 — 노출/클릭/비용 + 자가보고 전환
  appsflyer/          매일 추가 — MMP 어트리뷰션 전환
  braze/              CRM (별도 grain, 현재 조인 대상 아님 / 폴더만 예약)
processed/            전처리·조인 산출물 캐시
insights/             일자별 인사이트 리포트 (YYYY-MM-DD.md)
archive/              원본 zip·구버전 파일 보관
docs/                 정의 문서 (아래 표)
data_pipeline.py      raw 스캔→매핑→조인→파생지표
streamlit_app.py      대시보드
```

## 매일 워크플로우

1. `raw/channel/`, `raw/appsflyer/` 에 `YYYY-MM-DD.csv` 추가
2. `python3 -m streamlit run streamlit_app.py` 로 대시보드 확인 (새로고침 시 자동 반영)
3. 분석/인사이트는 `docs/metrics-definitions.md`의 산식과 임계값을 그대로 사용
4. 결과는 `insights/YYYY-MM-DD.md` 형식으로 저장 (요약 3줄 + 표 + 액션 항목)

## 핵심 정의 문서 (수정 시 반드시 동기화)

| 문서 | 내용 |
|---|---|
| [data-dictionary.md](docs/data-dictionary.md) | 모든 컬럼의 의미·타입·단위·출처 |
| [naming-convention.md](docs/naming-convention.md) | 소재/캠페인 네이밍 규칙 + 파생 컬럼 |
| [metrics-definitions.md](docs/metrics-definitions.md) | 지표 산식 + Source of Truth + 판단 임계값 |
| [join-rules.md](docs/join-rules.md) | 조인 키·채널 매핑·미스매치/중복 처리 |
| [glossary.md](docs/glossary.md) | 도메인 용어집 |

## 절대 하지 말 것 (데이터 사고 방지)

- ❌ **출처 혼용 금지**: 같은 지표(구매·매출)를 channel과 appsflyer에서 동시에 더하지 않는다.
  지표별 권위 출처는 [metrics-definitions.md](docs/metrics-definitions.md)를 따른다.
- ❌ **산식 즉흥 생성 금지**: CTR/CPC/CPA/CVR/ROAS는 문서 정의만 사용.
- ❌ **네이밍 추측 금지**: 소재/캠페인 파싱은 [naming-convention.md](docs/naming-convention.md) 규칙만 사용.
  매칭 안 되는 신규 패턴은 추측하지 말고 사용자에게 확인.
- ❌ **통화/단위 가정 금지**: 모든 금액은 원(KRW) 정수. 환산하지 않는다.
- ❌ **조용한 누락 금지**: 조인 미스매치·중복·결측은 무시하지 말고 리포트에 명시한다.

## 작업 원칙

- 전처리 로직은 `data_pipeline.py`에 집중. 정의가 바뀌면 문서 → 코드 순으로 반영.
- 새 채널/소재타입/캠페인목적이 등장하면 먼저 해당 docs를 업데이트한 뒤 코드 수정.
- 분석 결론은 반드시 데이터로 증명 (행 수·합계·기간 명시).

## 🔧 확정 필요 결정 (현재 기본값으로 운영 중)

1. **전환·매출 권위 출처** → 기본값: AppsFlyer (MMP 어트리뷰션). 상세는 metrics-definitions.md
2. **재업로드 정책** → 기본값: 같은 날짜+조인키 중복 시 마지막 파일 우선(dedup). 상세는 join-rules.md
