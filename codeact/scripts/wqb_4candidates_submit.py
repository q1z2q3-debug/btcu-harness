#!/usr/bin/env python3
"""
WQB 4个候选因子提交检查与正式发布脚本
========================================

功能：
  1. 对指定的候选因子列表执行8项提交检查（含SELF_CORRELATION ≤ 0.7）
  2. 检查状态库中是否已有记录，避免重复检查
  3. 对通过所有8项检查的因子自动执行正式提交
  4. 生成完整的检查结果报告

使用：
  python wqb_4candidates_submit.py [result_mode] [candidates] [email] [password] [db_path] [submit_interval] [report_path]

  candidates 格式：alpha_id:factor_name:sharpe:fitness:turnover，多个用逗号分隔
  示例：E5eE3Zp1:alpha_021_d1_raw:1.73:1.22:0.4034,E5eEALEL:alpha_021_d3:1.69:1.42:0.2719

状态表：
  - submit_checks: 存储每次提交检查的结果，以 alpha_id 为主键去重
  - 去重口径：同一 alpha_id 只保留最新检查结果，已检查过的不再重复调用API
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

CHECK_ORDER = [
    "LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER", "HIGH_TURNOVER",
    "CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE",
    "SELF_CORRELATION", "MATCHES_COMPETITION"
]


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

    def _parse_check_result(self, data: dict) -> dict:
        """
        解析检查结果数据

        Returns:
            dict with status, checks, self_correlation, sharpe, fitness, turnover
        """
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
        elif not checks_dict:
            overall_status = "PENDING"  # 没有检查项说明还在处理中
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
            "check_count": len(checks_dict),
        }

    def run_submit_check(self, alpha_id: str, poll: bool = True,
                         max_polls: int = 5, poll_interval: int = 20) -> dict:
        """
        运行提交检查（POST /alphas/{id}/submit），支持轮询等待检查完成

        注意：403 是正常的（检查未通过），响应体中包含检查结果。
        检查结果在 is.checks 数组中。
        第一次调用可能返回空检查项（处理中），需要轮询等待。

        Args:
            alpha_id: 因子ID
            poll: 是否启用轮询
            max_polls: 最大轮询次数
            poll_interval: 轮询间隔（秒）

        Returns:
            dict with:
              - status: "PASS" | "FAIL" | "PENDING"
              - checks: {check_name: {status, value, limit}}
              - self_correlation: float or None
              - sharpe: float or None
              - fitness: float or None
              - turnover: float or None
              - raw: 原始响应数据
              - check_count: 检查项数量
        """
        def _do_post():
            return self._session.post(f"{BASE_URL}/alphas/{alpha_id}/submit")

        last_result = None

        for poll_idx in range(max_polls if poll else 1):
            data = {}
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

            result = self._parse_check_result(data)
            last_result = result

            check_count = result["check_count"]
            status = result["status"]

            if poll_idx == 0:
                print(f"  第1次检查: 状态={status}, 检查项数={check_count}")
            else:
                print(f"  第{poll_idx+1}次轮询: 状态={status}, 检查项数={check_count}")

            # 判断是否检查完成：至少有5项检查，且没有PENDING状态
            if check_count >= 5 and status != "PENDING":
                break

            # 如果还没完成且不是最后一次，等待后重试
            if poll and poll_idx < max_polls - 1:
                print(f"  检查尚未完成，等待 {poll_interval}s 后重试...")
                time.sleep(poll_interval)

        return last_result

    def confirm_submit(self, alpha_id: str) -> dict:
        """
        正式提交 Alpha（通过所有检查后再次调用 submit 接口）
        根据 WQB API 文档：通过检查后再 PUT 一次即正式提交
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
                alpha_id TEXT PRIMARY KEY,
                factor_name TEXT,
                checked_at TEXT,
                status TEXT,
                self_correlation REAL,
                sharpe REAL,
                fitness REAL,
                turnover REAL,
                checks_json TEXT,
                passed INTEGER DEFAULT 0,
                submitted INTEGER DEFAULT 0,
                submit_result TEXT,
                error TEXT
            )
        """)
        # 兼容旧表：添加可能缺失的列
        for col_name, col_def in [
            ("submitted", "INTEGER DEFAULT 0"),
            ("submit_result", "TEXT"),
            ("factor_name", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE submit_checks ADD COLUMN {col_name} {col_def}")
            except sqlite3.OperationalError:
                pass
        conn.commit()
        conn.close()

    def get_existing_checks(self, alpha_ids: List[str]) -> Dict[str, dict]:
        """
        查询指定 alpha_id 是否已存在检查记录

        Returns:
            {alpha_id: {factor_name, status, self_correlation, sharpe, fitness, turnover, checks, submitted, checked_at}}
        """
        conn = sqlite3.connect(self.db_path)
        results = {}
        for alpha_id in alpha_ids:
            row = conn.execute(
                "SELECT alpha_id, factor_name, checked_at, status, "
                "self_correlation, sharpe, fitness, turnover, "
                "checks_json, passed, submitted, submit_result, error "
                "FROM submit_checks WHERE alpha_id = ?",
                (alpha_id,)
            ).fetchone()
            if row:
                checks = {}
                try:
                    checks = json.loads(row[8]) if row[8] else {}
                except Exception:
                    checks = {}
                results[alpha_id] = {
                    "alpha_id": row[0],
                    "factor_name": row[1],
                    "checked_at": row[2],
                    "status": row[3],
                    "self_correlation": row[4],
                    "sharpe": row[5],
                    "fitness": row[6],
                    "turnover": row[7],
                    "checks": checks,
                    "passed": bool(row[9]),
                    "submitted": bool(row[10]),
                    "submit_result": row[11],
                    "error": row[12],
                    "check_count": len(checks),
                }
        conn.close()
        return results

    def is_check_complete(self, record: dict) -> bool:
        """
        判断检查结果是否完整（至少有5项检查，且状态不是PENDING/ERROR）
        """
        if not record:
            return False
        if record.get("status") in ("PENDING", "ERROR"):
            return False
        if record.get("check_count", 0) < 5:
            return False
        return True

    def save_check_result(self, alpha_id: str, factor_name: str,
                          status: str, checks: dict,
                          self_correlation: float = None,
                          sharpe: float = None, fitness: float = None,
                          turnover: float = None,
                          error: str = None):
        """保存检查结果（INSERT OR REPLACE，以 alpha_id 为主键）"""
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

    def mark_submitted(self, alpha_id: str, submit_result: str):
        """标记为已正式提交"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            UPDATE submit_checks SET submitted = 1, submit_result = ?
            WHERE alpha_id = ?
        """, (submit_result, alpha_id))
        conn.commit()
        conn.close()


# ============================================================
# 候选因子解析
# ============================================================

def parse_candidates(candidates_str: str) -> List[dict]:
    """
    解析候选因子字符串

    格式：alpha_id:factor_name:sharpe:fitness:turnover，多个用逗号分隔

    Returns:
        [{alpha_id, factor_name, sharpe, fitness, turnover}, ...]
    """
    candidates = []
    for item in candidates_str.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split(":")
        if len(parts) < 2:
            print(f"[警告] 跳过格式错误的候选因子: {item}")
            continue
        alpha_id = parts[0].strip()
        factor_name = parts[1].strip() if len(parts) > 1 else alpha_id
        sharpe = float(parts[2]) if len(parts) > 2 and parts[2] else None
        fitness = float(parts[3]) if len(parts) > 3 and parts[3] else None
        turnover = float(parts[4]) if len(parts) > 4 and parts[4] else None
        candidates.append({
            "alpha_id": alpha_id,
            "factor_name": factor_name,
            "sharpe": sharpe,
            "fitness": fitness,
            "turnover": turnover,
        })
    return candidates


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
    lines.append("# WQB 候选因子提交检查与发布报告")
    lines.append("")
    lines.append(f"**检查时间**: {now_str}")
    lines.append(f"**检查因子数**: {len(factor_results)}")
    lines.append(f"**通过全部检查**: {sum(1 for r in factor_results if r['status'] == 'PASS')} 个")
    lines.append(f"**正式提交成功**: {len(submitted_factors)} 个")
    lines.append("")

    # 汇总表格
    lines.append("## 汇总结果")
    lines.append("")
    lines.append("| # | 因子名称 | Alpha ID | Sharpe | Fitness | 换手率 | 自相关性 | 检查状态 | 正式提交 |")
    lines.append("|---|---------|----------|--------|---------|--------|----------|----------|----------|")

    for i, r in enumerate(factor_results, 1):
        sc = r.get("self_correlation")
        sc_str = f"{sc:.4f}" if sc is not None else "N/A"
        sharpe_val = r.get("sharpe")
        sharpe_str = f"{sharpe_val:.2f}" if sharpe_val is not None else "N/A"
        fitness_val = r.get("fitness")
        fitness_str = f"{fitness_val:.2f}" if fitness_val is not None else "N/A"
        turnover_val = r.get("turnover")
        turnover_str = f"{turnover_val:.4f}" if turnover_val is not None else "N/A"
        status_icon = "✅ PASS" if r["status"] == "PASS" else (
            "⏳ PENDING" if r["status"] == "PENDING" else (
                "⚠️ ERROR" if r["status"] == "ERROR" else "❌ FAIL"
            )
        )
        submit_icon = "✅ 已提交" if r.get("submitted") else "-"
        lines.append(
            f"| {i} | {r['factor_name']} | `{r['alpha_id']}` | {sharpe_str} | {fitness_str} | "
            f"{turnover_str} | {sc_str} | {status_icon} | {submit_icon} |"
        )

    lines.append("")

    # 每项检查详细结果
    lines.append("## 8项检查详细结果")
    lines.append("")

    for i, r in enumerate(factor_results, 1):
        lines.append(f"### {i}. {r['factor_name']} (`{r['alpha_id']}`)")
        lines.append("")
        lines.append("| 检查项 | 状态 | 数值 | 阈值 | 说明 |")
        lines.append("|--------|------|------|------|------|")

        checks = r.get("checks", {})
        for check_name in CHECK_ORDER:
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

            # 检查项说明
            descriptions = {
                "LOW_SHARPE": "Sharpe ≥ 1.25",
                "LOW_FITNESS": "Fitness ≥ 1.0",
                "LOW_TURNOVER": "换手率 ≥ 0.01",
                "HIGH_TURNOVER": "换手率 ≤ 0.7",
                "CONCENTRATED_WEIGHT": "权重集中度检查",
                "LOW_SUB_UNIVERSE_SHARPE": "子宇宙Sharpe检查",
                "SELF_CORRELATION": "自相关性 ≤ 0.7",
                "MATCHES_COMPETITION": "竞赛重复检查",
            }
            desc = descriptions.get(check_name, "")
            lines.append(f"| {check_name} | {status_icon} | {value_str} | {limit_str} | {desc} |")

        lines.append("")

        if r.get("checked_at"):
            lines.append(f"- **检查时间**: {r['checked_at']}")
        if r.get("from_cache"):
            lines.append(f"- **数据来源**: 状态库缓存（已存在，无需重新检查）")
        else:
            lines.append(f"- **数据来源**: 实时API检查")
        if r.get("error"):
            lines.append(f"> ⚠️ 错误: {r['error']}")
        lines.append("")

    # 正式提交结果
    lines.append("## 正式提交结果")
    lines.append("")

    if submitted_factors:
        lines.append(f"共有 {len(submitted_factors)} 个因子通过全部8项检查并成功正式提交：")
        lines.append("")
        for sf in submitted_factors:
            lines.append(f"### ✅ {sf['factor_name']} (`{sf['alpha_id']}`)")
            lines.append("")
            if sf.get("submit_message"):
                lines.append(f"- 提交状态: {sf['submit_message']}")
            if sf.get("submit_data"):
                # 提取关键信息
                sd = sf["submit_data"]
                if isinstance(sd, dict):
                    if "status" in sd:
                        lines.append(f"- 状态: {sd['status']}")
                    if "id" in sd:
                        lines.append(f"- ID: {sd['id']}")
            lines.append("")
    else:
        lines.append("本次检查中没有因子通过全部 8 项检查，未执行正式提交。")
        lines.append("")

    # 失败原因分析
    failed_factors = [r for r in factor_results if r["status"] == "FAIL"]
    if failed_factors:
        lines.append("## 未通过检查的因子分析")
        lines.append("")
        for r in failed_factors:
            fail_checks = [name for name, c in r.get("checks", {}).items() if c.get("status") == "FAIL"]
            lines.append(f"### {r['factor_name']} (`{r['alpha_id']}`)")
            lines.append("")
            if fail_checks:
                lines.append(f"**未通过的检查项**: {', '.join(fail_checks)}")
                lines.append("")
                for name in fail_checks:
                    c = r["checks"].get(name, {})
                    val = c.get("value", "N/A")
                    lim = c.get("limit", "N/A")
                    lines.append(f"- **{name}**: 数值={val}, 阈值={lim}")
                lines.append("")
            else:
                lines.append("未找到具体失败的检查项信息。")
                lines.append("")

    # 说明
    lines.append("## 说明")
    lines.append("")
    lines.append("- **提交检查通过标准**：8 项检查全部为 PASS")
    lines.append("- **SELF_CORRELATION 阈值**：≤ 0.7")
    lines.append("- **Sharpe 阈值**：≥ 1.25")
    lines.append("- **Fitness 阈值**：≥ 1.0")
    lines.append("- **检查接口**：POST /alphas/{id}/submit")
    lines.append("- **正式提交接口**：PUT /alphas/{id}/submit")
    lines.append("- **提交间隔**：≥ 50 秒，避免 429 限流")
    lines.append("- **状态库去重**：同一 alpha_id 已有检查记录时直接从数据库读取，不重复调用 API")
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

    # 默认4个候选因子
    default_candidates = (
        "E5eE3Zp1:alpha_021_d1_raw:1.73:1.22:0.4034,"
        "E5eEALEL:alpha_021_d3:1.69:1.42:0.2719,"
        "O0xZv69J:alpha_021_d5:1.66:1.50:0.2261,"
        "pwKl0XoX:combo_d5_vol20_w9505:1.58:1.23:0.1791"
    )
    candidates_str = sys.argv[2] if len(sys.argv) > 2 else default_candidates
    email = sys.argv[3] if len(sys.argv) > 3 else "q1z2q3@126.com"
    password = sys.argv[4] if len(sys.argv) > 4 else "W2025zq0118"
    db_path = sys.argv[5] if len(sys.argv) > 5 else os.path.join(OUTPUT_DIR, "wqb_state.db")
    submit_interval = int(sys.argv[6]) if len(sys.argv) > 6 else 50
    report_path = sys.argv[7] if len(sys.argv) > 7 else os.path.join(OUTPUT_DIR, "wqb_4candidates_submit_report.md")

    # 解析候选因子
    candidates = parse_candidates(candidates_str)

    print(f"[参数] result_mode={result_mode}")
    print(f"[参数] 候选因子数: {len(candidates)}")
    for c in candidates:
        print(f"  - {c['factor_name']} ({c['alpha_id']}): "
              f"Sharpe={c['sharpe']}, Fitness={c['fitness']}, Turnover={c['turnover']}")
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
        # 1. 从状态库查询已有检查记录
        print("\n=== 步骤1: 查询状态库已有检查记录 ===")
        db = SubmissionCheckDB(db_path)
        alpha_ids = [c["alpha_id"] for c in candidates]
        existing = db.get_existing_checks(alpha_ids)

        print(f"状态库中已有 {len(existing)}/{len(candidates)} 个因子的检查记录")

        # 区分已检查（完整结果）和需重新检查的
        to_check = []
        cached_results = []
        for c in candidates:
            alpha_id = c["alpha_id"]
            if alpha_id in existing:
                rec = existing[alpha_id]
                if db.is_check_complete(rec):
                    print(f"  [缓存] {c['factor_name']} ({alpha_id}): "
                          f"status={rec['status']}, checks={rec['check_count']}项, "
                          f"submitted={rec['submitted']}")
                    cached_results.append({
                        "factor_name": c["factor_name"],
                        "alpha_id": alpha_id,
                        "status": rec["status"],
                        "checks": rec["checks"],
                        "self_correlation": rec["self_correlation"],
                        "sharpe": rec["sharpe"] if rec["sharpe"] else c["sharpe"],
                        "fitness": rec["fitness"] if rec["fitness"] else c["fitness"],
                        "turnover": rec["turnover"] if rec["turnover"] else c["turnover"],
                        "submitted": rec["submitted"],
                        "checked_at": rec["checked_at"],
                        "from_cache": True,
                        "error": rec["error"],
                    })
                else:
                    print(f"  [重检] {c['factor_name']} ({alpha_id}): "
                          f"缓存结果不完整 (status={rec['status']}, checks={rec['check_count']}项)，需重新检查")
                    to_check.append(c)
            else:
                print(f"  [待检] {c['factor_name']} ({alpha_id})")
                to_check.append(c)

        # 2. 如果有需要检查的因子，登录 WQB 并执行检查
        factor_results = list(cached_results)
        submitted_factors = []

        # 已缓存且已提交的因子也加入 submitted_factors
        for r in cached_results:
            if r.get("submitted"):
                submitted_factors.append({
                    "factor_name": r["factor_name"],
                    "alpha_id": r["alpha_id"],
                    "submit_message": "（来自状态库缓存）已正式提交",
                    "submit_data": None,
                })

        if to_check:
            print(f"\n=== 步骤2: 登录 WQB 平台（需检查 {len(to_check)} 个因子）===")
            client = WQBCheckClient(email, password)
            client.authenticate()

            # 3. 逐个执行提交检查
            print(f"\n=== 步骤3: 执行提交检查（{len(to_check)} 个因子）===")

            for i, cand in enumerate(to_check):
                alpha_id = cand["alpha_id"]
                factor_name = cand["factor_name"]
                print(f"\n[{i+1}/{len(to_check)}] 检查 {factor_name} ({alpha_id})...")

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

                    # 打印每项检查结果
                    fail_checks = [name for name, c in checks.items() if c.get("status") == "FAIL"]
                    if fail_checks:
                        print(f"  未通过项: {', '.join(fail_checks)}")
                        for name in fail_checks:
                            c = checks[name]
                            print(f"    - {name}: value={c.get('value')}, limit={c.get('limit')}")

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
                        "sharpe": sharpe if sharpe else cand.get("sharpe"),
                        "fitness": fitness if fitness else cand.get("fitness"),
                        "turnover": turnover if turnover else cand.get("turnover"),
                        "submitted": False,
                        "checked_at": checked_at,
                        "from_cache": False,
                        "error": None,
                    }
                    factor_results.append(result_entry)

                    # 如果通过所有检查且未提交过，执行正式提交
                    if status == "PASS" and not result_entry.get("submitted"):
                        print(f"  ✅ 通过全部检查，等待 {submit_interval}s 后执行正式提交...")
                        time.sleep(submit_interval)

                        try:
                            submit_result = client.confirm_submit(alpha_id)
                            submit_msg = f"正式提交成功 (status={submit_result.get('status', 'unknown')})"
                            print(f"  ✅ {submit_msg}")

                            db.mark_submitted(alpha_id, json.dumps(submit_result))
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
                    import traceback
                    traceback.print_exc()

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
                        "sharpe": cand.get("sharpe"),
                        "fitness": cand.get("fitness"),
                        "turnover": cand.get("turnover"),
                        "submitted": False,
                        "checked_at": checked_at,
                        "from_cache": False,
                        "error": err_msg,
                    })

                # 提交间隔（最后一个不需要等，除非后面还有提交操作）
                if i < len(to_check) - 1:
                    print(f"  ⏳ 等待 {submit_interval}s 后检查下一个因子...")
                    time.sleep(submit_interval)
        else:
            print("\n所有因子均已有检查记录，无需重新检查。")

        # 4. 生成报告
        print("\n=== 步骤4: 生成报告 ===")
        abs_report_path = generate_report(factor_results, submitted_factors, report_path)
        print(f"报告已生成: {abs_report_path}")

        # 5. 构造用户摘要
        pass_count = sum(1 for r in factor_results if r["status"] == "PASS")
        fail_count = sum(1 for r in factor_results if r["status"] == "FAIL")
        pending_count = sum(1 for r in factor_results if r["status"] == "PENDING")
        error_count = sum(1 for r in factor_results if r["status"] == "ERROR")
        submitted_count = len(submitted_factors)
        cached_count = sum(1 for r in factor_results if r.get("from_cache"))

        summary_lines = []
        summary_lines.append(f"**WQB 4候选因子提交检查结果** | 共 {len(factor_results)} 个因子")
        summary_lines.append("")
        summary_lines.append(
            f"✅ 通过: {pass_count} | ❌ 未通过: {fail_count} | "
            f"⏳ 待定: {pending_count} | ⚠️ 错误: {error_count} | 📤 已提交: {submitted_count}"
        )
        if cached_count > 0:
            summary_lines.append(f"（其中 {cached_count} 个来自状态库缓存，未重复调用API）")
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
            cache_tag = " [缓存]" if r.get("from_cache") else ""
            sharpe_val = r.get("sharpe")
            sharpe_str = f"{sharpe_val:.2f}" if sharpe_val else "N/A"
            fitness_val = r.get("fitness")
            fitness_str = f"{fitness_val:.2f}" if fitness_val else "N/A"
            summary_lines.append(
                f"- {r['factor_name']}: {status_str} (Sharpe={sharpe_str}, "
                f"Fitness={fitness_str}, {sc_str}){submit_tag}{cache_tag}"
            )

        summary_lines.append("")
        summary_lines.append(f"详细报告: [wqb_4candidates_submit_report.md](computer://{abs_report_path})")

        message = "\n".join(summary_lines)

        # 提交结果
        if sdk:
            await sdk.submit_result(
                result_mode=actual_mode,
                status="success",
                message=message,
                data={
                    "report_path": report_path,
                    "report_abs_path": abs_report_path,
                    "total_count": len(factor_results),
                    "pass_count": pass_count,
                    "fail_count": fail_count,
                    "pending_count": pending_count,
                    "error_count": error_count,
                    "submitted_count": submitted_count,
                    "cached_count": cached_count,
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
                            "turnover": r.get("turnover"),
                            "submitted": r.get("submitted", False),
                            "from_cache": r.get("from_cache", False),
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
