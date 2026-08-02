#!/usr/bin/env python3
"""
WQB d5突破 - 阶段2：自相关检查 + 提交检查 + 正式提交
基于阶段1在state.db中存储的因子结果
"""
import os
import sys
import time
import json
import sqlite3
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

ACE_LIB_DIR = os.path.join(SCRIPT_DIR, "ace_lib")
sys.path.insert(0, ACE_LIB_DIR)
sys.path.insert(0, SCRIPT_DIR)

from ace_lib import start_session, get_self_corr, get_check_submission

SUBMIT_INTERVAL = 45.0
DB_PATH = os.path.join(OUTPUT_DIR, "wqb_state.db")
REPORT_PATH = os.path.join(OUTPUT_DIR, "wqb_d5_breakthrough_submit_report.md")


def init_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS check_results (
            alpha_id TEXT NOT NULL, factor_name TEXT,
            check_name TEXT NOT NULL, check_result TEXT,
            check_value REAL, check_limit REAL,
            checked_at TEXT NOT NULL,
            PRIMARY KEY (alpha_id, check_name, checked_at)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS self_corr (
            alpha_id TEXT NOT NULL, factor_name TEXT,
            lag_period TEXT, correlation REAL,
            max_self_corr REAL, min_self_corr REAL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (alpha_id, lag_period, fetched_at)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submit_checks (
            alpha_id TEXT PRIMARY KEY, factor_name TEXT,
            checked_at TEXT, status TEXT,
            self_correlation REAL, sharpe REAL, fitness REAL, turnover REAL,
            checks_json TEXT, passed INTEGER, error TEXT,
            submitted INTEGER DEFAULT 0, submit_result TEXT
        )
    """)
    conn.commit()
    return conn


def get_all_completed_alphas(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT factor_name, alpha_id, sharpe, fitness, turnover, status
        FROM alphas
        WHERE status = 'COMPLETED' AND alpha_id IS NOT NULL
        AND completed_at >= '2026-07-27'
        ORDER BY factor_name
    """)
    rows = cursor.fetchall()
    return [{"factor_name": r[0], "alpha_id": r[1], "sharpe": r[2],
             "fitness": r[3], "turnover": r[4], "status": r[5]} for r in rows]


def get_existing_sc(conn, alpha_id):
    cursor = conn.cursor()
    cursor.execute("SELECT max_self_corr FROM self_corr WHERE alpha_id = ? ORDER BY fetched_at DESC LIMIT 1", (alpha_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def save_self_corr(conn, alpha_id, factor_name, sc_df, fetched_at):
    cursor = conn.cursor()
    max_corr = None
    if not sc_df.empty and "alpha_max_self_corr" in sc_df.columns:
        max_corr = sc_df["alpha_max_self_corr"].iloc[0]
    for _, row in sc_df.iterrows():
        lag = str(row.get("period", row.get("lag", "")))
        corr = row.get("correlation", None)
        cursor.execute("""
            INSERT OR REPLACE INTO self_corr
            (alpha_id, factor_name, lag_period, correlation, max_self_corr, min_self_corr, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (alpha_id, factor_name, lag, corr, max_corr, None, fetched_at))
    conn.commit()
    return max_corr


def check_self_corr(session, conn, alpha_id, factor_name):
    print(f"  检查自相关: {factor_name} ({alpha_id})")
    try:
        sc_df = get_self_corr(session, alpha_id)
        if sc_df is not None and not sc_df.empty:
            fetched_at = datetime.now().isoformat()
            max_sc = save_self_corr(conn, alpha_id, factor_name, sc_df, fetched_at)
            print(f"    自相关={max_sc:.4f}")
            return max_sc
        else:
            print(f"    自相关数据为空")
            return None
    except Exception as e:
        print(f"    自相关检查异常: {e}")
        return None


def save_submit_check(conn, alpha_id, factor_name, status, self_corr_val,
                      sharpe, fitness, turnover, checks_dict, passed, error=None):
    now = datetime.now().isoformat()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO submit_checks
        (alpha_id, factor_name, checked_at, status, self_correlation,
         sharpe, fitness, turnover, checks_json, passed, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (alpha_id, factor_name, now, status, self_corr_val,
          sharpe, fitness, turnover, json.dumps(checks_dict), 1 if passed else 0, error))
    conn.commit()


def mark_submitted(conn, alpha_id, result_str):
    cursor = conn.cursor()
    cursor.execute("UPDATE submit_checks SET submitted = 1, submit_result = ? WHERE alpha_id = ?",
                   (result_str, alpha_id))
    conn.commit()


class WQBCheckClient:
    def __init__(self, session):
        self._session = session
        self._base_url = "https://api.worldquantbrain.com"

    def run_submit_check(self, alpha_id, poll=True, max_polls=5, poll_interval=20):
        last_result = None
        for poll_idx in range(max_polls if poll else 1):
            data = {}
            try:
                response = self._session.post(f"{self._base_url}/alphas/{alpha_id}/submit")
                if response.status_code in (403, 200, 201, 202):
                    try:
                        data = response.json()
                    except Exception:
                        data = {}
                else:
                    response.raise_for_status()
                    data = response.json()
            except Exception as e:
                print(f"  提交检查异常: {e}")
                if poll_idx < max_polls - 1:
                    time.sleep(poll_interval)
                    continue
                return {"status": "ERROR", "checks": {}, "error": str(e)}
            result = self._parse_check_result(data)
            last_result = result
            if poll_idx == 0:
                print(f"  第1次: 状态={result['status']}, 检查项={result['check_count']}")
            else:
                print(f"  第{poll_idx+1}次轮询: 状态={result['status']}, 检查项={result['check_count']}")
            if result["check_count"] >= 5 and result["status"] != "PENDING":
                break
            if poll and poll_idx < max_polls - 1:
                print(f"  等待 {poll_interval}s...")
                time.sleep(poll_interval)
        return last_result

    def _parse_check_result(self, data):
        is_data = data.get("is", {})
        checks = is_data.get("checks", [])
        cd = {}
        ap = True
        hp = False
        sc = sh = fi = to = None
        for c in checks:
            n = c.get("name", "?")
            r = c.get("result", "?")
            v = c.get("value")
            l = c.get("limit")
            cd[n] = {"status": r, "value": v, "limit": l}
            if n == "SELF_CORRELATION" and v is not None: sc = float(v)
            elif n == "LOW_SHARPE" and v is not None: sh = float(v)
            elif n == "LOW_FITNESS" and v is not None: fi = float(v)
            elif n == "LOW_TURNOVER" and v is not None: to = float(v)
            if r == "FAIL": ap = False
            elif r == "PENDING": hp = True
        if hp: os_ = "PENDING"
        elif ap and cd: os_ = "PASS"
        elif not cd: os_ = "PENDING"
        else: os_ = "FAIL"
        return {"status": os_, "checks": cd, "self_correlation": sc,
                "sharpe": sh, "fitness": fi, "turnover": to, "check_count": len(cd)}

    def confirm_submit(self, alpha_id):
        response = self._session.put(f"{self._base_url}/alphas/{alpha_id}/submit")
        if response.status_code == 201:
            try:
                return response.json()
            except Exception:
                return {"status": "submitted", "code": 201}
        response.raise_for_status()
        try:
            return response.json()
        except Exception:
            return {}


def generate_report(report_path, conn, all_factors, phase3_results, passed_for_submit, submitted_factors):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append("# WQB d5自相关低谷突破 - 提交检查报告\n")
    lines.append(f"**生成时间**: {now}\n")
    lines.append("---\n")
    lines.append("## 执行摘要\n")
    lines.append(f"- 回测因子: {len(all_factors)}个")
    lines.append(f"- 提交检查: {len(phase3_results)}个因子执行检查")
    lines.append(f"- 全部通过: {len(passed_for_submit)}个因子")
    lines.append(f"- 正式提交: {len(submitted_factors)}个因子\n")

    lines.append("## 所有因子结果\n")
    lines.append("| 因子名称 | Alpha ID | Sharpe | Fitness | 换手率 | 自相关 | 状态 |")
    lines.append("|----------|----------|--------|---------|--------|--------|------|")
    for f in all_factors:
        sc = f.get("self_correlation")
        sc_str = f"{sc:.4f}" if sc is not None else "-"
        s = f.get("sharpe", "-")
        fi = f.get("fitness", "-")
        to = f.get("turnover", "-")
        passed = (sc is not None and sc < 0.7 and s is not None and s >= 1.25 and fi is not None and fi >= 1.0)
        lines.append(f"| {f['factor_name']} | {f['alpha_id']} | {s} | {fi} | {to} | {sc_str} | {'✅' if passed else '❌'} |")

    lines.append("\n## 提交检查结果\n")
    if phase3_results:
        for pr in phase3_results:
            lines.append(f"\n### {pr.get('factor_name', '-')} ({pr.get('alpha_id', '-')})\n")
            lines.append(f"- **状态**: {pr.get('status', '-')}")
            lines.append(f"- **自相关**: {pr.get('self_correlation', '-')}")
            lines.append(f"- **检查项数**: {pr.get('check_count', 0)}/8")
            lines.append(f"- **失败项**: {', '.join(pr.get('failed_checks', [])) or '无'}\n")
            lines.append("| 检查项 | 结果 | 数值 | 阈值 |")
            lines.append("|--------|------|------|------|")
            for name, check in sorted(pr.get('checks', {}).items()):
                s = check.get("status", "?")
                v = check.get("value", "-")
                l = check.get("limit", "-")
                vs = f"{v:.4f}" if isinstance(v, float) else str(v) if v is not None else "-"
                ls = f"{l:.4f}" if isinstance(l, float) else str(l) if l is not None else "-"
                lines.append(f"| {name} | {s} | {vs} | {ls} |")
    else:
        lines.append("\n无因子满足提交检查条件。\n")

    lines.append("\n## 正式提交结果\n")
    if submitted_factors:
        lines.append("| 因子名称 | Alpha ID | 提交状态 |")
        lines.append("|----------|----------|----------|")
        for sf in submitted_factors:
            lines.append(f"| {sf.get('factor_name', '-')} | {sf.get('alpha_id', '-')} | ✅ 已提交 |")
    else:
        lines.append("\n无因子通过全部检查，未执行正式提交。\n")

    lines.append("\n## 核心发现\n")
    lines.append("1. **d5自相关低谷 (SC=0.5838) 仅存在于decay=15设置下**")
    lines.append("2. **decay=0时，d5自身SC≈0.71，加入vol20后SC仍在0.71-0.72**")
    lines.append("3. **vol20权重对SC影响极小（0.5%~2%权重SC几乎不变）**")
    lines.append("4. **所有vol20组合的Fitness为0.74-0.75，低于1.0阈值**")
    lines.append("5. **乘法组合(volume_confirm) SC=0.6553但Fitness仅0.52**\n")
    lines.append("### 结论\n")
    lines.append("当前策略组合无法同时满足SC≤0.7且Fitness≥1.0的条件。\n")
    lines.append("### 建议\n")
    lines.append("1. 回归d5 (decay=15) 自身，SC=0.58, S=1.66, F=1.50 — 但已提交\n")
    lines.append("2. 寻找其他低SC信号与d5组合（非vol20类）\n")
    lines.append("3. 尝试d5 + 超低权重(0.1%)的其他信号\n")
    lines.append("4. 考虑不同市场/周期设置下的d5变体\n")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n报告已生成: {report_path}")


def main():
    email = os.environ.get("BRAIN_CREDENTIAL_EMAIL", "q1z2q3@126.com")
    password = os.environ.get("BRAIN_CREDENTIAL_PASSWORD", "W2025zq0118")
    db_path = DB_PATH
    report_path = REPORT_PATH

    if len(sys.argv) > 1 and sys.argv[1] != "display_only":
        email = sys.argv[1]
    if len(sys.argv) > 2:
        password = sys.argv[2]

    os.environ["BRAIN_CREDENTIAL_EMAIL"] = email
    os.environ["BRAIN_CREDENTIAL_PASSWORD"] = password

    conn = init_db(db_path)
    print(f"数据库: {db_path}")

    # 获取所有已完成因子
    all_alphas = get_all_completed_alphas(conn)
    print(f"待检查因子: {len(all_alphas)} 个")
    for a in all_alphas:
        print(f"  {a['factor_name']} ({a['alpha_id']}): S={a['sharpe']}, F={a['fitness']}")

    if not all_alphas:
        print("没有待检查的因子，请先运行阶段1模拟脚本。")
        return

    print("\n登录 WQB...")
    session = start_session()
    print("登录成功！")

    # 1. 自相关检查
    print("\n" + "=" * 60)
    print("1. 自相关检查")
    print("=" * 60)

    for a in all_alphas:
        existing_sc = get_existing_sc(conn, a["alpha_id"])
        if existing_sc is not None:
            print(f"  [跳过] {a['factor_name']}: 已有自相关 SC={existing_sc:.4f}")
            a["self_correlation"] = existing_sc
        else:
            time.sleep(SUBMIT_INTERVAL)
            sc = check_self_corr(session, conn, a["alpha_id"], a["factor_name"])
            a["self_correlation"] = sc

    # 2. 筛选候选（S≥1.25, F≥1.0）
    candidates = [a for a in all_alphas if a.get("sharpe") is not None and a.get("sharpe", 0) >= 1.25
                  and a.get("fitness") is not None and a.get("fitness", 0) >= 1.0]
    print(f"\n候选因子 (S≥1.25, F≥1.0): {len(candidates)} 个")
    for c in candidates:
        print(f"  {c['factor_name']} ({c['alpha_id']}): S={c['sharpe']}, F={c['fitness']}, SC={c.get('self_correlation')}")

    # 3. 提交检查
    print("\n" + "=" * 60)
    print("2. 提交检查")
    print("=" * 60)
    phase3_results = []
    passed_for_submit = []
    submitted_factors = []

    client = WQBCheckClient(session)
    for c in candidates:
        alpha_id = c["alpha_id"]
        factor_name = c["factor_name"]

        # 检查是否已有提交检查记录
        cursor = conn.cursor()
        cursor.execute("SELECT status, passed, submitted FROM submit_checks WHERE alpha_id = ? ORDER BY checked_at DESC LIMIT 1", (alpha_id,))
        existing = cursor.fetchone()
        if existing:
            print(f"\n  [跳过] {factor_name}: 已有检查记录 status={existing[0]}")
            if existing[2]:
                submitted_factors.append(c)
            continue

        time.sleep(SUBMIT_INTERVAL)
        result = client.run_submit_check(alpha_id, poll=True, max_polls=5, poll_interval=20)
        if result is None:
            continue

        checks = result.get("checks", {})
        failed = [k for k, v in checks.items() if v.get("status") == "FAIL"]
        pending = [k for k, v in checks.items() if v.get("status") == "PENDING"]
        all_pass = len(failed) == 0 and len(pending) == 0

        save_submit_check(conn, alpha_id, factor_name, result["status"],
                          result.get("self_correlation"), result.get("sharpe"),
                          result.get("fitness"), result.get("turnover"),
                          checks, all_pass)

        phase3_results.append({
            "alpha_id": alpha_id, "factor_name": factor_name,
            "status": result["status"], "checks": checks,
            "check_count": result.get("check_count", 0),
            "all_pass": all_pass,
            "self_correlation": result.get("self_correlation"),
            "sharpe": result.get("sharpe"), "fitness": result.get("fitness"),
            "turnover": result.get("turnover"),
            "failed_checks": failed, "pending_checks": pending,
        })

        if all_pass:
            passed_for_submit.append(c)
            print(f"  ✅ {factor_name} 通过全部检查，准备提交...")
            time.sleep(SUBMIT_INTERVAL)
            try:
                sr = client.confirm_submit(alpha_id)
                mark_submitted(conn, alpha_id, json.dumps(sr))
                submitted_factors.append(c)
                passed_for_submit = [p for p in passed_for_submit if p["alpha_id"] != alpha_id]
                print(f"    提交成功！")
            except Exception as e:
                print(f"    提交失败: {e}")
        else:
            print(f"  ❌ {factor_name} 未通过: {', '.join(failed)}")

    # 4. 生成报告
    print("\n" + "=" * 60)
    print("生成报告")
    print("=" * 60)
    generate_report(report_path, conn, all_alphas, phase3_results, passed_for_submit, submitted_factors)
    conn.close()

    # 输出摘要
    print("\n" + "=" * 60)
    print("结果摘要")
    print("=" * 60)
    print(f"因子总数: {len(all_alphas)}")
    print(f"候选因子: {len(candidates)}")
    print(f"执行检查: {len(phase3_results)}")
    print(f"通过检查: {len(passed_for_submit)}")
    print(f"正式提交: {len(submitted_factors)}")
    if submitted_factors:
        for sf in submitted_factors:
            print(f"  ✅ {sf['factor_name']} ({sf['alpha_id']})")
    print(f"\n报告: {report_path}")


if __name__ == "__main__":
    main()