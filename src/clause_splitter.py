"""合同条款智能切分器。

按"第X条"识别条款边界，记录每条在原文中的 start/end 字符位置，
供后端批量审计与前端原文标注使用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


@dataclass
class ContractClause:
    index: int
    title: str
    text: str
    start: int
    end: int


# 匹配"第X条"，其中 X 可以是中文数字或阿拉伯数字
_CLAUSE_HEAD = re.compile(
    r'^\s*(第\s*[一二三四五六七八九十百\d]+\s*条)\s*',
    re.MULTILINE,
)

# fallback：匹配纯数字编号如 "1." "1、" "1．"
_FALLBACK_HEAD = re.compile(
    r'^\s*(\d+[\.．、])\s*',
    re.MULTILINE,
)


def split_contract(text: str) -> List[ContractClause]:
    """将合同文本切分为条款列表，保留每条在原文中的位置。"""
    text = text or ""
    matches = list(_CLAUSE_HEAD.finditer(text))

    if not matches:
        matches = list(_FALLBACK_HEAD.finditer(text))

    if not matches:
        t = text.strip()
        return [ContractClause(0, "", t, 0, len(text))] if t else []

    clauses: List[ContractClause] = []
    for i, m in enumerate(matches):
        start = m.start()
        title = m.group(1).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        clause_text = text[start:end].rstrip()
        if clause_text:
            clauses.append(ContractClause(i, title, clause_text, start, end))
    return clauses
