"""
Alpha因子批量回测主入口 - run_backtest.py
==========================================

功能：
  - 批量回测 Alpha 因子库中的所有因子
  - 输出 JSON 格式详细结果数据
  - 输出 Markdown 格式分析报告
  - 按 Fitness / 夏普 / ICIR 等指标排序

用法：
  python run_backtest.py [result_mode] [n_stocks] [n_days] [categories]

参数：
  result_mode: 结果模式，display_only / notify / auto (默认 display_only)
  n_stocks: 模拟股票数量 (默认 50)
  n_days: 模拟交易日数量 (默认 500)
  categories: 因子类别，逗号分隔，如 "量价因子,动量反转因子" (默认全部)
"""

import asyncio
import sys
import os
import json
import time
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# 确保同目录模块可导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from codeact_sdk import CodeActSDK
from alpha_library import FACTOR_LIBRARY, AlphaLibrary
from factor_backtest import DataLoader, FactorEngine, BacktestEngine, PerformanceAnalyzer


# ============================================================
# 工具函数
# ============================================================

def _fmt_pct(value: float, digits: int = 2) -> str:
    """格式化百分比"""
    return f"{value * 100:.{digits}f}%"


def _fmt_num(value: float, digits: int = 3) -> str:
    """格式化数值"""
    return f"{value:.{digits}f}"


def run_batch_backtest(n_stocks: int = 50, n_days: int = 500,
                       categories: Optional[List[str]] = None,
                       use_real_data: bool = False,
                       forward_shift: int = 1,
                       n_groups: int = 10,
                       top_pct: float = 0.1,
                       bottom_pct: float = 0.1) -> Dict:
    """
    批量回测所有因子

    Returns:
        Dict with:
          - summary: 汇总表（DataFrame格式的dict）
          - details: 每个因子的详细结果
          - meta: 元信息（时间、参数等）
    """
    # 1. 加载数据
    print(f"[1/4] 加载数据: {n_stocks}只股票, {n_days}个交易日...")
    t0 = time.time()
    loader = DataLoader(n_stocks=n_stocks, n_days=n_days)
    data = loader.load(use_real_data=use_real_data)
    print(f"  数据维度: {data['close'].shape}, 耗时 {time.time()-t0:.1f}s")

    # 2. 确定因子列表
    factor_names = FACTOR_LIBRARY.list_factors()
    if categories:
        factor_names = [n for n in factor_names
                        if FACTOR_LIBRARY.get(n).category in categories]
    print(f"[2/4] 待回测因子数: {len(factor_names)}")

    # 3. 批量回测
    print("[3/4] 批量回测中...")
    all_results = {}
    forward_returns = data['returns'].shift(-forward_shift)

    for i, name in enumerate(factor_names, 1):
        t1 = time.time()
        try:
            # 计算因子
            engine = FactorEngine(data)
            factor = engine.get_clean_factor(name)

            # 回测
            bt = BacktestEngine(factor, forward_returns,
                                n_groups=n_groups,
                                top_pct=top_pct, bottom_pct=bottom_pct)
            result = bt.run()

            # 评估
            analyzer = PerformanceAnalyzer(result, factor, forward_returns)
            metrics = analyzer.evaluate()

            # 添加因子信息
            info = FACTOR_LIBRARY.factor_info(name)

            all_results[name] = {
                'factor_info': info,
                'metrics': _serialize_metrics(metrics),
            }

            elapsed = time.time() - t1
            print(f"  [{i}/{len(factor_names)}] {name:<20s} "
                  f"Fitness={metrics['fitness']:.3f} "
                  f"Sharpe={metrics['sharpe_ratio']:.3f} "
                  f"IC={metrics['ic_mean']:.4f} "
                  f"({elapsed:.1f}s)")
        except Exception as e:
            print(f"  [{i}/{len(factor_names)}] {name}: 失败 - {e}")
            all_results[name] = {
                'factor_info': {'name': name,
                                'category': FACTOR_LIBRARY.get(name).category
                                if name in FACTOR_LIBRARY.list_factors() else 'Unknown',
                                'description': '', 'formula': ''},
                'metrics': None,
                'error': str(e),
            }

    # 4. 生成汇总
    print("[4/4] 生成汇总表...")
    summary = build_summary_table(all_results)

    return {
        'meta': {
            'timestamp': datetime.now().isoformat(),
            'n_stocks': n_stocks,
            'n_days': n_days,
            'use_real_data': use_real_data,
            'forward_shift': forward_shift,
            'n_groups': n_groups,
            'top_pct': top_pct,
            'bottom_pct': bottom_pct,
            'total_factors': len(factor_names),
            'successful_factors': sum(1 for r in all_results.values() if r['metrics'] is not None),
        },
        'summary': summary,
        'details': all_results,
    }


def _serialize_metrics(metrics: Dict) -> Dict:
    """将metrics中的DataFrame/Series/Timestamp转为可JSON序列化格式"""

    def _convert(obj):
        """递归转换不可序列化的类型"""
        if isinstance(obj, dict):
            return {str(k) if hasattr(k, 'isoformat') else k: _convert(v)
                    for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_convert(v) for v in obj]
        elif isinstance(obj, (pd.Timestamp, np.datetime64)):
            return str(obj)
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif pd.isna(obj) if isinstance(obj, (float, np.floating)) else False:
            return None
        else:
            return obj

    return _convert(metrics)


def build_summary_table(all_results: Dict) -> List[Dict]:
    """构建汇总表（按Fitness降序）"""
    rows = []
    for name, result in all_results.items():
        m = result['metrics']
        info = result['factor_info']
        if m is None:
            rows.append({
                'factor': name,
                'category': info.get('category', 'Unknown'),
                'fitness': None,
                'sharpe_ratio': None,
                'annual_return': None,
                'max_drawdown': None,
                'daily_turnover': None,
                'ic_mean': None,
                'rank_ic_mean': None,
                'ic_ir_annual': None,
                'rank_ic_ir_annual': None,
                'status': 'failed',
            })
        else:
            rows.append({
                'factor': name,
                'category': info.get('category', 'Unknown'),
                'fitness': m.get('fitness', 0),
                'sharpe_ratio': m.get('sharpe_ratio', 0),
                'annual_return': m.get('annual_return', 0),
                'max_drawdown': m.get('max_drawdown', 0),
                'daily_turnover': m.get('daily_turnover', 0),
                'annual_turnover': m.get('annual_turnover', 0),
                'ic_mean': m.get('ic_mean', 0),
                'rank_ic_mean': m.get('rank_ic_mean', 0),
                'ic_ir_annual': m.get('ic_ir_annual', 0),
                'rank_ic_ir_annual': m.get('rank_ic_ir_annual', 0),
                'win_rate': m.get('stats', {}).get('win_rate', 0),
                'status': 'success',
            })

    # 按 Fitness 降序排列
    rows.sort(key=lambda x: x['fitness'] if x['fitness'] is not None else -999, reverse=True)
    return rows


# ============================================================
# 报告生成
# ============================================================

def generate_markdown_report(result: Dict) -> str:
    """生成 Markdown 格式报告"""
    meta = result['meta']
    summary = result['summary']
    details = result['details']

    lines = []

    # 标题
    lines.append("# Alpha 因子回测报告")
    lines.append("")
    lines.append(f"> 生成时间: {meta['timestamp']}")
    lines.append(f"> 股票数量: {meta['n_stocks']} | 交易日数: {meta['n_days']} "
                 f"| 因子总数: {meta['total_factors']} | 成功: {meta['successful_factors']}")
    lines.append(f"> 数据源: {'真实数据(akshare)' if meta['use_real_data'] else '模拟数据(MBP)'}")
    lines.append("")

    # 核心结论
    top5 = [r for r in summary if r['status'] == 'success'][:5]
    lines.append("## 📊 核心结论")
    lines.append("")
    if top5:
        lines.append(f"本次回测了 {meta['successful_factors']} 个因子，按 Fitness 评分排名前 5 的因子如下：")
        lines.append("")
        for i, r in enumerate(top5, 1):
            lines.append(f"{i}. **{r['factor']}** ({r['category']}): "
                         f"Fitness={r['fitness']:.3f}, "
                         f"Sharpe={r['sharpe_ratio']:.3f}, "
                         f"IC={r['ic_mean']:.4f}")
        lines.append("")
    else:
        lines.append("⚠️ 没有成功回测的因子。")
        lines.append("")

    # 完整排行榜
    lines.append("## 🏆 因子排行榜（按 Fitness 降序）")
    lines.append("")

    # 表头
    header = "| 排名 | 因子名称 | 类别 | Fitness | 夏普 | 年化收益 | 最大回撤 | 日换手 | IC | Rank IC | 年化ICIR |"
    sep = "|---|---|---|---|---|---|---|---|---|---|---|"
    lines.append(header)
    lines.append(sep)

    for i, r in enumerate(summary, 1):
        if r['status'] == 'failed':
            lines.append(f"| {i} | {r['factor']} | {r['category']} | - | - | - | - | - | - | - | - |")
        else:
            lines.append(
                f"| {i} "
                f"| **{r['factor']}** "
                f"| {r['category']} "
                f"| {r['fitness']:.3f} "
                f"| {r['sharpe_ratio']:.3f} "
                f"| {_fmt_pct(r['annual_return'])} "
                f"| {_fmt_pct(r['max_drawdown'])} "
                f"| {_fmt_pct(r['daily_turnover'])} "
                f"| {r['ic_mean']:.4f} "
                f"| {r['rank_ic_mean']:.4f} "
                f"| {r['ic_ir_annual']:.3f} |"
            )
    lines.append("")

    # 分类统计
    lines.append("## 📈 分类统计")
    lines.append("")
    categories = sorted(set(r['category'] for r in summary if r['status'] == 'success'))
    for cat in categories:
        cat_factors = [r for r in summary if r['category'] == cat and r['status'] == 'success']
        if not cat_factors:
            continue
        avg_fitness = np.mean([r['fitness'] for r in cat_factors])
        avg_sharpe = np.mean([r['sharpe_ratio'] for r in cat_factors])
        avg_ic = np.mean([r['ic_mean'] for r in cat_factors])
        best = max(cat_factors, key=lambda x: x['fitness'])

        lines.append(f"### {cat} ({len(cat_factors)}个因子)")
        lines.append("")
        lines.append(f"- 平均 Fitness: **{avg_fitness:.3f}**")
        lines.append(f"- 平均 Sharpe: {avg_sharpe:.3f}")
        lines.append(f"- 平均 IC: {avg_ic:.4f}")
        lines.append(f"- 最佳因子: **{best['factor']}** (Fitness={best['fitness']:.3f})")
        lines.append("")

    # 指标说明
    lines.append("## 📖 指标说明")
    lines.append("")
    lines.append("| 指标 | 含义 | 评价标准 |")
    lines.append("|---|---|---|")
    lines.append("| **Fitness** | 综合评分 = Sharpe × √|Returns| / max(Turnover, 0.125) | ≥ 1.0 为优秀 |")
    lines.append("| **Sharpe** | 夏普比率 = (年化收益 - 无风险利率) / 年化波动率 | ≥ 1.25 为优秀 |")
    lines.append("| **年化收益** | 多空组合的年化复合收益率 | 越高越好 |")
    lines.append("| **最大回撤** | 净值从峰值到谷底的最大跌幅 | 越小越好，< 20% 为可接受 |")
    lines.append("| **日换手率** | 每日调仓比例 | 1%~70% 为合理区间 |")
    lines.append("| **IC** | 信息系数 = 因子值与未来收益的相关系数 | > 0.05 有信息含量 |")
    lines.append("| **Rank IC** | 秩信息系数 = 因子排名与收益排名的相关系数 | > 0.05 有信息含量 |")
    lines.append("| **年化ICIR** | IC的均值/标准差 × √252 | > 2.0 为稳定有效 |")
    lines.append("")

    # 各因子详情
    lines.append("## 📋 因子详情")
    lines.append("")
    for r in summary:
        if r['status'] == 'failed':
            continue
        name = r['factor']
        info = details[name]['factor_info']
        m = details[name]['metrics']

        lines.append(f"### {name} ({r['category']})")
        lines.append("")
        lines.append(f"**公式**: `{info['formula']}`")
        lines.append("")
        lines.append(f"**说明**: {info['description']}")
        lines.append("")
        lines.append("| 指标 | 值 |")
        lines.append("|---|---|")
        lines.append(f"| Fitness | **{m['fitness']:.3f}** |")
        lines.append(f"| 夏普比率 | {m['sharpe_ratio']:.3f} |")
        lines.append(f"| 年化收益 | {_fmt_pct(m['annual_return'])} |")
        lines.append(f"| 最大回撤 | {_fmt_pct(m['max_drawdown'])} |")
        lines.append(f"| 日换手率 | {_fmt_pct(m['daily_turnover'])} |")
        lines.append(f"| 年化换手率 | {_fmt_pct(m['annual_turnover'])} |")
        lines.append(f"| IC均值 | {m['ic_mean']:.4f} |")
        lines.append(f"| Rank IC均值 | {m['rank_ic_mean']:.4f} |")
        lines.append(f"| 年化ICIR | {m['ic_ir_annual']:.3f} |")
        lines.append(f"| 年化Rank ICIR | {m['rank_ic_ir_annual']:.3f} |")
        lines.append(f"| 日胜率 | {_fmt_pct(m['stats']['win_rate'])} |")
        lines.append("")

        # 分组收益（单调性）
        if m.get('group_annual_returns'):
            lines.append("**分组年化收益（1=最低因子值，10=最高因子值）**:")
            lines.append("")
            group_str = " | ".join(
                f"G{k.split('_')[1]}: {_fmt_pct(v)}"
                for k, v in sorted(m['group_annual_returns'].items(),
                                   key=lambda x: int(x[0].split('_')[1]))
            )
            lines.append(group_str)
            lines.append("")

    # 附录：框架说明
    lines.append("---")
    lines.append("")
    lines.append("## 🔧 回测框架说明")
    lines.append("")
    lines.append("本框架对标 WorldQuant BRAIN 平台的 Alpha 因子研究范式：")
    lines.append("")
    lines.append("1. **因子库**: `alpha_library.py` - 27个经典因子，覆盖5大类别")
    lines.append("2. **数据层**: `DataLoader` - 支持模拟数据和 akshare 真实数据")
    lines.append("3. **因子预处理**: MAD去极值 + Z-score标准化")
    lines.append("4. **回测方法**: 分位数多空组合（Top 10% - Bottom 10%），每日调仓，等权配置")
    lines.append("5. **评估指标**: 8大核心指标 + 分层收益检验")
    lines.append("6. **Fitness公式**: `Sharpe × sqrt(|Returns|) / max(Turnover, 0.125)`")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# 主函数
# ============================================================

async def main():
    # 解析参数
    result_mode = sys.argv[1] if len(sys.argv) > 1 else "display_only"
    n_stocks = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    n_days = int(sys.argv[3]) if len(sys.argv) > 3 else 500
    categories_arg = sys.argv[4] if len(sys.argv) > 4 else ""
    use_real = sys.argv[5].lower() == 'true' if len(sys.argv) > 5 else False

    print(f"[参数] result_mode={result_mode}, n_stocks={n_stocks}, "
          f"n_days={n_days}, categories={categories_arg or '全部'}, "
          f"use_real={use_real}")

    sdk = CodeActSDK()

    try:
        # 解析因子类别
        categories = None
        if categories_arg:
            categories = [c.strip() for c in categories_arg.split(',') if c.strip()]

        # 运行批量回测
        result = run_batch_backtest(
            n_stocks=n_stocks,
            n_days=n_days,
            categories=categories,
            use_real_data=use_real,
        )

        # 生成报告
        report_md = generate_markdown_report(result)

        # 保存结果
        os.makedirs("./codeact/output", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # JSON 结果
        json_path = f"./codeact/output/backtest_result_{timestamp}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)

        # Markdown 报告
        md_path = f"./codeact/output/backtest_report_{timestamp}.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(report_md)

        print(f"\n✅ 回测完成！")
        print(f"  JSON结果: {json_path}")
        print(f"  Markdown报告: {md_path}")

        # 准备提交结果
        actual_mode = result_mode if result_mode != "auto" else "display_only"

        # 构建用户摘要消息
        summary = result['summary']
        success_count = result['meta']['successful_factors']
        top3 = [r for r in summary if r['status'] == 'success'][:3]

        summary_lines = [
            f"📊 Alpha因子回测完成 ({success_count}/{result['meta']['total_factors']}个成功)",
            f"   数据: {n_stocks}只股票 × {n_days}交易日 "
            f"({'真实数据' if use_real else '模拟数据'})",
            "",
            "🏆 Top 3 因子 (按Fitness):",
        ]
        for i, r in enumerate(top3, 1):
            summary_lines.append(
                f"   {i}. {r['factor']} ({r['category']}): "
                f"Fitness={r['fitness']:.3f}, "
                f"Sharpe={r['sharpe_ratio']:.3f}, "
                f"IC={r['ic_mean']:.4f}"
            )

        summary_lines.extend([
            "",
            f"📄 详细报告: [Markdown报告](computer://{os.path.abspath(md_path)})",
            f"📊 原始数据: [JSON结果](computer://{os.path.abspath(json_path)})",
        ])

        message = "\n".join(summary_lines)

        await sdk.submit_result(
            result_mode=actual_mode,
            status="success",
            message=message,
            data={
                "report_path": md_path,
                "json_path": json_path,
                "total_factors": result['meta']['total_factors'],
                "successful_factors": success_count,
                "top_factors": [r['factor'] for r in top3],
            },
        )

    except Exception as e:
        import traceback
        print(f"❌ 执行失败: {e}")
        traceback.print_exc()
        await sdk.submit_result(
            result_mode="notify",
            status="error",
            message=f"因子回测执行失败: {str(e)}",
            data={"error_type": type(e).__name__},
        )


if __name__ == "__main__":
    asyncio.run(main())
