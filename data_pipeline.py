"""데이터 파이프라인: raw/<소스>/<날짜>.csv 를 자동 스캔·병합·조인한다.

폴더 구조 (docs/join-rules.md 참조):
    raw/
      channel/   YYYY-MM-DD.csv   (일별, 노출/클릭/비용 + 자가보고 전환)
      appsflyer/ YYYY-MM-DD.csv   (일별, MMP 어트리뷰션 전환)
      braze/     ...              (CRM, 별도 grain — 현재 조인 대상 아님)

매일 전날 데이터를 raw/channel, raw/appsflyer 에 날짜.csv로 떨어뜨리면
glob이 전부 읽어 합치므로 대시보드 새로고침 시 자동 반영된다. 스케줄러 불필요.
"""

from __future__ import annotations

import glob
import os

import pandas as pd

# 앱스플라이어의 미디어소스 표기 -> 채널 데이터의 채널 표기 매핑.
# 새 채널이 생기면 여기에 한 줄만 추가하면 된다.
MEDIA_SOURCE_TO_CHANNEL = {
    "googleadwords_int": "구글",
    "Facebook Ads": "메타",
    "naver_search": "네이버",
}

# 날짜·채널·캠페인·그룹·소재 5개 키로 조인한다.
JOIN_KEYS = ["일", "채널", "캠페인", "그룹", "소재"]

# 원천 데이터 루트(프로젝트 루트 기준 상대 경로).
RAW_DIRNAME = "raw"


def _source_dir(root: str, source: str) -> str:
    return os.path.join(root, RAW_DIRNAME, source)


def source_coverage(root: str) -> dict:
    """일별 소스(channel/appsflyer)의 적재 현황과 누락 일자를 점검한다.

    반환: {소스: {"files": n, "first": date, "last": date, "missing": [날짜...]}}
    누락 = first~last 사이 연속 일자 중 파일이 없는 날.
    """
    out: dict = {}
    for source in ("channel", "appsflyer"):
        paths = sorted(glob.glob(os.path.join(_source_dir(root, source), "*.csv")))
        dates = sorted(
            os.path.splitext(os.path.basename(p))[0]
            for p in paths
            if not os.path.basename(p).startswith("README")
        )
        dts = pd.to_datetime(pd.Series(dates), errors="coerce").dropna()
        if dts.empty:
            out[source] = {"files": 0, "first": None, "last": None, "missing": []}
            continue
        full = pd.date_range(dts.min(), dts.max(), freq="D")
        missing = [d.strftime("%Y-%m-%d") for d in full.difference(dts)]
        out[source] = {
            "files": len(dates),
            "first": dts.min().strftime("%Y-%m-%d"),
            "last": dts.max().strftime("%Y-%m-%d"),
            "missing": missing,
        }
    return out


def _read_source(root: str, source: str) -> pd.DataFrame:
    """raw/<source>/*.csv 전부 읽어 하나로 합친다. BOM(utf-8-sig) 처리."""
    paths = sorted(glob.glob(os.path.join(_source_dir(root, source), "*.csv")))
    if not paths:
        return pd.DataFrame()
    frames = [pd.read_csv(p, encoding="utf-8-sig") for p in paths]
    return pd.concat(frames, ignore_index=True)


def _dedup(df: pd.DataFrame, keys: list[str], label: str) -> pd.DataFrame:
    """같은 키 중복 시 마지막(최신 로드) 행 우선. 제거 건수는 호출부에서 검증."""
    before = len(df)
    out = df.drop_duplicates(subset=keys, keep="last").reset_index(drop=True)
    removed = before - len(out)
    if removed:
        out.attrs.setdefault("warnings", []).append(
            f"{label}: 중복 {removed}행 제거(같은 {keys} 기준, 최신 우선)"
        )
    return out


def load_channel(root: str) -> pd.DataFrame:
    """raw/channel/*.csv 로드 + dedup."""
    df = _read_source(root, "channel")
    if df.empty:
        return df
    df["일"] = pd.to_datetime(df["일"])
    return _dedup(df, JOIN_KEYS, "channel")


def load_appsflyer(root: str) -> pd.DataFrame:
    """raw/appsflyer/*.csv 로드 + 미디어소스→채널 매핑 + dedup."""
    df = _read_source(root, "appsflyer")
    if df.empty:
        return df
    df["일"] = pd.to_datetime(df["일"])
    df["채널"] = df["미디어소스"].map(MEDIA_SOURCE_TO_CHANNEL).fillna(df["미디어소스"])
    return _dedup(df, JOIN_KEYS, "appsflyer")


def _add_derived_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """노출/클릭/비용/전환 기반 파생지표를 안전하게(0 나눗셈 방지) 계산."""
    out = df.copy()

    def safe_div(num, den):
        return (num / den.replace(0, pd.NA)).astype("Float64")

    out["CTR"] = safe_div(out["클릭"], out["노출"])          # 클릭률
    out["CPC"] = safe_div(out["비용"], out["클릭"])          # 클릭당 비용
    out["CPA"] = safe_div(out["비용"], out["구매"])          # 구매당 비용(획득비용)
    out["CVR"] = safe_div(out["구매"], out["클릭"])          # 클릭→구매 전환율
    out["ROAS"] = safe_div(out["구매매출"], out["비용"])     # 광고비 대비 매출
    out["가입당비용"] = safe_div(out["비용"], out["회원가입"])
    return out


def _add_naming_derivatives(df: pd.DataFrame) -> pd.DataFrame:
    """소재명을 분해해 소재타입/카테고리/시즌/AB변형/버전 파생 컬럼 추가.

    규칙: docs/naming-convention.md (뒤에서부터 파싱, AB 토큰은 선택적).
    """
    out = df.copy()

    def parse(s: str):
        parts = str(s).split("_")
        if len(parts) < 3:
            return ("미분류", str(s), "", "단일", False, "")
        type_ = parts[0]
        version = parts[-1]
        if parts[-2] in ("A", "B"):
            ab, ab_flag = parts[-2], True
            season = parts[-3]
            category = "_".join(parts[1:-3])
        else:
            ab, ab_flag = "단일", False
            season = parts[-2]
            category = "_".join(parts[1:-2])
        return (type_, category, season, ab, ab_flag, version)

    parsed = out["소재"].map(parse)
    out["소재타입"] = parsed.map(lambda x: x[0])
    out["카테고리"] = parsed.map(lambda x: x[1])
    out["시즌"] = parsed.map(lambda x: x[2])
    out["AB변형"] = parsed.map(lambda x: x[3])
    out["AB여부"] = parsed.map(lambda x: x[4])
    out["버전"] = parsed.map(lambda x: x[5])
    return out


def build_dataset(root: str) -> pd.DataFrame:
    """채널(기준) + 앱스플라이어(비교) 조인 + 파생지표/네이밍 파생 컬럼 생성.

    - 노출/클릭/비용 및 파생지표: channel 기준
    - 전환 지표(회원가입/구매/구매매출): channel 원본 유지 + appsflyer 는 _앱스플라이어 접미사
    """
    ch = load_channel(root)
    af = load_appsflyer(root)

    if ch.empty:
        raise FileNotFoundError(
            f"{_source_dir(root, 'channel')} 에서 *.csv 를 찾지 못했습니다."
        )

    base = _add_derived_metrics(ch)
    base = _add_naming_derivatives(base)
    warnings = list(ch.attrs.get("warnings", []))

    if af.empty:
        merged = base.copy()
        for col in ["클릭", "회원가입", "구매", "구매매출"]:
            merged[f"{col}_앱스플라이어"] = pd.NA
        warnings.append("appsflyer 데이터 없음 — 어트리뷰션 비교 불가")
        merged.attrs["warnings"] = warnings
        return merged

    warnings += list(af.attrs.get("warnings", []))

    # 앱스플라이어 전환 지표에만 _앱스플라이어 접미사를 붙이고 채널은 원래 이름 유지.
    af_cols = ["클릭", "회원가입", "구매", "구매매출"]
    af_metrics = af[JOIN_KEYS + af_cols].copy()
    af_metrics = af_metrics.rename(columns={c: f"{c}_앱스플라이어" for c in af_cols})

    merged = base.merge(af_metrics, on=JOIN_KEYS, how="left", indicator=True)

    # 조인 미스매치 카운트(검증용).
    only_channel = int((merged["_merge"] == "left_only").sum())
    af_only = len(af) - int((merged["_merge"] == "both").sum())
    if only_channel:
        warnings.append(f"channel 단독 행 {only_channel}건 (appsflyer 매칭 없음)")
    if af_only:
        warnings.append(f"appsflyer 단독 행 {af_only}건 (조인에서 제외됨)")
    merged = merged.drop(columns=["_merge"])

    # 비교 별칭 + 어트리뷰션 갭.
    for c in ["클릭", "구매", "구매매출"]:
        merged[f"{c}_채널"] = merged[c]
    merged["구매차이"] = merged["구매"] - merged["구매_앱스플라이어"]

    merged.attrs["warnings"] = warnings
    return merged


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    data = build_dataset(here)
    print(f"행 수: {len(data)}")
    print(f"날짜 범위: {data['일'].min().date()} ~ {data['일'].max().date()}")
    print(f"채널: {sorted(data['채널'].unique())}")
    print(f"소재타입: {sorted(data['소재타입'].unique())}")
    if data.attrs.get("warnings"):
        print("경고:")
        for w in data.attrs["warnings"]:
            print("  -", w)
