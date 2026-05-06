from __future__ import annotations

from io import BytesIO
from pathlib import Path

import streamlit as st

from core import (
    add_index_series,
    build_line_points_export,
    get_chinese_font_status,
    load_data_bundle,
    make_interactive_line_figure,
    make_matplotlib_figure,
    process_index_data,
    resolve_target,
    table_pct_chg_and_latest,
    try_fetch_optional_metrics,
    update_time_series_data,
)

st.set_page_config(page_title="指数盈利分解网页展示", page_icon=":bar_chart:", layout="wide")
st.markdown(
    """
<style>
.main .block-container {
    max-width: 1400px;
    padding-top: 1.4rem;
    padding-bottom: 1.2rem;
}
.title-wrap {
    border-radius: 12px;
    padding: 14px 18px;
    background: linear-gradient(90deg, #f4f8ff 0%, #eef6ff 100%);
    border: 1px solid #dbe7ff;
    margin-bottom: 14px;
}
.title-wrap h1 {
    margin: 0;
    font-size: 1.7rem;
}
.title-wrap p {
    margin: 6px 0 0 0;
    color: #4b5563;
}
div.stButton > button, div.stForm button[kind="primary"] {
    font-weight: 600;
}
</style>
""",
    unsafe_allow_html=True,
)
st.markdown(
    """
<div class="title-wrap">
  <h1>指数盈利分解网页展示</h1>
  <p>输入证券名称或 Wind 代码，生成图表、交互式折线图与坐标点明细。</p>
</div>
""",
    unsafe_allow_html=True,
)

active_font, font_candidates = get_chinese_font_status()
if active_font is None:
    st.warning("未检测到常用中文字体，图像可能出现中文乱码。建议安装: " + " / ".join(font_candidates))

project_root = Path(__file__).resolve().parent.parent

# ── 数据维护 expander ─────────────────────────────────────────────────────────
with st.expander("数据维护（周度更新 / 添加新资产）", expanded=False):
    st.markdown(
        "**周度更新**：将 close / PE_TTM / PB_LF / PB_MRQ_GSD 四张表更新到今日，按周频写回 parquet。  \n"
        "**添加新资产**：输入 Wind 代码（逗号或换行分隔），拉取自 2015-01-01 至今的历史数据并追加到 parquet。"
    )
    col_upd, col_add = st.columns([1, 2])
    with col_upd:
        if st.button("执行：周度更新", use_container_width=True):
            with st.spinner("正在从 Wind 拉取增量数据…"):
                try:
                    msg = update_time_series_data(project_root)
                    st.success(msg)
                    st.cache_data.clear()
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"周度更新失败: {exc}")
    with col_add:
        new_codes_input = st.text_area(
            "新增资产 Wind 代码（逗号或换行分隔）",
            placeholder="例如: 603906.SH\n000001.SH",
            height=80,
        )
        if st.button("执行：添加新资产", use_container_width=True):
            raw = new_codes_input.replace("\n", ",").replace("，", ",")
            codes_list = [c.strip() for c in raw.split(",") if c.strip()]
            if not codes_list:
                st.warning("请先填写至少一个 Wind 代码。")
            else:
                with st.spinner(f"正在添加 {len(codes_list)} 个标的…"):
                    try:
                        msg = add_index_series(project_root, codes_list)
                        st.success(msg)
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"添加新资产失败: {exc}")

# ── 补充最近交易日快照 checkbox ──────────────────────────────────────────────
supplement_today = st.checkbox(
    "补充最近交易日快照（内存）",
    value=True,
    help="勾选后，在加载 parquet 后额外从 Wind 拉取「昨日」单日数据并合并到内存，不写回文件。",
)


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

# ── 查询表单 ─────────────────────────────────────────────────────────────────
with st.container(border=True):
    with st.form("query_form"):
        c1, c2, c3 = st.columns([3, 3, 1.5])
        with c1:
            index = st.text_input("证券名称（如：龙蟠科技）", value="龙蟠科技")
        with c2:
            code = st.text_input("Wind 代码（如：603906.SH）", value="")
        with c3:
            st.markdown("<div style='height:27px'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("生成图像", use_container_width=True)

if submitted:
    try:
        index_name, index_code = resolve_target(bundle, index=index, code=code)
        data, data_org = process_index_data(bundle, index_name=index_name, take_log=False, take_clip=False)
        eg, dy, warn_msg = try_fetch_optional_metrics(index_code)

        data_pct_chg, data_latest = table_pct_chg_and_latest(
            data, data_org=data_org, expected_earnings_growth_2026=eg, latest_ttm_dividend_yield=dy
        )
        data_pct_chg = data_pct_chg.rename(columns={"close": "收盘价"})
        data_latest = data_latest.rename(columns={"ROE": "ROE(%)"})
        data_pct_chg.index.name = f"{index_name}_{index_code}"
        data_latest.index.name = ""

        st.success(f"已匹配: {index_name} ({index_code})")
        if warn_msg:
            st.warning(warn_msg)

        fig = make_matplotlib_figure(index_name, index_code, data, data_org, data_pct_chg, data_latest)
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
                label="下载坐标点明细 CSV",
                data=csv_bytes,
                file_name=f"{index_name}_{index_code}_坐标点明细.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with d2:
            st.download_button(
                label="下载静态总图 PNG",
                data=img_buffer.getvalue(),
                file_name=f"{index_name}_{index_code}_图表.png",
                mime="image/png",
                use_container_width=True,
            )
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
