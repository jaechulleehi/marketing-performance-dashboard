"""마케팅 성과 EDA 대시보드.

raw/channel/, raw/appsflyer/ 의 YYYY-MM-DD.csv 를 자동으로 읽어 조인·전처리하고
채널/캠페인/소재별 성과를 인터랙티브하게 탐색한다.

실행:  python3 -m streamlit run streamlit_app.py
새 날짜 데이터는 raw/<소스>/ 에 CSV를 추가한 뒤 새로고침하면 자동 반영된다.
"""

from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import streamlit as st

from data_pipeline import build_dataset, source_coverage

HERE = os.path.dirname(os.path.abspath(__file__))

st.set_page_config(page_title="마케팅 성과 대시보드", page_icon="📊", layout="wide")


@st.cache_data
def load_data(folder: str, _mtime: float) -> pd.DataFrame:
    """데이터 로드. 폴더 내 CSV 수정시각(_mtime)이 바뀌면 캐시 자동 무효화."""
    return build_dataset(folder)


def folder_mtime(folder: str) -> float:
    """raw/ 내 모든 CSV의 최신 수정시각 → 캐시 키로 사용(파일 추가 시 자동 무효화)."""
    import glob

    paths = glob.glob(os.path.join(folder, "raw", "**", "*.csv"), recursive=True)
    return max((os.path.getmtime(p) for p in paths), default=0.0)


def fmt_won(x: float) -> str:
    return f"₩{x:,.0f}" if pd.notna(x) else "-"


def fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%" if pd.notna(x) else "-"


# ============================================================ 메트릭 하이라키
# 분석은 항상 같은 위계로 진행한다:
#   ① 볼륨/퍼널: 노출 → 클릭 → 회원가입 → 구매   (규모)
#   ② 금액:      비용, 구매매출
#   ③ 효율:      CTR·CVR(퍼널 전환) → CPC·CPA·AOV(단가) → ROAS(성과)
VOLUME = ["노출", "클릭", "회원가입", "구매"]
BASE_SUM = ["노출", "클릭", "회원가입", "구매", "비용", "구매매출"]

GOOD_ROAS = 4.0  # docs/metrics-definitions.md 의 '양호' 기준선

# 표 컬럼 포맷(메트릭 하이라키 순).
TABLE_FORMAT = {
    "노출": st.column_config.NumberColumn("노출", format="%d"),
    "클릭": st.column_config.NumberColumn("클릭", format="%d"),
    "회원가입": st.column_config.NumberColumn("가입", format="%d"),
    "구매": st.column_config.NumberColumn("구매", format="%d"),
    "비용": st.column_config.NumberColumn("비용", format="₩%d"),
    "구매매출": st.column_config.NumberColumn("매출", format="₩%d"),
    "CTR": st.column_config.NumberColumn("CTR", format="%.2f%%"),
    "CVR": st.column_config.NumberColumn("CVR", format="%.2f%%"),
    "CPC": st.column_config.NumberColumn("CPC", format="₩%d"),
    "CPA": st.column_config.NumberColumn("CPA", format="₩%d"),
    "AOV": st.column_config.NumberColumn("AOV", format="₩%d"),
    "ROAS": st.column_config.NumberColumn("ROAS", format="%.2f"),
}
METRIC_ORDER = ["노출", "클릭", "회원가입", "구매", "비용", "구매매출",
                "CTR", "CVR", "CPC", "CPA", "AOV", "ROAS"]


def aggregate(data: pd.DataFrame, by) -> pd.DataFrame:
    """차원(by)별 집계 + 효율지표. 비율은 '합의 비율'로 계산(비율의 평균 금지).

    CTR·CVR 은 표시 편의를 위해 %(×100)로 저장.
    """
    keys = [by] if isinstance(by, str) else list(by)
    g = data.groupby(keys, as_index=False)[BASE_SUM].sum()

    def sdiv(n: str, d: str) -> pd.Series:
        return g[n] / g[d].replace(0, pd.NA)

    g["CTR"] = sdiv("클릭", "노출") * 100
    g["CVR"] = sdiv("구매", "클릭") * 100
    g["CPC"] = sdiv("비용", "클릭")
    g["CPA"] = sdiv("비용", "구매")
    g["AOV"] = sdiv("구매매출", "구매")
    g["ROAS"] = sdiv("구매매출", "비용")
    return g


def metric_table(g: pd.DataFrame, dims: list[str], sort_by: str = "구매매출") -> None:
    """메트릭 하이라키 순서로 정렬된 상세 테이블."""
    cols = dims + [m for m in METRIC_ORDER if m in g.columns]
    st.dataframe(
        g[cols].sort_values(sort_by, ascending=False),
        hide_index=True,
        use_container_width=True,
        column_config=TABLE_FORMAT,
    )


def render_dimension(data: pd.DataFrame, dim: str, sub_dim: str | None, key: str) -> None:
    """한 차원(채널/캠페인/그룹/소재…)에 대한 일관된 메트릭 하이라키 분석 뷰."""
    g = aggregate(data, dim).sort_values("구매매출", ascending=False)
    n = len(g)
    if n == 0:
        st.info("데이터가 없습니다.")
        return

    # --- 하이라이트 (성과 요약)
    top_rev = g.iloc[0]
    with st.container(horizontal=True):
        st.metric(f"{dim} 개수", f"{n}", border=True)
        st.metric(f"매출 1위 {dim}", str(top_rev[dim]), fmt_won(top_rev["구매매출"]),
                  border=True)
        if g["ROAS"].notna().any():
            br = g.loc[g["ROAS"].idxmax()]
            st.metric("ROAS 최고", str(br[dim]), f"{br['ROAS']:.2f}", border=True)
        if g["CPA"].notna().any():
            lc = g.loc[g["CPA"].idxmin()]
            st.metric("CPA 최저", str(lc[dim]), fmt_won(lc["CPA"]), border=True)

    # --- ② 금액: 비용 vs 매출  /  ③ 성과: ROAS
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("**② 비용 vs 매출**")
            fig = px.bar(
                g.melt(id_vars=dim, value_vars=["비용", "구매매출"]),
                x=dim, y="value", color="variable", barmode="group",
            )
            fig.update_layout(legend_title_text="", height=330,
                              xaxis_title="", yaxis_title="원")
            st.plotly_chart(fig, use_container_width=True, key=f"{key}_money")
    with c2:
        with st.container(border=True):
            st.markdown(f"**③ ROAS** (점선 = 양호 기준 {GOOD_ROAS})")
            gr = g.dropna(subset=["ROAS"]).sort_values("ROAS", ascending=False)
            fig = px.bar(gr, x=dim, y="ROAS", color="ROAS", text_auto=".2f",
                         color_continuous_scale="RdYlGn")
            fig.add_hline(y=GOOD_ROAS, line_dash="dot", line_color="gray")
            fig.update_layout(height=330, xaxis_title="", coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True, key=f"{key}_roas")

    # --- ③ 퍼널 효율: CTR·CVR  /  효율 맵
    c3, c4 = st.columns(2)
    with c3:
        with st.container(border=True):
            st.markdown("**③ 퍼널 전환율 — CTR·CVR**")
            fig = px.bar(
                g.melt(id_vars=dim, value_vars=["CTR", "CVR"]),
                x=dim, y="value", color="variable", barmode="group",
            )
            fig.update_layout(legend_title_text="", height=330,
                              xaxis_title="", yaxis_title="%")
            st.plotly_chart(fig, use_container_width=True, key=f"{key}_funnel")
    with c4:
        with st.container(border=True):
            st.markdown("**효율 맵** — 비용(x) vs 매출(y), 크기=구매, 색=ROAS")
            fig = px.scatter(
                g, x="비용", y="구매매출", size="구매", color="ROAS",
                hover_name=dim, color_continuous_scale="RdYlGn", size_max=40,
            )
            fig.update_layout(height=330)
            st.plotly_chart(fig, use_container_width=True, key=f"{key}_scatter")

    # --- 상세 테이블
    with st.container(border=True):
        st.markdown(f"**{dim}별 상세** (메트릭 하이라키 순)")
        metric_table(g, [dim])

    # --- 드릴다운: 한 항목 선택 → 퍼널 + 하위 차원 분해
    if sub_dim:
        with st.container(border=True):
            st.markdown(f"**🔎 드릴다운** — {dim} 선택 → 퍼널 & {sub_dim}별 분해")
            options = list(g[dim])
            sel = st.selectbox(f"{dim} 선택", options, key=f"{key}_drill")
            sub = data[data[dim] == sel]

            d1, d2 = st.columns([1, 2])
            with d1:
                row = aggregate(sub, dim).iloc[0]
                funnel_df = pd.DataFrame({
                    "단계": VOLUME,
                    "값": [row["노출"], row["클릭"], row["회원가입"], row["구매"]],
                })
                fig = px.funnel(funnel_df, x="값", y="단계")
                fig.update_layout(height=300, title_text=f"{sel} 퍼널")
                st.plotly_chart(fig, use_container_width=True, key=f"{key}_drillfunnel")
            with d2:
                gs = aggregate(sub, sub_dim)
                metric_table(gs, [sub_dim])


# ---------------------------------------------------------------- 데이터 로드
try:
    df = load_data(HERE, folder_mtime(HERE))
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()

# ---------------------------------------------------------------- 사이드바 필터
with st.sidebar:
    st.header("필터")

    min_d, max_d = df["일"].min().date(), df["일"].max().date()
    date_range = st.date_input("기간", value=(min_d, max_d), min_value=min_d, max_value=max_d)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
    else:
        start = end = date_range

    channels = sorted(df["채널"].unique())
    sel_channels = st.multiselect("채널", channels, default=channels)

    campaigns = sorted(df[df["채널"].isin(sel_channels)]["캠페인"].unique())
    sel_campaigns = st.multiselect("캠페인", campaigns, default=campaigns)

    st.caption(
        "💡 새 날짜 데이터는 `raw/channel/`, `raw/appsflyer/` 에 "
        "`YYYY-MM-DD.csv` 로 추가하면 자동 반영됩니다."
    )

    warnings = df.attrs.get("warnings", [])
    if warnings:
        with st.expander(f"⚠️ 데이터 검증 경고 {len(warnings)}건", expanded=False):
            for w in warnings:
                st.write("- ", w)

mask = (
    (df["일"].dt.date >= start)
    & (df["일"].dt.date <= end)
    & (df["채널"].isin(sel_channels))
    & (df["캠페인"].isin(sel_campaigns))
)
fdf = df[mask]

st.title("📊 마케팅 성과 대시보드")
st.caption(f"기간 {start} ~ {end} · {len(fdf)}개 행 · 노출/비용은 채널 데이터 기준")

# ---------------------------------------------------------------- 데이터 적재 현황
cov = source_coverage(HERE)
with st.container(border=True):
    st.markdown("**📦 데이터 적재 현황** (raw/ 일별 파일 기준)")
    cols = st.columns(len(cov))
    for col, (src, info) in zip(cols, cov.items()):
        with col:
            if info["files"] == 0:
                st.metric(src, "없음")
                continue
            n_missing = len(info["missing"])
            st.metric(
                src,
                f'{info["files"]}일',
                delta=(f"누락 {n_missing}일" if n_missing else "누락 없음"),
                delta_color=("inverse" if n_missing else "normal"),
            )
            st.caption(f'{info["first"]} ~ {info["last"]}')
            if n_missing:
                preview = ", ".join(info["missing"][:5])
                more = " …" if n_missing > 5 else ""
                st.caption(f"⚠️ 누락: {preview}{more}")

if fdf.empty:
    st.warning("선택한 조건에 해당하는 데이터가 없습니다.")
    st.stop()

# ---------------------------------------------------------------- KPI (하이라키)
tot_imp = fdf["노출"].sum()
tot_clk = fdf["클릭"].sum()
tot_join = fdf["회원가입"].sum()
tot_buy = fdf["구매"].sum()
tot_cost = fdf["비용"].sum()
tot_rev = fdf["구매매출"].sum()
ctr = tot_clk / tot_imp if tot_imp else 0
cvr = tot_buy / tot_clk if tot_clk else 0
roas = tot_rev / tot_cost if tot_cost else 0
cpa = tot_cost / tot_buy if tot_buy else 0

st.markdown("##### ① 볼륨 / 퍼널")
with st.container(horizontal=True):
    st.metric("노출", f"{tot_imp:,.0f}", border=True)
    st.metric("클릭", f"{tot_clk:,.0f}", border=True)
    st.metric("회원가입", f"{tot_join:,.0f}", border=True)
    st.metric("구매", f"{tot_buy:,.0f}", border=True)
st.markdown("##### ② 금액 / ③ 효율")
with st.container(horizontal=True):
    st.metric("비용", fmt_won(tot_cost), border=True)
    st.metric("매출", fmt_won(tot_rev), border=True)
    st.metric("ROAS", f"{roas:.2f}", border=True)
    st.metric("CTR", fmt_pct(ctr), border=True)
    st.metric("CVR", fmt_pct(cvr), border=True)
    st.metric("CPA", fmt_won(cpa), border=True)

# ---------------------------------------------------------------- 탭 (차원별 독립 뷰)
(tab_overview, tab_channel, tab_campaign, tab_group,
 tab_creative, tab_attr, tab_raw) = st.tabs(
    ["개요", "채널", "캠페인", "그룹", "소재", "어트리뷰션", "원본 데이터"]
)

# ---- 개요: 전체 퍼널 + 일자별 추세
with tab_overview:
    c0, c1, c2 = st.columns([1, 1.3, 1.3])
    with c0:
        with st.container(border=True):
            st.markdown("**전체 퍼널**")
            funnel_df = pd.DataFrame({
                "단계": VOLUME,
                "값": [tot_imp, tot_clk, tot_join, tot_buy],
            })
            fig = px.funnel(funnel_df, x="값", y="단계")
            fig.update_layout(height=320)
            st.plotly_chart(fig, use_container_width=True, key="ov_funnel")

    daily = aggregate(fdf, "일").sort_values("일")
    if len(daily) <= 1:
        st.info("날짜가 하루뿐이라 추세가 점으로 보입니다. raw/ 에 다른 날짜를 추가하세요.")
    with c1:
        with st.container(border=True):
            st.markdown("**일자별 비용 vs 매출**")
            fig = px.line(daily, x="일", y=["비용", "구매매출"], markers=True)
            fig.update_layout(legend_title_text="", height=320, yaxis_title="원")
            st.plotly_chart(fig, use_container_width=True, key="ov_money")
    with c2:
        with st.container(border=True):
            st.markdown("**일자별 ROAS / CTR**")
            fig = px.line(daily, x="일", y=["ROAS", "CTR"], markers=True)
            fig.update_layout(legend_title_text="", height=320)
            st.plotly_chart(fig, use_container_width=True, key="ov_eff")

# ---- 채널 뷰
with tab_channel:
    st.caption("채널 단위 성과. 드릴다운에서 채널 → 캠페인으로 분해합니다.")
    render_dimension(fdf, "채널", "캠페인", key="ch")

# ---- 캠페인 뷰 (캠페인 / 캠페인목적 전환)
with tab_campaign:
    cmp_dim = st.segmented_control(
        "분석 단위", ["캠페인", "캠페인목적"], default="캠페인", key="cmp_dim",
    ) or "캠페인"
    st.caption(f"{cmp_dim} 단위 성과. 드릴다운에서 → 그룹으로 분해합니다.")
    render_dimension(fdf, cmp_dim, "그룹", key="cmp")

# ---- 그룹(타겟) 뷰
with tab_group:
    st.caption("타겟 그룹(논타겟·유사타겟·리마케팅·VIP·윈백) 성과. 드릴다운 → 소재.")
    render_dimension(fdf, "그룹", "소재", key="grp")

# ---- 소재 뷰 (소재타입 / AB변형 / 개별소재)
with tab_creative:
    cr_dim = st.segmented_control(
        "분석 단위", ["소재타입", "AB변형", "소재"], default="소재타입", key="cr_dim",
    ) or "소재타입"
    sub = "소재" if cr_dim != "소재" else "소재타입"
    st.caption(f"{cr_dim} 단위 성과. 드릴다운 → {sub}.")
    render_dimension(fdf, cr_dim, sub, key="cr")

# ---- 어트리뷰션 비교 (채널 vs 앱스플라이어)
with tab_attr:
    st.caption("채널 데이터의 전환과 앱스플라이어 전환을 비교합니다 (어트리뷰션 갭).")
    if "구매_앱스플라이어" in fdf and fdf["구매_앱스플라이어"].notna().any():
        cmp = (
            fdf.groupby("채널")[["구매_채널", "구매_앱스플라이어"]]
            .sum()
            .reset_index()
        )
        c1, c2 = st.columns(2)
        with c1:
            with st.container(border=True):
                st.subheader("채널별 구매: 채널 vs 앱스플라이어")
                fig = px.bar(
                    cmp.melt(id_vars="채널", value_vars=["구매_채널", "구매_앱스플라이어"]),
                    x="채널", y="value", color="variable", barmode="group",
                )
                fig.update_layout(legend_title_text="", height=380)
                st.plotly_chart(fig, use_container_width=True)
        with c2:
            with st.container(border=True):
                st.subheader("매출 비교")
                rev = (
                    fdf.groupby("채널")[["구매매출_채널", "구매매출_앱스플라이어"]]
                    .sum()
                    .reset_index()
                )
                fig = px.bar(
                    rev.melt(id_vars="채널"),
                    x="채널", y="value", color="variable", barmode="group",
                )
                fig.update_layout(legend_title_text="", height=380)
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("앱스플라이어 데이터가 조인되지 않아 비교할 수 없습니다.")

# ---- 원본 데이터
with tab_raw:
    st.subheader("조인·전처리된 전체 데이터")
    st.dataframe(fdf, hide_index=True, use_container_width=True)
    st.download_button(
        "CSV 다운로드",
        fdf.to_csv(index=False).encode("utf-8-sig"),
        file_name="merged_marketing_data.csv",
        mime="text/csv",
    )
