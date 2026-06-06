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

# ---------------------------------------------------------------- KPI 카드
tot_imp = fdf["노출"].sum()
tot_clk = fdf["클릭"].sum()
tot_cost = fdf["비용"].sum()
tot_rev = fdf["구매매출"].sum()
tot_buy = fdf["구매"].sum()
ctr = tot_clk / tot_imp if tot_imp else 0
roas = tot_rev / tot_cost if tot_cost else 0
cpa = tot_cost / tot_buy if tot_buy else 0

with st.container(horizontal=True):
    st.metric("총 노출", f"{tot_imp:,.0f}", border=True)
    st.metric("총 클릭", f"{tot_clk:,.0f}", border=True)
    st.metric("CTR", fmt_pct(ctr), border=True)
    st.metric("총 비용", fmt_won(tot_cost), border=True)
    st.metric("총 매출", fmt_won(tot_rev), border=True)
    st.metric("ROAS", f"{roas:.2f}", border=True)
    st.metric("CPA", fmt_won(cpa), border=True)

# ---------------------------------------------------------------- 탭
tab_overview, tab_channel, tab_creative, tab_attr, tab_raw = st.tabs(
    ["개요", "채널·캠페인", "소재", "어트리뷰션 비교", "원본 데이터"]
)

# ---- 개요: 일자별 추세
with tab_overview:
    daily = (
        fdf.groupby("일")[["노출", "클릭", "비용", "구매매출", "구매"]]
        .sum()
        .reset_index()
    )
    daily["ROAS"] = daily["구매매출"] / daily["비용"].replace(0, pd.NA)
    daily["CTR"] = daily["클릭"] / daily["노출"].replace(0, pd.NA)

    if len(daily) <= 1:
        st.info(
            "현재 날짜가 하루뿐이라 추세선이 점 하나로 보입니다. "
            "다른 날짜 CSV를 폴더에 추가하면 추세가 그려집니다."
        )

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.subheader("일자별 비용 vs 매출")
            fig = px.line(daily, x="일", y=["비용", "구매매출"], markers=True)
            fig.update_layout(legend_title_text="", height=350)
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        with st.container(border=True):
            st.subheader("일자별 ROAS / CTR")
            fig = px.line(daily, x="일", y=["ROAS", "CTR"], markers=True)
            fig.update_layout(legend_title_text="", height=350)
            st.plotly_chart(fig, use_container_width=True)

# ---- 채널·캠페인
with tab_channel:
    by_ch = (
        fdf.groupby("채널")[["노출", "클릭", "비용", "구매", "구매매출"]]
        .sum()
        .reset_index()
    )
    by_ch["ROAS"] = by_ch["구매매출"] / by_ch["비용"].replace(0, pd.NA)
    by_ch["CTR"] = by_ch["클릭"] / by_ch["노출"].replace(0, pd.NA)

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.subheader("채널별 비용 vs 매출")
            fig = px.bar(
                by_ch.melt(id_vars="채널", value_vars=["비용", "구매매출"]),
                x="채널", y="value", color="variable", barmode="group",
            )
            fig.update_layout(legend_title_text="", height=350)
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        with st.container(border=True):
            st.subheader("채널별 ROAS")
            fig = px.bar(by_ch, x="채널", y="ROAS", color="채널", text_auto=".2f")
            fig.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig, use_container_width=True)

    with st.container(border=True):
        st.subheader("캠페인별 성과")
        by_cmp = (
            fdf.groupby(["채널", "캠페인"])[["노출", "클릭", "비용", "구매", "구매매출"]]
            .sum()
            .reset_index()
        )
        by_cmp["ROAS"] = by_cmp["구매매출"] / by_cmp["비용"].replace(0, pd.NA)
        by_cmp["CPA"] = by_cmp["비용"] / by_cmp["구매"].replace(0, pd.NA)
        st.dataframe(
            by_cmp.sort_values("구매매출", ascending=False),
            hide_index=True,
            use_container_width=True,
            column_config={
                "비용": st.column_config.NumberColumn(format="₩%d"),
                "구매매출": st.column_config.NumberColumn(format="₩%d"),
                "CPA": st.column_config.NumberColumn(format="₩%d"),
                "ROAS": st.column_config.NumberColumn(format="%.2f"),
            },
        )

# ---- 소재
with tab_creative:
    by_cr = (
        fdf.groupby("소재")[["노출", "클릭", "비용", "구매", "구매매출"]]
        .sum()
        .reset_index()
    )
    by_cr["ROAS"] = by_cr["구매매출"] / by_cr["비용"].replace(0, pd.NA)
    by_cr["CTR"] = by_cr["클릭"] / by_cr["노출"].replace(0, pd.NA)

    with st.container(border=True):
        st.subheader("소재별 ROAS Top 15")
        top = by_cr.sort_values("ROAS", ascending=False).head(15)
        fig = px.bar(top, x="ROAS", y="소재", orientation="h", text_auto=".2f")
        fig.update_layout(height=500, yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)

    with st.container(border=True):
        st.subheader("소재 효율 산점도 (비용 vs 매출, 크기=클릭)")
        fig = px.scatter(
            by_cr, x="비용", y="구매매출", size="클릭", color="ROAS",
            hover_name="소재", color_continuous_scale="Viridis",
        )
        fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True)

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
