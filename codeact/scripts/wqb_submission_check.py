#!/usr/bin/env python3
"""
WQB 因子提交检查与正式提交脚本
=================================

功能：
  1. 从状态库读取指定因子的 alpha_id
  2. 对每个因子执行提交检查（8项检查）
  3. 验证 SELF_CORRELATION ≤ 0.7 等所有检查项
  4. 对通过所有检查的因子执行正式提交
  5. 生成检查结果报告

使用：
  python wqb_submission_check.py [result_mode] [factor_names] [email] [password] [db_path] [submit_interval] [report_path]

状态表：
  - submit_checks: 存储每次提交检查的结果，以 alpha_id + checked_at 为去重依据
  - 去重口径：同一 alpha_id 同一天多次检查会分别记录
"""

import asyncio
import json
import os
import sys
import time
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests

# ============================================================
# 路径配置
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# 常量
# ============================================================

BASE_URL = "https://api.worldquantbrain.com"

# 8项提交检查及阈值
SUBMISSION_CHECKS = {
    "LOW_SHARPE": 1.25,
    "LOW_FITNESS": 1.0,
    "LOW_TURNOVER": 0.01,
    "HIGH_TURNOVER": 0.7,
    "CONCENTRATED_WEIGHT": None,
    "LOW_SUB_UNIVERSE_SHARPE": None,
    "SELF_CORRELATION": 0.7,
    "MATCHES_COMPETITION": None,
}


# ============================================================
# 指数退避重试
# ============================================================

def retry_with_backoff(func, max_retries: int = 5, base_delay: float = 3.0,
                       backoff_factor: float = 2.0,
                       status_codes: tuple = (429, 500, 502, 503, 504)):
    """
    指数退避重试包装器
    """
    delay = base_delay
    last_exception = None
    for attempt in range(max_retries):
        try:
            return func()
        except requests.HTTPError as e:
            if e.response.status_code in status_codes:
                last_exception = e
                retry_after = e.response.headers.get("Retry-After")
                if retry_after:
                    wait = float(retry_after)
                else:
                    wait = delay * (backoff_factor ** attempt)
                print(f"  [重试 {attempt+1}/{max_retries}] 状态码 {e.response.status_code}, "
                      f"等待 {wait:.1f}s 后重试...")
                time.sleep(wait)
            else:
                raise
    raise last_exception


# ============================================================
# WQB API 客户端
# ============================================================

class WQBCheckClient:
    """WQB 提交检查专用客户端"""

    def __init__(self, email: str, password: str):
        # 清除代理环境变量
        for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                    "ALL_PROXY", "all_proxy"]:
            if var in os.environ:
                del os.environ[var]

        self.email = email
        self._session = requests.Session()
        self._session.auth = (email, password)
        self._session.trust_env = False
        self._authenticated = False

    def authenticate(self) -> dict:
        """登录认证"""
        def _do():
            response = self._session.post(f"{BASE_URL}/authentication")
            response.raise_for_status()
            return response.json()

        user_info = retry_with_backoff(_do, max_retries=3)
        self._authenticated = True
        print(f"[WQB] 登录成功: {user_info.get('user', {}).get('id', 'unknown')}")
        return user_info

    def run_submit_check(self, alpha_id: str) -> dict:
        """
        运行提交检查（POST /alphas/{id}/submit）

        注意：403 是正常的（检查未通过），响应体中包含检查结果。
        检查结果在 is.checks 数组中。

        Returns:
            dict with:
              - status: "PASS" | "FAIL" | "PENDING"
              - checks: {check_name: {status, value, limit}}
              - self_correlation: float or None
              - sharpe: float or None
              - fitness: float or None
              - turnover: float or None
              - raw: 原始响应数据
        """
        def _do_post():
            return self._session.post(f"{BASE_URL}/alphas/{alpha_id}/submit")

        try:
            response = retry_with_backoff(
                _do_post, max_retries=3, base_delay=5.0,
                status_codes=(429, 500, 502, 503, 504)
            )
            # 403是正常的（检查未通过），200/201/202是全部通过或处理中
            if response.status_code in (403, 200, 201, 202):
                try:
                    data = response.json()
                except Exception:
                    data = {}
            else:
                response.raise_for_status()
                data = response.json()
        except requests.HTTPError as e:
            if e.response.status_code == 403:
                try:
                    data = e.response.json()
                except Exception:
                    data = {}
            else:
                raise

        # 解析 IS 指标
        is_data = data.get("is", {})

        # 解析检查结果
        checks_list = is_data.get("checks", [])
        checks_dict = {}
        all_pass = True
        has_pending = False
        self_corr_value = None
        sharpe = None
        fitness = None
        turnover = None

        for check in checks_list:
            name = check.get("name", "UNKNOWN")
            result = check.get("result", "UNKNOWN")
            value = check.get("value")
            limit = check.get("limit")
            checks_dict[name] = {
                "status": result,
                "value": value,
                "limit": limit,
            }
            # 从检查项中提取关键指标
            if name == "SELF_CORRELATION" and value is not None:
                self_corr_value = float(value)
            elif name == "LOW_SHARPE" and value is not None:
                sharpe = float(value)
            elif name == "LOW_FITNESS" and value is not None:
                fitness = float(value)
            elif name == "LOW_TURNOVER" and value is not None:
                turnover = float(value)

            if result == "FAIL":
                all_pass = False
            elif result == "PENDING":
                has_pending = True

        if has_pending:
            overall_status = "PENDING"
        elif all_pass and checks_dict:
            overall_status = "PASS"
        else:
            overall_status = "FAIL"

        return {
            "status": overall_status,
            "checks": checks_dict,
            "self_correlation": self_corr_value,
            "sharpe": sharpe,
            "fitness": fitness,
            "turnover": turnover,
            "raw": data,
        }

    def confirm_submit(self, alpha_id: str) -> dict:
        """
        正式提交 Alpha（通过所有检查后再次调用 submit 接口）
        根据 WQB API 文档：通过检查后再 POST/PUT 一次即正式提交
        """
        def _do_put():
            return self._session.put(f"{BASE_URL}/alphas/{alpha_id}/submit")

        response = retry_with_backoff(
            _do_put, max_retries=3, base_delay=5.0,
            status_codes=(429, 500, 502, 503, 504)
        )
        response.raise_for_status()
        return response.json()


# ============================================================
# 数据库操作
# ============================================================

class SubmissionCheckDB:
    """提交检查结果数据库管理"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        """确保 submit_checks 表存在"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS submit_checks (
                alpha_id TEXT NOT NULL,
                factor_name TEXT,
                checked_at TEXT NOT NULL,
                status TEXT,
                self_correlation REAL,
                sharpe REAL,
                fitness REAL,
                turnover REAL,
                checks_json TEXT,
                passed INTEGER,
                submitted INTEGER DEFAULT 0,
                submit_result TEXT,
                error TEXT,
                PRIMARY KEY (alpha_id, checked_at)
            )
        """)
        # 兼容旧表：添加提交相关列
        for col_name, col_def in [
            ("submitted", "INTEGER DEFAULT 0"),
            ("submit_result", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE submit_checks ADD COLUMN {col_name} {col_def}")
            except sqlite3.OperationalError:
                pass
        conn.commit()
        conn.close()

    def get_factor_alpha_ids(self, factor_names: List[str]) -> Dict[str, str]:
        """
        根据因子名列表获取 alpha_id 映射

        Returns:
            {factor_name: alpha_id}，只返回找到的因子
        """
        conn = sqlite3.connect(self.db_path)
        result = {}
        for name in factor_names:
            row = conn.execute(
                "SELECT factor_name, alpha_id FROM alphas WHERE factor_name = ? AND alpha_id IS NOT NULL",
                (name,)
            ).fetchone()
            if row:
                result[row[0]] = row[1]
        conn.close()
        return result

    def get_factor_metrics(self, factor_names: List[str]) -> Dict[str, dict]:
        """获取因子的基本指标"""
        conn = sqlite3.connect(self.db_path)
        result = {}
        for name in factor_names:
            row = conn.execute(
                "SELECT factor_name, alpha_id, sharpe, fitness, turnover, status "
                "FROM alphas WHERE factor_name = ?",
                (name,)
            ).fetchone()
            if row:
                result[row[0]] = {
                    "factor_name": row[0],
                    "alpha_id": row[1],
                    "sharpe": row[2],
                    "fitness": row[3],
                    "turnover": row[4],
                    "status": row[5],
                }
        conn.close()
        return result

    def save_check_result(self, alpha_id: str, factor_name: str,
                          status: str, checks: dict,
                          self_correlation: float = None,
                          sharpe: float = None, fitness: float = None,
                          turnover: float = None,
                          error: str = None):
        """保存检查结果"""
        now = datetime.now().isoformat(timespec="seconds")
        passed = 1 if status == "PASS" else 0
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO submit_checks (
                alpha_id, factor_name, checked_at, status,
                self_correlation, sharpe, fitness, turnover,
                checks_json, passed, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            alpha_id, factor_name, now, status,
            self_correlation, sharpe, fitness, turnover,
            json.dumps(checks, ensure_ascii=False),
            passed, error
        ))
        conn.commit()
        conn.close()
        return now

    def mark_submitted(self, alpha_id: str, checked_at: str, submit_result: str):
        """标记为已正式提交"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            UPDATE submit_checks SET submitted = 1, submit_result = ?
            WHERE alpha_id = ? AND checked_at = ?
        """, (submit_result, alpha_id, checked_at))
        conn.commit()
        conn.close()


# ============================================================
# 报告生成
# ============================================================

def generate_report(factor_results: List[dict], submitted_factors: List[dict],
                    report_path: str) -> str:
    """
    生成 Markdown 格式的检查报告

    Args:
        factor_results: 每个因子的检查结果列表
        submitted_factors: 成功正式提交的因子列表
        report_path: 报告输出路径

    Returns:
        报告文件的绝对路径
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    lines.append("# WQB 因子提交检查报告")
    lines.append("")
    lines.append(f"**检查时间**: {now_str}")
    lines.append(f"**检查因子数**: {len(factor_results)}")
    lines.append(f"**通过全部检查**: {sum(1 for r in factor_results if r['status'] == 'PASS')} 个")
    lines.append(f"**正式提交成功**: {len(submitted_factors)} 个")
    lines.append("")

    # 汇总表格
    lines.append("## 汇总结果")
    lines.append("")
    lines.append("| 因子名称 | Alpha ID | Sharpe | Fitness | 自相关性 | 检查状态 | 正式提交 |")
    lines.append("|---------|----------|--------|---------|----------|----------|----------|")

    for r in factor_results:
        sc = r.get("self_correlation")
        sc_str = f"{sc:.4f}" if sc is not None else "N/A"
        status_icon = "✅ PASS" if r["status"] == "PASS" else (
            "⏳ PENDING" if r["status"] == "PENDING" else "❌ FAIL"
        )
        submit_icon = "✅ 已提交" if r.get("submitted") else "-"
        sharpe_str = f"{r['sharpe']:.2f}" if r.get("sharpe") else "N/A"
        fitness_str = f"{r['fitness']:.2f}" if r.get("fitness") else "N/A"
        lines.append(
            f"| {r['factor_name']} | {r['alpha_id']} | {sharpe_str} | {fitness_str} | "
            f"{sc_str} | {status_icon} | {submit_icon} |"
        )

    lines.append("")

    # 每项检查详细结果
    lines.append("## 8项检查详细结果")
    lines.append("")

    check_order = [
        "LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER", "HIGH_TURNOVER",
        "CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE",
        "SELF_CORRELATION", "MATCHES_COMPETITION"
    ]

    for r in factor_results:
        lines.append(f"### {r['factor_name']} ({r['alpha_id']})")
        lines.append("")
        lines.append("| 检查项 | 状态 | 数值 | 阈值 |")
        lines.append("|--------|------|------|------|")

        checks = r.get("checks", {})
        for check_name in check_order:
            check = checks.get(check_name, {})
            status = check.get("status", "N/A")
            value = check.get("value")
            limit = check.get("limit")

            status_icon = "✅ PASS" if status == "PASS" else (
                "⏳ PENDING" if status == "PENDING" else (
                    "❌ FAIL" if status == "FAIL" else status
                )
            )
            value_str = str(value) if value is not None else "-"
            limit_str = str(limit) if limit is not None else "-"
            lines.append(f"| {check_name} | {status_icon} | {value_str} | {limit_str} |")

        lines.append("")

        if r.get("error"):
            lines.append(f"> ⚠️ 错误: {r['error']}")
            lines.append("")

    # 正式提交结果
    if submitted_factors:
        lines.append("## 正式提交成功的因子")
        lines.append("")
        for sf in submitted_factors:
            lines.append(f"- **{sf['factor_name']}** ({sf['alpha_id']})")
            if sf.get("submit_message"):
                lines.append(f"  - 提交信息: {sf['submit_message']}")
        lines.append("")
    else:
        lines.append("## 正式提交结果")
        lines.append("")
        lines.append("本次检查中没有因子通过全部 8 项检查，未执行正式提交。")
        lines.append("")

    # 说明
    lines.append("## 说明")
    lines.append("")
    lines.append("- 提交检查通过标准：8 项检查全部为 PASS")
    lines.append("- SELF_CORRELATION 阈值：≤ 0.7")
    lines.append("- Sharpe 阈值：≥ 1.25")
    lines.append("- Fitness 阈值：≥ 1.0")
    lines.append("- 检查接口：POST /alphas/{id}/submit")
    lines.append("")

    report_content = "\n".join(lines)
    abs_path = os.path.abspath(report_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    return abs_path


# ============================================================
# 主流程
# ============================================================

async def main():
    # 参数解析
    result_mode = sys.argv[1] if len(sys.argv) > 1 else "display_only"
    factor_names_str = sys.argv[2] if len(sys.argv) > 2 else (
        "combo_d10_vol20_w8020,combo_d10_vol20_w9010,combo_d10_vol120_w9010,"
        "combo_d10_vol60_w7525,combo_d10_vol120_w9505"
    )
    email = sys.argv[3] if len(sys.argv) > 3 else "q1z2q3@126.com"
    password = sys.argv[4] if len(sys.argv) > 4 else "W2025zq0118"
    db_path = sys.argv[5] if len(sys.argv) > 5 else os.path.join(OUTPUT_DIR, "wqb_state.db")
    submit_interval = int(sys.argv[6]) if len(sys.argv) > 6 else 50
    report_path = sys.argv[7] if len(sys.argv) > 7 else os.path.join(OUTPUT_DIR, "wqb_submission_check_report.md")

    factor_names = [n.strip() for n in factor_names_str.split(",") if n.strip()]

    print(f"[参数] result_mode={result_mode}")
    print(f"[参数] 因子列表: {factor_names}")
    print(f"[参数] 提交间隔: {submit_interval}s")
    print(f"[参数] 状态库: {db_path}")
    print(f"[参数] 报告路径: {report_path}")

    # 映射 result_mode
    actual_mode = result_mode if result_mode != "auto" else "display_only"

    # 延迟导入 codeact_sdk（沙箱环境）
    try:
        from codeact_sdk import CodeActSDK
        sdk = CodeActSDK()
    except ImportError:
        sdk = None
        print("[警告] codeact_sdk 不可用，仅本地运行模式")

    try:
        # 1. 从状态库查询因子 alpha_id
        print("\n=== 步骤1: 从状态库查询因子信息 ===")
        db = SubmissionCheckDB(db_path)
        factor_metrics = db.get_factor_metrics(factor_names)

        found_count = len(factor_metrics)
        missing = [n for n in factor_names if n not in factor_metrics]

        print(f"找到 {found_count}/{len(factor_names)} 个因子")
        if missing:
            print(f"未找到的因子: {missing}")

        if found_count == 0:
            message = "错误：未找到任何指定的因子，请检查因子名称是否正确"
            if sdk:
                await sdk.submit_result(
                    result_mode="notify",
                    status="error",
                    message=message,
                    data={"missing_factors": missing},
                )
            else:
                print(message)
            return

        for name, info in factor_metrics.items():
            print(f"  {name}: alpha_id={info['alpha_id']}, "
                  f"sharpe={info['sharpe']}, fitness={info['fitness']}")

        # 2. 登录 WQB
        print("\n=== 步骤2: 登录 WQB 平台 ===")
        client = WQBCheckClient(email, password)
        client.authenticate()

        # 3. 逐个执行提交检查
        print("\n=== 步骤3: 执行提交检查 ===")
        factor_results = []
        submitted_factors = []

        for i, (factor_name, info) in enumerate(factor_metrics.items()):
            alpha_id = info["alpha_id"]
            print(f"\n[{i+1}/{found_count}] 检查 {factor_name} ({alpha_id})...")

            try:
                check_result = client.run_submit_check(alpha_id)
                status = check_result["status"]
                checks = check_result["checks"]
                self_corr = check_result["self_correlation"]
                sharpe = check_result["sharpe"]
                fitness = check_result["fitness"]
                turnover = check_result["turnover"]

                print(f"  检查状态: {status}")
                print(f"  Sharpe: {sharpe}, Fitness: {fitness}")
                print(f"  Self-Correlation: {self_corr}")

                # 保存到数据库
                checked_at = db.save_check_result(
                    alpha_id=alpha_id,
                    factor_name=factor_name,
                    status=status,
                    checks=checks,
                    self_correlation=self_corr,
                    sharpe=sharpe,
                    fitness=fitness,
                    turnover=turnover,
                )

                result_entry = {
                    "factor_name": factor_name,
                    "alpha_id": alpha_id,
                    "status": status,
                    "checks": checks,
                    "self_correlation": self_corr,
                    "sharpe": sharpe,
                    "fitness": fitness,
                    "turnover": turnover,
                    "submitted": False,
                    "error": None,
                    "checked_at": checked_at,
                }
                factor_results.append(result_entry)

                # 如果通过所有检查，执行正式提交
                if status == "PASS":
                    print(f"  ✅ 通过全部检查，执行正式提交...")
                    try:
                        submit_result = client.confirm_submit(alpha_id)
                        submit_msg = f"正式提交成功 (status={submit_result.get('status', 'unknown')})"
                        print(f"  ✅ {submit_msg}")

                        db.mark_submitted(alpha_id, checked_at, json.dumps(submit_result))
                        result_entry["submitted"] = True
                        result_entry["submit_message"] = submit_msg

                        submitted_factors.append({
                            "factor_name": factor_name,
                            "alpha_id": alpha_id,
                            "submit_message": submit_msg,
                            "submit_data": submit_result,
                        })
                    except Exception as e:
                        err_msg = f"正式提交失败: {type(e).__name__}: {e}"
                        print(f"  ❌ {err_msg}")
                        result_entry["submit_error"] = err_msg

            except Exception as e:
                err_msg = f"{type(e).__name__}: {e}"
                print(f"  ❌ 检查失败: {err_msg}")

                # 保存失败记录
                checked_at = db.save_check_result(
                    alpha_id=alpha_id,
                    factor_name=factor_name,
                    status="ERROR",
                    checks={},
                    error=err_msg,
                )

                factor_results.append({
                    "factor_name": factor_name,
                    "alpha_id": alpha_id,
                    "status": "ERROR",
                    "checks": {},
                    "self_correlation": None,
                    "sharpe": info.get("sharpe"),
                    "fitness": info.get("fitness"),
                    "turnover": None,
                    "submitted": False,
                    "error": err_msg,
                    "checked_at": checked_at,
                })

            # 提交间隔（最后一个不需要等）
            if i < found_count - 1:
                print(f"  ⏳ 等待 {submit_interval}s 后检查下一个因子...")
                time.sleep(submit_interval)

        # 4. 生成报告
        print("\n=== 步骤4: 生成报告 ===")
        abs_report_path = generate_report(factor_results, submitted_factors, report_path)
        print(f"报告已生成: {abs_report_path}")

        # 5. 构造用户摘要
        pass_count = sum(1 for r in factor_results if r["status"] == "PASS")
        fail_count = sum(1 for r in factor_results if r["status"] == "FAIL")
        error_count = sum(1 for r in factor_results if r["status"] == "ERROR")
        submitted_count = len(submitted_factors)

        summary_lines = []
        summary_lines.append(f"**WQB 因子提交检查结果** | 共 {len(factor_results)} 个因子")
        summary_lines.append("")
        summary_lines.append(
            f"✅ 通过: {pass_count} | ❌ 未通过: {fail_count} | "
            f"⚠️ 错误: {error_count} | 📤 已提交: {submitted_count}"
        )
        summary_lines.append("")

        # 列出每个因子的关键结果
        for r in factor_results:
            sc = r.get("self_correlation")
            sc_str = f"自相关={sc:.4f}" if sc is not None else "自相关=N/A"
            status_str = "✅ PASS" if r["status"] == "PASS" else (
                "❌ FAIL" if r["status"] == "FAIL" else (
                    "⚠️ ERROR" if r["status"] == "ERROR" else "⏳ PENDING"
                )
            )
            submit_tag = " [已提交]" if r.get("submitted") else ""
            summary_lines.append(
                f"- {r['factor_name']}: {status_str} (Sharpe={r.get('sharpe', 'N/A')}, "
                f"Fitness={r.get('fitness', 'N/A')}, {sc_str}){submit_tag}"
            )

        summary_lines.append("")
        summary_lines.append(f"详细报告: [wqb_submission_check_report.md](computer://{abs_report_path})")

        message = "\n".join(summary_lines)

        # 提交结果
        if sdk:
            await sdk.submit_result(
                result_mode=actual_mode,
                status="success",
                message=message,
                data={
                    "report_path": report_path,
                    "total_count": len(factor_results),
                    "pass_count": pass_count,
                    "fail_count": fail_count,
                    "error_count": error_count,
                    "submitted_count": submitted_count,
                    "submitted_factors": [
                        {"factor_name": sf["factor_name"], "alpha_id": sf["alpha_id"]}
                        for sf in submitted_factors
                    ],
                    "factor_results": [
                        {
                            "factor_name": r["factor_name"],
                            "alpha_id": r["alpha_id"],
                            "status": r["status"],
                            "self_correlation": r.get("self_correlation"),
                            "sharpe": r.get("sharpe"),
                            "fitness": r.get("fitness"),
                            "submitted": r.get("submitted", False),
                        }
                        for r in factor_results
                    ],
                },
            )
        else:
            print("\n=== 最终结果 ===")
            print(message)

    except Exception as e:
        error_msg = f"执行失败: {type(e).__name__}: {e}"
        print(f"\n❌ {error_msg}")
        import traceback
        traceback.print_exc()

        if sdk:
            await sdk.submit_result(
                result_mode="notify",
                status="error",
                message=error_msg,
                data={"error_type": type(e).__name__},
            )
        else:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
