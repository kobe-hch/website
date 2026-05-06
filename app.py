from __future__ import annotations

from io import BytesIO
from pathlib import Path

import streamlit as st

from core import (
    build_line_points_export,
    get_chinese_font_status,
    load_data_bundle,
    make_interactive_line_figure,
    make_matplotlib_figure,
    process_index_data,
    resolve_target,
    table_pct_chg_and_latest,
    try_fetch_optional_metrics,
)

st.set_page_config(page_title="指数盈利分解", page_icon=":bar_chart:", layout="wide")

st.markdown(
    """
<style>
/* ── 全局布局 ─────────────────────────────────────────────────────────── */
.main .block-container {
    max-width: 1380px;
    padding-top: 1.6rem;
    padding-bottom: 2.4rem;
    padding-left: 2rem;
    padding-right: 2rem;
}

/* ── 页面标题栏 ───────────────────────────────────────────────────────── */
.pg-header {
    display: flex;
    align-items: baseline;
    gap: 1.1rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid oklch(87% 0.010 72);
    margin-bottom: 1.6rem;
}
.pg-header h1 {
    margin: 0;
    font-size: 1.4rem;
    font-weight: 700;
    color: oklch(19% 0.010 260);
    letter-spacing: -0.01em;
}
.pg-header span {
    font-size: 0.875rem;
    color: oklch(50% 0.008 240);
}

/* ── 按钮 ─────────────────────────────────────────────────────────────── */
div.stButton > button,
div.stFormSubmitButton > button,
div.stDownloadButton > button {
    font-weight: 600;
    background-color: oklch(46% 0.135 255) !important;
    border: 1px solid oklch(40% 0.135 255) !important;
    color: oklch(98% 0.003 255) !important;
    border-radius: 6px !important;
    transition: background-color 0.12s ease-out, border-color 0.12s ease-out;
}
div.stButton > button:hover,
div.stFormSubmitButton > button:hover,
div.stDownloadButton > button:hover {
    background-color: oklch(39% 0.135 255) !important;
    border-color: oklch(34% 0.135 255) !important;
}

/* ── 사이드바 ──────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: oklch(97.5% 0.004 72);
    border-right: 1px solid oklch(89% 0.010 72);
}
section[data-testid="stSidebar"] > div {
    padding-top: 1.4rem;
}
.sb-section {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: oklch(52% 0.008 240);
    margin: 1.1rem 0 0.35rem;
}

/* ── 탭 텍스트 ─────────────────────────────────────────────────────────── */
div[data-testid="stTabs"] button {
    font-size: 0.9rem;
    font-weight: 500;
}
</style>
""",
    unsafe_allow_html=True,
)

# ── 页面标题 ──────────────────────────────────────────────────────────────────
st.markdown(
    """
<div class="pg-header">
  <h1>指数盈利分解</h1>
  <span>输入证券名称或 Wind 代码，生成图表与数据明细</span>
</div>
""",
    unsafe_allow_html=True,
)

active_font, font_candidates = get_chinese_font_status()
if active_font is None:
    st.warning("未检测到常用中文字体，图像可能出现中文乱码。建议安装: " + " / ".join(font_candidates))

project_root = Path(__file__).resolve().parent / "data"
supplement_today = False

# ── 数据加载 ──────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def cached_bundle(root: str, _supplement: bool):
    return load_data_bundle(root, supplement_today=_supplement)


try:
    bundle, snap_warn = cached_bundle(str(project_root), supplement_today)
except Exception as exc:  # noqa: BLE001
    st.error(f"数据文件加载失败，请检查 parquet 文件是否完整: {exc}")
    st.stop()

if snap_warn:
    st.warning(snap_warn)

# ── 查询表单 ──────────────────────────────────────────────────────────────────
with st.form("query_form"):
    c1, c2, c3 = st.columns([3, 3, 1.5])
    with c1:
        index = st.text_input("证券名称", value="", placeholder="如：龙蟠科技")
    with c2:
        code = st.text_input("Wind 代码", value="", placeholder="如：603906.SH")
    st.caption("证券名称与 Wind 代码二选一即可")
    with c3:
        st.markdown("<div style='height:27px'></div>", unsafe_allow_html=True)
        submitted = st.form_submit_button("生成图像", use_container_width=True)

# ── 查询结果 ──────────────────────────────────────────────────────────────────
if submitted:
    try:
        index_name, index_code = resolve_target(bundle, index=index, code=code)
        data, data_org = process_index_data(
            bundle, index_name=index_name, take_log=False, take_clip=False
        )
        eg, dy, warn_msg = try_fetch_optional_metrics(index_code)

        data_pct_chg, data_latest = table_pct_chg_and_latest(
            data,
            data_org=data_org,
            expected_earnings_growth_2026=eg,
            latest_ttm_dividend_yield=dy,
        )
        data_pct_chg = data_pct_chg.rename(columns={"close": "收盘价"})
        data_latest = data_latest.rename(columns={"ROE": "ROE(%)"})
        data_pct_chg.index.name = f"{index_name}_{index_code}"
        data_latest.index.name = ""

        st.success(f"已匹配: {index_name} ({index_code})")
        if warn_msg:
            st.warning(warn_msg)

        fig = make_matplotlib_figure(
            index_name, index_code, data, data_org, data_pct_chg, data_latest
        )
        points_df = build_line_points_export(data, data_org)
        pfig = make_interactive_line_figure(
            data,
            data_org,
            title_close=f"收盘价_{index_name}_{index_code}",
            title_pe="市盈率TTM",
            title_EPS="每股收益EPS",
            legend_close_label=f"收盘价_{index_name}_{index_code}",
            hover_close_label="收盘价(左2轴)",
        )

        tab1, tab2, tab3 = st.tabs(["静态总图", "交互式折线图", "坐标点明细"])
        with tab1:
            with st.container(border=True):
                st.pyplot(fig, use_container_width=True, dpi=600)
        with tab2:
            with st.container(border=True):
                st.plotly_chart(pfig, use_container_width=True)
        with tab3:
            with st.container(border=True):
                st.dataframe(points_df, use_container_width=True, hide_index=False)

        csv_bytes = points_df.to_csv(encoding="utf-8-sig").encode("utf-8-sig")
        img_buffer = BytesIO()
        fig.savefig(img_buffer, format="png", dpi=600, bbox_inches="tight")

        st.divider()
        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "下载坐标点明细 CSV",
                data=csv_bytes,
                file_name=f"{index_name}_{index_code}_坐标点明细.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with d2:
            st.download_button(
                "下载静态总图 PNG",
                data=img_buffer.getvalue(),
                file_name=f"{index_name}_{index_code}_图表.png",
                mime="image/png",
                use_container_width=True,
            )
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
