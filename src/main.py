"""FastAPI 入口:合同条款智能审计系统。

- /audit         单条款审计
- /upload        文件上传 → 解析 → 审计
- /export        导出 txt/docx/pdf
- /files/{name}  下载文件
- /history/add   勾选'采纳'入历史库
- /history       浏览历史采纳建议
- /health        健康检查
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from typing import List, Optional, Dict, Any

# ===== 路径与镜像 =====
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

# Windows 控制台默认 GBK,无法输出 emoji/部分 Unicode → 强制改 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

VECTOR_DB_DIR = os.path.join(BASE_DIR, "data", "vector_db")
HISTORICAL_DB_DIR = os.path.join(BASE_DIR, "data", "historical_db")
HISTORICAL_DOC_DIR = os.path.join(BASE_DIR, "data", "historical_documents")
RULES_CSV = os.path.join(SRC_DIR, "rules.csv")
EXPORT_DIR = os.path.join(BASE_DIR, "data", "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)
os.makedirs(HISTORICAL_DOC_DIR, exist_ok=True)

# ===== 业务模块 =====
from audit_core import AuditCore
from clause_splitter import split_contract
from parsers import parse_upload
from report_exporter import export_docx, export_pdf, export_txt
from revision_engine import RevisionEngine

# ===== FastAPI =====
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

print("正在初始化模型、知识库与规则引擎...")
core = AuditCore(
    vector_db_dir=VECTOR_DB_DIR,
    historical_db_dir=HISTORICAL_DB_DIR,
    rules_csv=RULES_CSV,
)
readiness = core.is_ready()
print("✅ 初始化完成:", readiness)

app = FastAPI(title="合同条款智能审计系统", version="2.0")
# CORS: 开发环境允许 localhost，生产环境应限制为具体域名
# 注意: allow_origins=["*"] 与 allow_credentials=True 同时使用存在安全风险
_ALLOW_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOW_ORIGINS,
    allow_credentials="*" not in _ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuditRequest(BaseModel):
    clause: str


class HistoryAddRequest(BaseModel):
    clause: str
    risk_type: str
    risk_level: str
    suggestion: str


class DocumentAuditRequest(BaseModel):
    content: str
    filename: str = ""


class RuleItem(BaseModel):
    rule_id: str
    clause_type: str
    pattern: str
    risk_level: str
    reason: str
    suggestion: str


class RuleTestRequest(BaseModel):
    pattern: str
    clause: str


class LLMConfigRequest(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""


# ===== 内存任务存储（本地部署，进程内存储；重启丢失） =====
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field


@dataclass
class DocumentAuditJob:
    job_id: str
    filename: str
    original_content: str
    clauses: List[dict]
    status: str = "pending"          # pending / running / completed / failed
    results: List[dict] = field(default_factory=list)
    progress: dict = field(default_factory=lambda: {"done": 0, "total": 0})
    created_at: float = field(default_factory=time.time)


document_jobs: Dict[str, DocumentAuditJob] = {}
rev_engine = RevisionEngine(core.llm)


import json as _json


def _save_document_history(job: DocumentAuditJob) -> None:
    """将完成的审计任务持久化到文件系统。"""
    results = sorted(job.results, key=lambda x: x["index"])
    summary = {"high": 0, "mid": 0, "low": 0, "total": len(job.clauses)}
    for r in results:
        lvl = r.get("audit", {}).get("level", "")
        if "高" in lvl:
            summary["high"] += 1
        elif "中" in lvl:
            summary["mid"] += 1
        elif "低" in lvl:
            summary["low"] += 1
    record = {
        "doc_id": job.job_id,
        "filename": job.filename,
        "created_at": job.created_at,
        "original_content": job.original_content,
        "clauses": results,
        "summary": summary,
    }
    path = os.path.join(HISTORICAL_DOC_DIR, f"{job.job_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(record, f, ensure_ascii=False, indent=2)


def _list_document_history() -> List[dict]:
    """列出所有历史合同审计记录（按时间倒序）。"""
    items = []
    try:
        files = sorted(os.listdir(HISTORICAL_DOC_DIR), reverse=True)
    except Exception:
        return items
    for fname in files:
        if not fname.endswith(".json"):
            continue
        path = os.path.join(HISTORICAL_DOC_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            s = data.get("summary", {})
            items.append({
                "doc_id": data.get("doc_id", fname.replace(".json", "")),
                "filename": data.get("filename", ""),
                "created_at": data.get("created_at", 0),
                "clause_count": s.get("total", 0),
                "high_count": s.get("high", 0),
                "mid_count": s.get("mid", 0),
                "low_count": s.get("low", 0),
            })
        except Exception:
            continue
    return items


def _get_document_history(doc_id: str) -> Optional[dict]:
    """读取单条历史合同审计详情。"""
    path = os.path.join(HISTORICAL_DOC_DIR, f"{doc_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return None


def _run_document_audit(job: DocumentAuditJob) -> None:
    """后台线程：逐条审计整份合同，中高风险的生成修订条款。"""
    job.status = "running"
    total = len(job.clauses)
    job.progress["total"] = total

    def audit_one(c: dict) -> dict:
        result = core.audit(c["text"])
        level = result.get("level", "") or result.get("risk_level", "")
        # 中高风险生成修订条款
        if "高" in level or "中" in level:
            result["revised_text"] = rev_engine.revise(c["text"], result)
        else:
            result["revised_text"] = c["text"]
        return {
            "index": c["index"],
            "title": c["title"],
            "text": c["text"],
            "start": c["start"],
            "end": c["end"],
            "audit": result,
        }

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(audit_one, c): c for c in job.clauses}
        for future in as_completed(futures):
            c = futures[future]
            try:
                res = future.result(timeout=25)
                job.results.append(res)
            except Exception as e:
                job.results.append({
                    "index": c["index"],
                    "title": c["title"],
                    "text": c["text"],
                    "start": c["start"],
                    "end": c["end"],
                    "audit": {
                        "level": "中风险",
                        "risk_type": "其他",
                        "reason": f"审计异常: {e}",
                        "suggestion": "请稍后重试",
                        "revised_text": c["text"],
                        "confidence": 0.0,
                        "rpn": 0,
                        "risk_score": {},
                    },
                })
            job.progress["done"] += 1

    job.status = "completed"
    _save_document_history(job)
    # 保留 10 分钟后自动清理
    def _cleanup():
        time.sleep(600)
        document_jobs.pop(job.job_id, None)
    threading.Thread(target=_cleanup, daemon=True).start()


# ===== 健康检查 =====
@app.get("/")
async def root():
    return {
        "service": "合同条款智能审计系统",
        "version": "2.0",
        "ready": core.is_ready(),
    }


@app.get("/health")
async def health():
    info = core.is_ready()
    info["historical_count"] = core.history.count()
    return info


# ===== 单条款审计 =====
@app.post("/audit")
async def audit_clause(req: AuditRequest):
    if not req.clause.strip():
        raise HTTPException(status_code=400, detail="条款内容不能为空")
    result = core.audit(req.clause)
    return result


# ===== 兼容旧表单接口 =====
@app.post("/audit/form")
async def audit_clause_form(clause: str = Form(...)):
    if not clause.strip():
        raise HTTPException(status_code=400, detail="条款内容不能为空")
    return core.audit(clause)


# ===== 文件上传 → 解析 → 审计 =====
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    t0 = time.time()
    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取上传文件失败:{e}")
    text, err = parse_upload(file.filename or "", file_bytes)
    parse_elapsed = round(time.time() - t0, 3)
    if err and not text:
        raise HTTPException(status_code=400, detail=err)

    audit = core.audit(text or "")
    audit["filename"] = file.filename
    audit["content"] = text
    audit["timing"]["parse"] = parse_elapsed
    audit["timing"]["total"] = round(
        sum(v for v in audit["timing"].values() if isinstance(v, (int, float))) - audit["timing"].get("total", 0),
        3,
    )
    if err:
        audit["parse_warning"] = err
    return audit


# ===== 报告导出 =====
@app.post("/export")
async def export_report(
    format_type: str = Form(...),
    audit_payload: str = Form(...),
):
    """audit_payload 为 JSON 字符串(前端把 /audit 或 /upload 的返回原样回传)。"""
    import json as _json
    try:
        payload = _json.loads(audit_payload)
    except Exception:
        raise HTTPException(status_code=400, detail="audit_payload 不是合法 JSON")

    if format_type not in {"txt", "docx", "pdf"}:
        raise HTTPException(status_code=400, detail="format_type 仅支持 txt/docx/pdf")

    name = f"audit_{uuid.uuid4().hex[:8]}.{format_type}"
    out_path = os.path.join(EXPORT_DIR, name)
    try:
        if format_type == "txt":
            export_txt(payload, out_path)
        elif format_type == "docx":
            export_docx(payload, out_path)
        else:
            export_pdf(payload, out_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败:{e}")

    return {"code": 200, "filename": name, "format": format_type}


@app.post("/export/revised")
async def export_revised(
    content: str = Form(...),
    format_type: str = Form(...),
    filename: str = Form(""),
):
    if not content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")
    if format_type not in {"txt", "docx"}:
        raise HTTPException(status_code=400, detail="format_type 仅支持 txt/docx")

    base = (filename or "合同").replace(".txt", "").replace(".docx", "").replace(".pdf", "")
    name = f"revised_{base}_{uuid.uuid4().hex[:8]}.{format_type}"
    out_path = os.path.join(EXPORT_DIR, name)

    try:
        if format_type == "txt":
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            from docx import Document
            from docx.shared import Pt
            doc = Document()
            for line in content.split("\n"):
                p = doc.add_paragraph(line)
                if p.runs:
                    p.runs[0].font.size = Pt(10.5)
            doc.save(out_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败:{e}")

    return {"code": 200, "filename": name, "format": format_type}


# ===== 规则管理 =====
@app.get("/rules")
async def list_rules():
    return {"total": core.rules.rule_count(), "items": core.rules.list_rules()}


@app.post("/rules")
async def add_rule(req: RuleItem):
    ok = core.rules.add_rule(
        req.rule_id, req.clause_type, req.pattern,
        req.risk_level, req.reason, req.suggestion,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="规则格式非法或正则编译失败")
    return {"code": 200, "total": core.rules.rule_count()}


@app.put("/rules/{rule_id}")
async def update_rule(rule_id: str, req: RuleItem):
    ok = core.rules.update_rule(
        rule_id,
        rule_id=req.rule_id,
        clause_type=req.clause_type,
        pattern=req.pattern,
        risk_level=req.risk_level,
        reason=req.reason,
        suggestion=req.suggestion,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="规则不存在或正则编译失败")
    return {"code": 200, "total": core.rules.rule_count()}


@app.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    ok = core.rules.delete_rule(rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"code": 200, "total": core.rules.rule_count()}


@app.post("/rules/reload")
async def reload_rules():
    core.rules.reload()
    return {"code": 200, "total": core.rules.rule_count()}


@app.post("/rules/test")
async def test_rule(req: RuleTestRequest):
    import re as _re
    try:
        r = _re.compile(req.pattern)
        m = r.search(req.clause)
        return {"hit": bool(m), "matched": m.group(0)[:80] if m else ""}
    except _re.error as e:
        raise HTTPException(status_code=400, detail=f"正则编译失败: {e}")


# ===== LLM 配置管理 =====
@app.get("/config")
async def get_config():
    """获取当前 LLM 配置（API Key 脱敏）。"""
    return core.llm.get_config()


@app.post("/config")
async def update_config(req: LLMConfigRequest):
    """更新 LLM 配置，立即生效。至少提供一个字段。"""
    if not req.api_key and not req.base_url and not req.model:
        raise HTTPException(status_code=400, detail="至少提供一个配置字段(api_key/base_url/model)")
    result = core.update_llm_config(
        api_key=req.api_key,
        base_url=req.base_url,
        model=req.model,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["config"].get("error", "配置更新失败"))
    return {"code": 200, "message": "配置已更新", "config": result["config"]}


@app.get("/files/{filename}")
async def download_file(filename: str):
    safe = os.path.basename(filename)
    path = os.path.join(EXPORT_DIR, safe)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, media_type="application/octet-stream", filename=safe)


# ===== 整份合同批量审计 =====
@app.post("/audit/document")
async def audit_document(req: DocumentAuditRequest, background_tasks: BackgroundTasks):
    if not req.content or not req.content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")
    clauses = split_contract(req.content)
    job = DocumentAuditJob(
        job_id=str(uuid.uuid4()),
        filename=req.filename,
        original_content=req.content,
        clauses=[{"index": c.index, "title": c.title, "text": c.text, "start": c.start, "end": c.end} for c in clauses],
    )
    document_jobs[job.job_id] = job
    background_tasks.add_task(_run_document_audit, job)
    return {"job_id": job.job_id, "total": len(clauses), "status": "pending"}


@app.get("/audit/document/{job_id}")
async def get_document_audit(job_id: str):
    job = document_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    results = sorted(job.results, key=lambda x: x["index"])
    summary = {"high": 0, "mid": 0, "low": 0, "total": len(job.clauses)}
    for r in results:
        lvl = r.get("audit", {}).get("level", "")
        if "高" in lvl:
            summary["high"] += 1
        elif "中" in lvl:
            summary["mid"] += 1
        elif "低" in lvl:
            summary["low"] += 1
    return {
        "job_id": job.job_id,
        "status": job.status,
        "filename": job.filename,
        "original_content": job.original_content,
        "progress": job.progress,
        "clauses": results,
        "summary": summary,
    }


# ===== 历史采纳建议库 =====
@app.post("/history/add")
async def history_add(req: HistoryAddRequest):
    if not core.history.is_ready():
        raise HTTPException(status_code=503, detail="历史库未就绪")
    rid = core.history.add(req.clause, req.risk_type, req.risk_level, req.suggestion)
    if not rid:
        raise HTTPException(status_code=500, detail="入库失败")
    return {"code": 200, "record_id": rid, "total": core.history.count()}


@app.get("/history")
async def history_list(limit: int = 50):
    return {"total": core.history.count(), "items": core.history.list_recent(limit)}


# ===== 历史合同审计记录 =====
@app.get("/history/documents")
async def list_document_history():
    items = _list_document_history()
    return {"total": len(items), "items": items}


@app.get("/history/documents/{doc_id}")
async def get_document_history(doc_id: str):
    data = _get_document_history(doc_id)
    if not data:
        raise HTTPException(status_code=404, detail="记录不存在")
    return data


# ===== 启动 =====
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
