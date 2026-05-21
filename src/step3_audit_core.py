"""CLI 演示:对单条款执行完整审计流程(用于离线快速验证)。

用法:
    cd src
    python step3_audit_core.py
"""
import os
import sys
import json

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
sys.path.insert(0, SRC_DIR)

from audit_core import AuditCore

VECTOR_DB_DIR = os.path.join(BASE_DIR, "data", "vector_db")
HISTORICAL_DB_DIR = os.path.join(BASE_DIR, "data", "historical_db")
RULES_CSV = os.path.join(SRC_DIR, "rules.csv")


def main():
    core = AuditCore(
        vector_db_dir=VECTOR_DB_DIR,
        historical_db_dir=HISTORICAL_DB_DIR,
        rules_csv=RULES_CSV,
    )
    print("就绪状态:", core.is_ready())

    clauses = [
        "甲方(借款人)若未能按期偿还借款,需向乙方(出借人)支付日利率2%的违约金,且乙方有权单方面处置甲方名下所有财产,无需经过甲方同意。",
        "双方应对在合作过程中获悉的对方商业秘密承担保密义务,期限自合同签订之日起至合同终止后2年。",
        "争议解决方式由甲方单方决定,可选择诉讼或仲裁。",
    ]

    for i, c in enumerate(clauses, 1):
        print(f"\n========= 测试条款 {i} =========")
        print(c)
        result = core.audit(c)
        print(json.dumps({
            "risk_type": result["risk_type"],
            "level": result["level"],
            "rpn": result["rpn"],
            "formula": result["formula"],
            "confidence": result["confidence"],
            "need_review": result["need_review"],
            "rule_hits": [h["rule_id"] for h in result["rule_hits"]],
            "timing": result["timing"],
            "reason": result["reason"][:200],
            "suggestion": result["suggestion"][:200],
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
