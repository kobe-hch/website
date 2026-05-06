from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter

import HHWindPy as w


COLOR = ["#E1547A", "#79B9C6", "#969696", "#f2c097", "#96c268", "#4451e3"]
CHINESE_FONT_CANDIDATES = [
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Source Han Sans CN",
    "Arial Unicode MS",
]
_ACTIVE_CHINESE_FONT: str | None = None


@dataclass
class DataBundle:
    sec_name: pd.DataFrame
    close: pd.DataFrame
    pe: pd.DataFrame
    pb: pd.DataFrame


def configure_matplotlib_chinese_font() -> tuple[str | None, list[str]]:
    """配置 Matplotlib 中文字体；返回 (生效字体, 候选列表)。"""
    global _ACTIVE_CHINESE_FONT

    available_names = {f.name for f in font_manager.fontManager.ttflist}
    selected = next((name for name in CHINESE_FONT_CANDIDATES if name in available_names), None)
    _ACTIVE_CHINESE_FONT = selected

    # 即使未匹配到已安装字体，也设置候选链，便于系统继续回退。
    plt.rcParams["font.sans-serif"] = CHINESE_FONT_CANDIDATES + list(plt.rcParams.get("font.sans-serif", []))
    plt.rcParams["axes.unicode_minus"] = False
    return _ACTIVE_CHINESE_FONT, CHINESE_FONT_CANDIDATES


def get_chinese_font_status() -> tuple[str | None, list[str]]:
    return _ACTIVE_CHINESE_FONT, CHINESE_FONT_CANDIDATES


configure_matplotlib_chinese_font()


def initialize_data(*args, **kwargs):
    raise NotImplementedError("initialize_data 暂未实现（对应 code.py 36-286）。")


def batch_clean_data(*args, **kwargs):
    raise NotImplementedError("batch_clean_data 暂未实现（对应 code.py 299-315）。")


def append_latest_snapshot(*args, **kwargs):
    """兼容旧名；请使用 append_latest_snapshot_in_memory。"""
    return append_latest_snapshot_in_memory(*args, **kwargs)


def _normalize_wind_codes(codes: list[str] | tuple[str, ...] | str) -> str:
    if isinstance(codes, str):
        return ",".join(c.strip().upper() for c in codes.split(",") if c.strip())
    return ",".join(str(c).strip().upper() for c in codes if str(c).strip())


def _wsd_df(res: object) -> pd.DataFrame:
    if res is None:
        raise RuntimeError("Wind wsd 无返回（网络或服务异常）。")
    err = getattr(res, "ErrorCode", None)
    if err not in (None, 0):
        raise RuntimeError(f"Wind wsd ErrorCode={err}")
    df = getattr(res, "dfData", None)
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        raise RuntimeError("Wind wsd 返回空表（dfData 为空）。")
    return df.copy()


def _wss_sec_names_for_codes(codes: list[str]) -> pd.DataFrame:
    """返回 columns 为 sec_name, index_code 的 DataFrame，顺序与 codes 一致。"""
    codes = [str(c).strip().upper() for c in codes if str(c).strip()]
    if not codes:
        raise ValueError("代码列表为空。")
    csv = ",".join(codes)
    res = w.wss(csv, "sec_name")
    if res is None:
        raise RuntimeError("Wind wss 无返回（网络或服务异常）。")
    err = getattr(res, "ErrorCode", None)
    if err not in (None, 0):
        raise RuntimeError(f"Wind wss ErrorCode={err}")
    names: list[str] = []
    data = getattr(res, "Data", None)
    if data and len(data) >= 1 and isinstance(data[0], (list, tuple)) and len(data[0]) == len(codes):
        names = [str(x) if x is not None else "" for x in data[0]]
    else:
        df = getattr(res, "dfData", None)
        if df is None or df.empty:
            raise RuntimeError("Wind wss 返回空表或无法解析 sec_name。")
        col = None
        for c in df.columns:
            if str(c).lower() == "sec_name":
                col = c
                break
        if col is None:
            col = df.columns[-1]
        if df.shape[0] == len(codes):
            names = [str(x) for x in df[col].tolist()]
        elif df.shape[1] == len(codes):
            names = [str(x) for x in df.iloc[0].tolist()]
        else:
            names = [str(x) for x in df[col].tolist()[: len(codes)]]
            if len(names) != len(codes):
                raise RuntimeError("Wind wss 返回行数与请求代码数不一致，无法对齐 sec_name。")
    out = pd.DataFrame({"index_code": codes, "sec_name": names})
    mask = out["sec_name"].duplicated(keep=False) & out["index_code"].str.contains(".HK", regex=False)
    out.loc[mask, "sec_name"] = out.loc[mask, "sec_name"] + "_H股"
    return out


def _normalize_wsd_week_block(
    data_add: pd.DataFrame,
    sec_name: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """周度块：单列转置、首周五索引、列名为 sec_name（与 code.py 增量段一致，剔除末行在 concat 之后做）。"""
    if data_add.shape[1] == 1:
        data_add = data_add.T
        friday_date = pd.date_range(start=start_date, end=end_date, freq="D")
        friday_date = friday_date[friday_date.weekday == 4][0]
        data_add.index = pd.DatetimeIndex([friday_date])
    data_add = data_add.copy()
    data_add.columns = sec_name["sec_name"].values
    data_add.index = pd.to_datetime(data_add.index)
    return data_add


def _concat_drop_incomplete_last_week(
    df: pd.DataFrame,
    data_add: pd.DataFrame,
    *,
    drop_dup_before_trim: bool,
    dedupe_keep_last: bool,
) -> pd.DataFrame:
    """合并增量后若末行非周五则剔除（与 code.py close/pe/pb 逻辑一致）。"""
    out = pd.concat([df, data_add], axis=0)
    if drop_dup_before_trim:
        out = out.drop_duplicates()
    out = out.sort_index()
    out = out.copy()
    out["mark"] = out.index.weekday
    if len(out) and out["mark"].iloc[-1] != 4:
        out = out.iloc[:-1]
    out = out.drop(columns=["mark"])
    if dedupe_keep_last:
        out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def update_time_series_data(base_dir: str | Path) -> str:
    """周度增量更新四个 parquet（对齐 code.py 98-201）。"""
    base_dir = Path(base_dir)
    today = datetime.now().strftime("%Y-%m-%d")
    sec_name = pd.read_parquet(base_dir / "指数代码与名称.parquet")
    sec_name = sec_name[["sec_name", "index_code"]].copy()
    sec_name["sec_name"] = sec_name["sec_name"].astype(str).str.strip()
    sec_name["index_code"] = sec_name["index_code"].astype(str).str.strip()
    col_rule = sec_name["index_code"].tolist()
    codes_arg = _normalize_wind_codes(col_rule)
    opt = "Period=W;PriceAdj=F"
    logs: list[str] = []

    close = pd.read_parquet(base_dir / "指数价格数据.parquet")
    close.index = pd.to_datetime(close.index)
    start_date = close.index.max().strftime("%Y-%m-%d")
    if start_date < today:
        data_add = _wsd_df(w.wsd(codes_arg, "close", start_date, today, opt))
        data_add = _normalize_wsd_week_block(data_add, sec_name, start_date, today)
        close = _concat_drop_incomplete_last_week(
            close, data_add, drop_dup_before_trim=True, dedupe_keep_last=False
        )
        close.to_parquet(base_dir / "指数价格数据.parquet", index=True)
        logs.append(f"close: 已追加增量块")
    else:
        logs.append("close: 已是最新，跳过")

    pe = pd.read_parquet(base_dir / "指数PE数据.parquet")
    pe.index = pd.to_datetime(pe.index)
    start_date = pe.index.max().strftime("%Y-%m-%d")
    if start_date < today:
        data_add = _wsd_df(w.wsd(codes_arg, "pe_ttm", start_date, today, opt))
        data_add = _normalize_wsd_week_block(data_add, sec_name, start_date, today)
        pe = _concat_drop_incomplete_last_week(pe, data_add, drop_dup_before_trim=False, dedupe_keep_last=True)
        pe.to_parquet(base_dir / "指数PE数据.parquet", index=True)
        logs.append("pe_ttm: 已追加增量块")
    else:
        logs.append("pe_ttm: 已是最新，跳过")

    pb = pd.read_parquet(base_dir / "指数PB数据.parquet")
    pb.index = pd.to_datetime(pb.index)
    start_date = pb.index.max().strftime("%Y-%m-%d")
    if start_date < today:
        data_add = _wsd_df(w.wsd(codes_arg, "pb_lf", start_date, today, opt))
        data_add = _normalize_wsd_week_block(data_add, sec_name, start_date, today)
        pb = _concat_drop_incomplete_last_week(pb, data_add, drop_dup_before_trim=False, dedupe_keep_last=True)
        pb.to_parquet(base_dir / "指数PB数据.parquet", index=True)
        logs.append("pb_lf: 已追加增量块")
    else:
        logs.append("pb_lf: 已是最新，跳过")

    pb_2 = pd.read_parquet(base_dir / "指数PB数据_海外.parquet")
    pb_2.index = pd.to_datetime(pb_2.index)
    start_date = pb_2.index.max().strftime("%Y-%m-%d")
    if start_date < today:
        data_add = _wsd_df(w.wsd(codes_arg, "pb_mrq_gsd", start_date, today, opt))
        data_add = _normalize_wsd_week_block(data_add, sec_name, start_date, today)
        pb_2 = _concat_drop_incomplete_last_week(pb_2, data_add, drop_dup_before_trim=False, dedupe_keep_last=True)
        pb_2.to_parquet(base_dir / "指数PB数据_海外.parquet", index=True)
        logs.append("pb_mrq_gsd: 已追加增量块")
    else:
        logs.append("pb_mrq_gsd: 已是最新，跳过")

    return "；".join(logs)


def add_index_series(base_dir: str | Path, new_codes: list[str]) -> str:
    """为 parquet 增加新标的列（对齐 code.py 203-285 拉数与合并逻辑）。"""
    base_dir = Path(base_dir)
    add_codes = [str(c).strip().upper() for c in new_codes if str(c).strip()]
    if not add_codes:
        raise ValueError("请提供至少一个 Wind 代码。")

    sec_name = pd.read_parquet(base_dir / "指数代码与名称.parquet")
    sec_name = sec_name[["sec_name", "index_code"]].copy()
    sec_name["sec_name"] = sec_name["sec_name"].astype(str).str.strip()
    sec_name["index_code"] = sec_name["index_code"].astype(str).str.strip()

    existing = set(sec_name["index_code"].str.upper())
    to_add = [c for c in add_codes if c not in existing]
    if not to_add:
        return "所选代码已在指数代码与名称中，未写入。"

    new_rows = _wss_sec_names_for_codes(to_add)
    sec_name = pd.concat([sec_name, new_rows], axis=0, ignore_index=True)
    col_rule = sec_name["sec_name"].tolist()
    codes_arg = _normalize_wind_codes(to_add)

    close = pd.read_parquet(base_dir / "指数价格数据.parquet")
    pe = pd.read_parquet(base_dir / "指数PE数据.parquet")
    pb = pd.read_parquet(base_dir / "指数PB数据.parquet")
    pb_2 = pd.read_parquet(base_dir / "指数PB数据_海外.parquet")
    close.index = pd.to_datetime(close.index)
    pe.index = pd.to_datetime(pe.index)
    pb.index = pd.to_datetime(pb.index)
    pb_2.index = pd.to_datetime(pb_2.index)
    opt = "Period=W;PriceAdj=F"

    end_close = close.index.max().strftime("%Y-%m-%d")
    data_add = _wsd_df(w.wsd(codes_arg, "close", "2015-01-01", end_close, opt))
    if data_add.shape[1] == 1:
        data_add.columns = [new_rows.loc[new_rows["index_code"] == to_add[0], "sec_name"].values[0]]
    else:
        data_add.columns = sec_name[sec_name["index_code"].isin(to_add)]["sec_name"].values
    data_add.index = pd.to_datetime(data_add.index)
    close = pd.concat([close, data_add], axis=1).drop_duplicates().sort_index()
    close = close.reindex(columns=col_rule)

    end_pe = pe.index.max().strftime("%Y-%m-%d")
    data_add = _wsd_df(w.wsd(codes_arg, "pe_ttm", "2015-01-01", end_pe, opt))
    if data_add.shape[1] == 1:
        data_add.columns = [new_rows.loc[new_rows["index_code"] == to_add[0], "sec_name"].values[0]]
    else:
        data_add.columns = sec_name[sec_name["index_code"].isin(to_add)]["sec_name"].values
    data_add.index = pd.to_datetime(data_add.index)
    pe = pd.concat([pe, data_add], axis=1).drop_duplicates().sort_index()
    pe = pe.reindex(columns=col_rule)

    end_pb = pb.index.max().strftime("%Y-%m-%d")
    data_add = _wsd_df(w.wsd(codes_arg, "pb_lf", "2015-01-01", end_pb, opt))
    if data_add.shape[1] == 1:
        data_add.columns = [new_rows.loc[new_rows["index_code"] == to_add[0], "sec_name"].values[0]]
    else:
        data_add.columns = sec_name[sec_name["index_code"].isin(to_add)]["sec_name"].values
    data_add.index = pd.to_datetime(data_add.index)
    pb = pd.concat([pb, data_add], axis=1).drop_duplicates().sort_index()
    pb = pb.reindex(columns=col_rule)

    end_pb2 = pb_2.index.max().strftime("%Y-%m-%d")
    data_add = _wsd_df(w.wsd(codes_arg, "pb_mrq_gsd", "2015-01-01", end_pb2, opt))
    if data_add.shape[1] == 1:
        data_add.columns = [new_rows.loc[new_rows["index_code"] == to_add[0], "sec_name"].values[0]]
    else:
        data_add.columns = sec_name[sec_name["index_code"].isin(to_add)]["sec_name"].values
    data_add.index = pd.to_datetime(data_add.index)
    pb_2 = pd.concat([pb_2, data_add], axis=1).drop_duplicates().sort_index()
    pb_2 = pb_2.reindex(columns=col_rule)

    sec_name.to_parquet(base_dir / "指数代码与名称.parquet", index=False)
    close.to_parquet(base_dir / "指数价格数据.parquet", index=True)
    pe.to_parquet(base_dir / "指数PE数据.parquet", index=True)
    pb.to_parquet(base_dir / "指数PB数据.parquet", index=True)
    pb_2.to_parquet(base_dir / "指数PB数据_海外.parquet", index=True)
    return f"已添加 {len(to_add)} 个标的并写回 parquet: " + ", ".join(to_add)


def append_latest_snapshot_in_memory(
    sec_name: pd.DataFrame,
    close: pd.DataFrame,
    pe: pd.DataFrame,
    pb_domestic: pd.DataFrame,
    pb_2: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str | None]:
    """对齐 code.py 317-348：使用「当前自然日减 1 天」为快照日期，仅内存合并。"""
    snap_day = (pd.Timestamp.now().normalize() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    sec = sec_name[["sec_name", "index_code"]].copy()
    sec["sec_name"] = sec["sec_name"].astype(str).str.strip()
    sec["index_code"] = sec["index_code"].astype(str).str.strip()
    col_rule = sec["index_code"].tolist()
    codes_arg = _normalize_wind_codes(col_rule)
    warn: str | None = None
    try:
        c = close.copy()
        p = pe.copy()
        b = pb_domestic.copy()
        b2 = pb_2.copy()
        c.index = pd.to_datetime(c.index)
        p.index = pd.to_datetime(p.index)
        b.index = pd.to_datetime(b.index)
        b2.index = pd.to_datetime(b2.index)

        row = _wsd_df(w.wsd(codes_arg, "close", snap_day, snap_day, ""))
        row = row.T
        row.index = pd.to_datetime([snap_day])
        row.columns = sec["sec_name"].values
        c = pd.concat([c, row], axis=0).drop_duplicates().sort_index()

        row = _wsd_df(w.wsd(codes_arg, "pe_ttm", snap_day, snap_day, ""))
        row = row.T
        row.index = pd.to_datetime([snap_day])
        row.columns = sec["sec_name"].values
        p = pd.concat([p, row], axis=0).drop_duplicates().sort_index()

        row = _wsd_df(w.wsd(codes_arg, "pb_lf", snap_day, snap_day, ""))
        row = row.T
        row.index = pd.to_datetime([snap_day])
        row.columns = sec["sec_name"].values
        b = pd.concat([b, row], axis=0).drop_duplicates().sort_index()

        row = _wsd_df(w.wsd(codes_arg, "pb_mrq_gsd", snap_day, snap_day, ""))
        row = row.T
        row.index = pd.to_datetime([snap_day])
        row.columns = sec["sec_name"].values
        b2 = pd.concat([b2, row], axis=0).drop_duplicates().sort_index()
        return c, p, b, b2, None
    except Exception as exc:  # noqa: BLE001
        warn = f"补充最近交易日快照失败（已使用本地 parquet）: {exc}"
        return close, pe, pb_domestic, pb_2, warn


def load_data_bundle(
    base_dir: str | Path,
    supplement_today: bool = True,
) -> tuple[DataBundle, str | None]:
    base_dir = Path(base_dir)
    sec_name = pd.read_parquet(base_dir / "指数代码与名称.parquet")
    close = pd.read_parquet(base_dir / "指数价格数据.parquet")
    pe = pd.read_parquet(base_dir / "指数PE数据.parquet")
    pb_dom = pd.read_parquet(base_dir / "指数PB数据.parquet")
    pb_2 = pd.read_parquet(base_dir / "指数PB数据_海外.parquet")

    sec_name = sec_name[["sec_name", "index_code"]].copy()
    sec_name["sec_name"] = sec_name["sec_name"].astype(str).str.strip()
    sec_name["index_code"] = sec_name["index_code"].astype(str).str.strip()

    close.index = pd.to_datetime(close.index)
    pe.index = pd.to_datetime(pe.index)
    pb_dom.index = pd.to_datetime(pb_dom.index)
    pb_2.index = pd.to_datetime(pb_2.index)

    supplement_warn: str | None = None
    if supplement_today:
        close, pe, pb_dom, pb_2, supplement_warn = append_latest_snapshot_in_memory(sec_name, close, pe, pb_dom, pb_2)

    pb = pb_dom.combine_first(pb_2)
    close.index = pd.to_datetime(close.index)
    pe.index = pd.to_datetime(pe.index)
    pb.index = pd.to_datetime(pb.index)
    return DataBundle(sec_name=sec_name, close=close, pe=pe, pb=pb), supplement_warn


def resolve_target(bundle: DataBundle, index: Optional[str], code: Optional[str]) -> tuple[str, str]:
    index = (index or "").strip()
    code = (code or "").strip().upper()
    mapping = bundle.sec_name

    if index:
        hit = mapping[mapping["sec_name"] == index]
        if hit.empty:
            raise ValueError(f"未找到证券名称: {index}")
        return hit.iloc[0]["sec_name"], hit.iloc[0]["index_code"]

    if code:
        hit = mapping[mapping["index_code"].str.upper() == code]
        if hit.empty:
            raise ValueError(f"未找到 Wind 代码: {code}")
        return hit.iloc[0]["sec_name"], hit.iloc[0]["index_code"]

    raise ValueError("请至少输入证券名称或 Wind 代码。")


def process_index_data(
    bundle: DataBundle,
    index_name: str,
    take_log: bool = True,
    take_clip: bool = False,
    time_range: tuple[str | pd.Timestamp, str | pd.Timestamp] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = pd.DataFrame(
        {"close": bundle.close[index_name], "PE_TTM": bundle.pe[index_name], "PB_MRQ": bundle.pb[index_name]}
    )
    data = data.dropna(subset=["close", "PE_TTM", "PB_MRQ"], how="all")

    if time_range is not None:
        start_date, end_date = pd.to_datetime(time_range[0]), pd.to_datetime(time_range[1])
        data = data.loc[start_date:end_date]

    if take_clip:
        data["PE_TTM"] = data["PE_TTM"].clip(lower=0, upper=200)

    data["EPS"] = np.where(data["PE_TTM"] != 0, data["close"] / data["PE_TTM"], np.nan)
    data["ROE"] = np.where(data["PE_TTM"] != 0, 100 * (data["PB_MRQ"] / data["PE_TTM"]), np.nan)

    data_org = data.copy()
    norm_cols = ["close", "PE_TTM", "EPS"]
    norm_base = data[norm_cols].apply(
        lambda s: s.loc[s.first_valid_index()] if s.first_valid_index() is not None else np.nan
    )
    data[norm_cols] = data[norm_cols].div(norm_base)
    data["PE_TTM"] = data["PE_TTM"].fillna(value=0)

    if take_log:
        data = data.dropna()
        data = data.apply(pd.to_numeric, errors="coerce")
        data[["close", "PE_TTM", "EPS"]] = 1 + np.log(data[["close", "PE_TTM", "EPS"]].where(data > 0))
    return data, data_org


def table_pct_chg_and_latest(
    data: pd.DataFrame,
    data_org: pd.DataFrame | None = None,
    years: list[int] | None = None,
    pct_cols: list[str] | None = None,
    latest_cols: list[str] | None = None,
    round_decimals: int = 2,
    expected_earnings_growth_2026: float | None = None,
    latest_ttm_dividend_yield: float | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if years is None:
        years = [1, 3, 5]
    if pct_cols is None:
        pct_cols = ["close", "PE_TTM", "EPS"]
    if latest_cols is None:
        latest_cols = ["ROE", "PE_TTM", "PB_MRQ"]

    end_trade_day = data.index.max()
    latest_org = (data_org if data_org is not None else data).loc[end_trade_day]
    latest = data.loc[end_trade_day]

    rows = {}
    for y in years:
        start_day = data.index[-y * 51 - 1] if len(data) > y * 51 else data.index[0]
        base = data.loc[start_day]
        pct_chg = (latest - base) / base * 100
        pct_chg = pct_chg.replace([np.inf, -np.inf], None)

        if (
            "EPS" in pct_chg.index
            and pd.notna(base.get("EPS"))
            and pd.notna(latest.get("EPS"))
            and base["EPS"] < 0
            and latest["EPS"] > 0
        ):
            pct_chg["EPS"] = -pct_chg["EPS"]

        if (
            "PE_TTM" in pct_chg.index
            and pd.notna(base.get("PE_TTM"))
            and pd.notna(latest.get("PE_TTM"))
            and (base["PE_TTM"] < 0 and latest["PE_TTM"] < 0)
        ):
            pct_chg["PE_TTM"] = f"{round(float(pct_chg['PE_TTM']), 2)}, 无实际含义"

        rows[f"近{y}年涨跌幅(%)"] = pct_chg

    data_pct_chg = pd.DataFrame(rows).T[pct_cols].round(round_decimals)
    data_latest = pd.DataFrame({"最新数据": latest_org}).T[latest_cols].round(round_decimals)
    if expected_earnings_growth_2026 is not None:
        data_latest["2026年预期\n归母净利润增速(%)"] = round(expected_earnings_growth_2026, round_decimals)
    if latest_ttm_dividend_yield is not None:
        data_latest["最新股息率\n_TTM(%)"] = round(latest_ttm_dividend_yield, round_decimals)
    return data_pct_chg, data_latest


def _set_yaxis_2f(axis, decimals: int = 2) -> None:
    axis.ticklabel_format(axis="y", style="plain", useOffset=False)
    axis.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:.{decimals}f}"))


def _format_cell(val, decimals: int = 2) -> str:
    if pd.isna(val):
        return ""
    if isinstance(val, (int, float, np.integer, np.floating)):
        return f"{val:.{decimals}f}"
    return str(val)


def _text_width(text: str) -> float:
    text = str(text)
    lines = text.splitlines() or [text]
    return max(sum(2 if "\u4e00" <= ch <= "\u9fff" else 1 for ch in line) for line in lines)


def _build_full_table(df: pd.DataFrame, corner_text: str = "", decimals: int = 2) -> tuple[list, list]:
    header = [corner_text] + [str(c) for c in df.columns]
    body = [[str(idx)] + [_format_cell(v, decimals) for v in row] for idx, row in zip(df.index, df.values)]
    full = [header] + body
    raw = [[None] * len(header)] + [[None] + list(row) for row in df.values]
    return full, raw


def _calc_col_widths(full_table: list, pad: float = 0.8, min_w: float = 1.8) -> list:
    ncols = len(full_table[0])
    raw_widths = [max(max(_text_width(row[j]) for row in full_table) + pad, min_w) for j in range(ncols)]
    total = sum(raw_widths)
    return [w / total for w in raw_widths]


def _calc_table_height(nrows: int, base: float = 0.08, per_row: float = 0.115, max_h: float = 0.84) -> float:
    return min(max_h, base + nrows * per_row)


def _draw_table(
    ax,
    full_table: list,
    raw_values: list,
    bbox: list,
    font_size: int = 12,
    index_fill_color: str = "#dbeeff",
    edge_color: str = "black",
    line_w: float = 0.8,
):
    col_widths = _calc_col_widths(full_table, pad=0.2, min_w=1.0)
    tbl = ax.table(cellText=full_table, cellLoc="center", loc="center", bbox=bbox, colWidths=col_widths)
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(font_size)

    nrows, ncols = len(full_table), len(full_table[0])
    for i in range(nrows):
        for j in range(ncols):
            cell = tbl[(i, j)]
            cell.set_edgecolor(edge_color)
            cell.set_linewidth(line_w)
            txt = cell.get_text()
            txt.set_color("black")
            txt.set_weight("normal")
            txt.set_ha("center")
            if i == 0 or j == 0:
                cell.set_facecolor(index_fill_color)
                txt.set_weight("bold")
            else:
                cell.set_facecolor("white")
                txt.set_ha("right")
                val = raw_values[i][j]
                if isinstance(val, (int, float, np.integer, np.floating)) and not pd.isna(val) and val < 0:
                    txt.set_color("red")
    return tbl


_TABLE_LAYOUT = {
    "left_x": -0.04,
    "bottom_y": 0.10,
    "gap": 0.04,
    "left_w": 0.55,
    "right_w": 0.5,
    "left_shift": 0.015,
    "font_size": 10,
    "index_fill_color": "#dbeeff",
}


def plot_tables(
    ax: plt.Axes,
    data_pct_chg: pd.DataFrame,
    data_latest: pd.DataFrame,
    decimals: int = 2,
    font_size: int = None,
    index_fill_color: str = None,
) -> None:
    ax.axis("off")
    layout = _TABLE_LAYOUT
    font_size = font_size if font_size is not None else layout["font_size"]
    index_fill_color = index_fill_color or layout["index_fill_color"]

    corner1 = "" if data_pct_chg.index.name is None else str(data_pct_chg.index.name)
    corner2 = "" if data_latest.index.name is None else str(data_latest.index.name)
    full_pct, raw_pct = _build_full_table(data_pct_chg, corner_text=corner1, decimals=decimals)
    full_latest, raw_latest = _build_full_table(data_latest, corner_text=corner2, decimals=decimals)

    left_x = layout["left_x"]
    right_x = left_x + layout["left_w"] + layout["gap"]
    bottom_y = layout["bottom_y"]
    left_h = _calc_table_height(len(full_pct))
    right_h = _calc_table_height(len(full_latest))

    _draw_table(
        ax,
        full_pct,
        raw_pct,
        bbox=[left_x, bottom_y, layout["left_w"], left_h],
        font_size=font_size,
        index_fill_color=index_fill_color,
    )

    right_bottom_y = bottom_y + left_h - right_h
    _draw_table(
        ax,
        full_latest,
        raw_latest,
        bbox=[right_x, right_bottom_y, layout["right_w"], right_h],
        font_size=font_size,
        index_fill_color=index_fill_color,
    )

    note_text = " 注释: \n 1、当 EPS 由负转正时, 涨跌幅计算取绝对值; 由正转负时, 保持原值。\n 当 PE_TTM 存在负数时,涨跌幅无实际含义。\n 2、每1年按照滚动51周近似。"
    ax.text(right_x, bottom_y + 0.14, note_text, ha="left", va="top", fontsize=font_size, color="#000000", transform=ax.transAxes)


def plot_pe_eps_roe(
    data: pd.DataFrame,
    take_log: bool = False,
    title_close: str = "收盘价",
    title_pe: str = "市盈率TTM",
    title_EPS: str = "每股收益EPS",
    pe_on_left_axis: bool = False,
    ax: plt.Axes = None,
    data_org: pd.DataFrame = None,
) -> None:
    if take_log:
        title_close += " (对数化)"
        title_pe += " (对数化)"
        title_EPS += " (对数化)"

    if ax is None:
        _, ax1 = plt.subplots(figsize=(12, 6))
    else:
        ax1 = ax

    l1 = ax1.plot(data.index, data["close"], label=title_close + "(左2轴)", color=COLOR[1], linewidth=2)

    ax_pe = None
    if pe_on_left_axis:
        label_text = "收盘价与每股收益EPS的归一化取值"
        label_text_newline = "\n".join(label_text)
        ax1.set_ylabel(label_text_newline, color="black", rotation=0, va="center", ha="center", labelpad=8)

        ax_pe = ax1.twinx()
        ax_pe.spines["left"].set_position(("outward", 55))
        ax_pe.spines["left"].set_visible(True)
        ax_pe.spines["right"].set_visible(False)
        ax_pe.yaxis.set_label_position("left")
        ax_pe.yaxis.set_ticks_position("left")
        ax_pe.patch.set_visible(False)

        pe_data = data_org["PE_TTM"] if data_org is not None else data["PE_TTM"]
        l2 = ax_pe.plot(data.index, pe_data, label=title_pe + "(左1轴)", color=COLOR[4], linewidth=2)
        ax_pe.tick_params(axis="y", labelcolor="black", left=True, right=False)
        title_pe_newline = "\n".join(title_pe)
        ax_pe.set_ylabel(title_pe_newline, color="black", rotation=0, va="center", ha="center", labelpad=8)
    else:
        l2 = ax1.plot(data.index, data["PE_TTM"], label=title_pe, color=COLOR[4], linewidth=2)

    l3 = ax1.plot(data.index, data["EPS"], label=title_EPS + "(左2轴)", color=COLOR[3], linewidth=2)

    ymin, ymax = ax1.get_ylim()
    yticks = np.asarray(ax1.get_yticks(), dtype=float)
    if ymin <= 1.0 <= ymax and (yticks.size == 0 or not np.isclose(yticks, 1.0).any()):
        ax1.set_yticks(np.sort(np.r_[yticks, 1.0]))

    start_year = data.index.min().year
    ax1.set_xlim(pd.Timestamp(f"{start_year}-01-01"), data.index.max())
    ax1.xaxis.set_major_locator(mdates.YearLocator(1))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax1.grid(True, linestyle="--", alpha=0.3)

    ax2 = ax1.twinx()
    l4 = ax2.plot(data.index, data["ROE"], label="ROE(右轴, %)", color=COLOR[0], linewidth=2)

    if pe_on_left_axis:
        label_text_newline = "\n".join("净资产收益率ROE")
        ax2.set_ylabel(label_text_newline, color="black", rotation=0, va="center", ha="center", labelpad=10)

    _set_yaxis_2f(ax1)
    _set_yaxis_2f(ax2)
    if ax_pe is not None:
        _set_yaxis_2f(ax_pe)

    lines = l1 + l2 + l3 + l4
    labels = [line.get_label() for line in lines]
    ax1.legend(lines, labels, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=len(labels), frameon=True, edgecolor="black")

    title_text = "恒等式: Price = Earnings * PE , 截至: " + data.index.max().strftime("%Y-%m-%d")
    ax1.set_title(title_text, fontsize=14)


def make_matplotlib_figure(index_name: str, code: str, data: pd.DataFrame, data_org: pd.DataFrame, data_pct_chg: pd.DataFrame, data_latest: pd.DataFrame):
    fig = plt.figure(figsize=(14, 10))
    gs = fig.add_gridspec(2, 1, height_ratios=[2, 1], hspace=0.04)
    ax_chart = fig.add_subplot(gs[0])
    ax_table = fig.add_subplot(gs[1])

    plot_pe_eps_roe(
        data,
        take_log=False,
        title_close=f"收盘价_{index_name}_{code}",
        pe_on_left_axis=True,
        ax=ax_chart,
        data_org=data_org[data_org.index.isin(data.index)],
    )
    data_pct_chg.index.name = f"{index_name}_{code}"
    data_latest.index.name = ""
    plot_tables(ax_table, data_pct_chg, data_latest)

    fig.text(0.10, 0.10, "数据来源：Wind", ha="right", va="bottom", fontsize=10, color="black")
    fig.tight_layout(h_pad=0.2)
    return fig


def make_interactive_line_figure(
    data: pd.DataFrame,
    data_org: pd.DataFrame,
    title_close: str = "收盘价",
    title_pe: str = "市盈率TTM",
    title_EPS: str = "每股收益EPS",
    legend_close_label: str | None = None,
    hover_close_label: str = "收盘价(左2轴)",
) -> go.Figure:
    def _stack_text(text: str) -> str:
        chars = [ch for ch in str(text).replace(" ", "") if ch != "\n"]
        return "<br>".join(chars)

    legend_close_label = legend_close_label if legend_close_label is not None else title_close

    fig = go.Figure()
    pe_series = data_org["PE_TTM"] if data_org is not None else data["PE_TTM"]

    # 透明首条 trace：统一 hover 时日期独占最上方，不跟在收盘价后
    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data["close"],
            mode="lines",
            line=dict(width=0),
            opacity=0,
            showlegend=False,
            name="_hover_date",
            yaxis="y",
            hovertemplate="日期: %{x|%Y-%m-%d}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data["close"],
            mode="lines",
            line=dict(color=COLOR[1], width=2),
            name=legend_close_label + "(左2轴)",
            yaxis="y",
            hovertemplate=hover_close_label + ": %{y:.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=pe_series,
            mode="lines",
            line=dict(color=COLOR[4], width=2),
            name=title_pe + "(左1轴)",
            yaxis="y3",
            hovertemplate=title_pe + "(左1轴): %{y:.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data["EPS"],
            mode="lines",
            line=dict(color=COLOR[3], width=2),
            name=title_EPS + "(左2轴)",
            yaxis="y",
            hovertemplate=title_EPS + "(左2轴): %{y:.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data["ROE"],
            mode="lines",
            line=dict(color=COLOR[0], width=2),
            name="ROE(右轴, %)",
            yaxis="y2",
            hovertemplate="ROE(右轴, %): %{y:.2f}<extra></extra>",
        )
    )

    start_year = data.index.min().year
    x_start = pd.Timestamp(f"{start_year}-01-01")
    x_end = data.index.max()
    fig.update_layout(
        title="恒等式: Price = Earnings * PE , 截至: " + data.index.max().strftime("%Y-%m-%d"),
        title_x=0.5,
        title_xanchor="center",
        xaxis_title="日期",
        hovermode="x unified",
        margin=dict(l=170, r=120, t=80, b=165),
        xaxis=dict(
            domain=[0.12, 0.88],
            range=[x_start, x_end],
            tickformat="%Y",
            dtick="M12",
            tickangle=0,
            automargin=True,
            showgrid=True,
            gridcolor="rgba(0,0,0,0.15)",
        ),
        yaxis=dict(
            title="",
            tickformat=".2f",
            automargin=True,
            title_standoff=20,
            showgrid=True,
            gridcolor="rgba(0,0,0,0.15)",
        ),
        yaxis2=dict(
            title="",
            overlaying="y",
            side="right",
            tickformat=".2f",
            automargin=True,
            title_standoff=18,
        ),
        yaxis3=dict(
            title="",
            overlaying="y",
            side="left",
            anchor="free",
            position=0.045,
            tickformat=".2f",
            automargin=True,
            title_standoff=8,
        ),
        legend=dict(orientation="h", yanchor="top", y=-0.22, xanchor="center", x=0.5),
    )
    fig.add_annotation(
        x=0.075,
        y=0.5,
        xref="paper",
        yref="paper",
        text=_stack_text("收盘价与每股收益EPS的归一化取值"),
        showarrow=False,
        textangle=0,
        xanchor="center",
        yanchor="middle",
        align="center",
        font=dict(size=12, color="black"),
    )
    fig.add_annotation(
        x=-0.01,
        y=0.5,
        xref="paper",
        yref="paper",
        text=_stack_text(title_pe),
        showarrow=False,
        textangle=0,
        xanchor="center",
        yanchor="middle",
        align="center",
        font=dict(size=12, color="black"),
    )
    fig.add_annotation(
        x=0.98,
        y=0.5,
        xref="paper",
        yref="paper",
        text=_stack_text("净资产收益率ROE"),
        showarrow=False,
        textangle=0,
        xanchor="center",
        yanchor="middle",
        align="center",
        font=dict(size=12, color="black"),
    )
    return fig


def build_line_points_export(data: pd.DataFrame, data_org: pd.DataFrame) -> pd.DataFrame:
    org = data_org.reindex(data.index)
    close = org["close"]
    pe = org["PE_TTM"]
    pb = org["PB_MRQ"]
    eps = np.where(pe != 0, close / pe, np.nan)
    roe = np.where(pe != 0, 100 * (pb / pe), np.nan)
    out = pd.DataFrame({"close": close, "PE_TTM": pe, "PB_MRQ": pb, "EPS": eps, "ROE": roe}, index=data.index)
    out = out[~out.index.duplicated(keep="last")]
    out = out.sort_index(ascending=False)
    out.index = pd.to_datetime(out.index).strftime("%Y-%m-%d")
    out.index.name = "日期"
    return out


def _last_valid_number(series: list | None) -> float | None:
    if not series:
        return None
    for val in reversed(series):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    return None


def _wsd_series_from_response(res: object) -> list | None:
    err = getattr(res, "ErrorCode", None)
    if err not in (None, 0):
        return None
    data = getattr(res, "Data", None)
    if data is None or (isinstance(data, list) and len(data) == 0):
        return None
    first = data[0]
    if first is None:
        return None
    if isinstance(first, (list, tuple)) or (hasattr(first, "__iter__") and not isinstance(first, (str, bytes))):
        return list(first)
    return [first]


def try_fetch_optional_metrics(index_code: str) -> tuple[float | None, float | None, str | None]:
    today = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - pd.Timedelta(days=15)).strftime("%Y-%m-%d")
    try:
        res_eg = w.wsd(index_code, "west_avgnp_yoy", start, today, "")
        res_dy = w.wsd(index_code, "dividendyield2", start, today, "")
        eg_err = getattr(res_eg, "ErrorCode", None)
        dy_err = getattr(res_dy, "ErrorCode", None)
        eg_vals = _wsd_series_from_response(res_eg)
        dy_vals = _wsd_series_from_response(res_dy)
        expected_earnings_growth_2026 = _last_valid_number(eg_vals)
        latest_ttm_dividend_yield = _last_valid_number(dy_vals)
        if expected_earnings_growth_2026 is None and latest_ttm_dividend_yield is None:
            parts = []
            if eg_err not in (None, 0):
                parts.append(f"west_avgnp_yoy ErrorCode={eg_err}")
            elif eg_vals is None:
                parts.append("west_avgnp_yoy 返回 Data 为空或不可用")
            elif _last_valid_number(eg_vals) is None:
                parts.append("west_avgnp_yoy 序列无有效数值")
            if dy_err not in (None, 0):
                parts.append(f"dividendyield2 ErrorCode={dy_err}")
            elif dy_vals is None:
                parts.append("dividendyield2 返回 Data 为空或不可用")
            elif _last_valid_number(dy_vals) is None:
                parts.append("dividendyield2 序列无有效数值")
            detail = "；".join(parts) if parts else "west_avgnp_yoy / dividendyield2 均无有效值"
            return None, None, "Wind 扩展指标无有效返回值（" + detail + "）。"
        if expected_earnings_growth_2026 is None or latest_ttm_dividend_yield is None:
            missing = []
            if expected_earnings_growth_2026 is None:
                if eg_err not in (None, 0):
                    missing.append(f"west_avgnp_yoy(ErrorCode={eg_err})")
                elif eg_vals is None:
                    missing.append("west_avgnp_yoy(Data 为空)")
                else:
                    missing.append("west_avgnp_yoy(无有效数值)")
            if latest_ttm_dividend_yield is None:
                if dy_err not in (None, 0):
                    missing.append(f"dividendyield2(ErrorCode={dy_err})")
                elif dy_vals is None:
                    missing.append("dividendyield2(Data 为空)")
                else:
                    missing.append("dividendyield2(无有效数值)")
            return expected_earnings_growth_2026, latest_ttm_dividend_yield, (
                "Wind 扩展指标部分无有效值: " + "、".join(missing)
            )
        return expected_earnings_growth_2026, latest_ttm_dividend_yield, None
    except Exception as exc:  # noqa: BLE001
        return None, None, f"Wind 扩展指标获取失败: {exc}"
