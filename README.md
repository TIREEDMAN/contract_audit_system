# 合同条款智能审计系统 v2.0

基于大模型 + 检索增强 + 规则引擎 + P×L×D 风险量化的合同条款审计系统。
配套谢鹏本科毕业设计论文实现,严格对齐论文章节 2/3/4 的方法与公式。

---

## 一、核心特性

| 模块 | 实现 | 对应论文章节 |
|------|------|--------------|
| 大模型 | GLM-4.7-Flash(智谱 AI,OpenAI 兼容 SDK) | 2.2 / 3.2.2 |
| 嵌入模型 | `paraphrase-MiniLM-L6-v2`(384 维) | 2.4 |
| 向量检索 | numpy 余弦相似度 + 法规/模板/判例三类知识源 | 3.2.3 |
| 历史采纳库 | 独立向量集合,用户勾选"采纳"自动入库 | 3.3 扩展 |
| 提示工程 | CoT 四步推理 + 小样本(4 类×10 例) + 自一致性(3 次投票) | 3.2.4 |
| 规则引擎 | CSV 驱动正则,21 条核心规则,与 LLM 并行执行后融合 | 3.3 |
| 风险评分 | RPN = P × L × D,L = log10(A×M) + 5,D = 11 - E_sys - 3·E_expert | 3.4 |
| 三色分级 | 高(>343 红)/ 中(125-343 黄)/ 低(≤125 绿) | 3.4.3 |
| 文件解析 | PyMuPDF(PDF,仅文本版)+ python-docx + txt | 3.5 |
| 报告导出 | docx(Word 批注)+ pdf(中文字体)+ txt | 3.5 |
| 前端 | 原生 HTML5 + CSS Grid(无 Vue,无构建依赖) | 4.2 |

> **PDF 限制**:仅支持文本版 PDF,扫描件请先转换为 docx 或 txt。

---

## 二、目录结构

```
contract_audit_system-main/
├── index.html                ← 前端单页,直接浏览器打开
├── requirements.txt
├── .env.example              ← 环境变量样例
├── README.md
├── src/
│   ├── main.py               ← FastAPI 入口
│   ├── audit_core.py         ← 审计编排
│   ├── llm_client.py         ← GLM 客户端 + 自一致性投票
│   ├── prompts.py            ← CoT 系统提示 + 40 条小样本
│   ├── risk_model.py         ← P×L×D 评分
│   ├── rule_engine.py        ← 规则引擎
│   ├── rules.csv             ← 21 条审计规则
│   ├── rag_retriever.py      ← 向量检索器
│   ├── historical_kb.py      ← 历史采纳库
│   ├── parsers.py            ← 文件解析
│   ├── report_exporter.py    ← txt/docx/pdf 导出
│   ├── step1_data_process.py ← 数据预处理(可选)
│   ├── step2_build_rag_db.py ← 构建主知识库
│   └── step3_audit_core.py   ← CLI 单条款审计 demo
├── data/
│   ├── knowledge_base/
│   │   ├── regulations/      ← 法规(民法典/合同法司法解释...)
│   │   ├── templates/        ← 模板条款
│   │   └── cases/            ← 典型判例
│   ├── vector_db/            ← 自动生成,主向量库(embeddings.npy + index.json)
│   ├── historical_db/        ← 自动生成,历史采纳库
│   └── exports/              ← 自动生成,导出报告
```

---

## 三、安装与运行

### 1. 创建虚拟环境并安装依赖

```bash
cd contract_audit_system-main
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`:

```ini
LLM_API_KEY=8d6e3cb9755d4dc594b09d1deeb78521.jyUQfk3WKIgxQN4X
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
LLM_MODEL=GLM-4.7-Flash
HF_ENDPOINT=https://hf-mirror.com
```

默认已内置 GLM-4.7-Flash 免费模型 Key,开箱即用。
如需更换模型或 Key,修改 `.env` 中的 `LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL` 即可。

可通过 `set LLM_API_KEY=...`(Windows)或 `export LLM_API_KEY=...`(\*nix)
临时注入,无需 .env 文件。

### 3. 构建主知识库(首次必须)

```bash
cd src
python step2_build_rag_db.py
```

脚本会读取 `data/knowledge_base/{regulations,templates,cases}/` 下所有
`.txt`,按类别切分后生成 `embeddings.npy` + `index.json` 存入 `data/vector_db/`。
首次运行会下载嵌入模型(约 90MB,通过 hf-mirror 国内镜像)。

### 4. 启动后端

```bash
cd src
python main.py
```

监听 `http://127.0.0.1:8000`。
启动日志会打印 LLM / 向量库 / 历史库 / 规则数的就绪状态。

### 5. 打开前端

双击 `index.html` 在浏览器中打开,或用本地静态服务托管。
前端默认连接 `http://127.0.0.1:8000`,如需修改请编辑 `index.html` 顶部
`API_BASE` 常量。

---

## 四、关键 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查,返回各模块就绪状态与历史库条数 |
| POST | `/audit` | 单条款审计(JSON body: `{"clause": "..."}`) |
| POST | `/upload` | 上传 txt / docx / pdf,自动解析后审计 |
| POST | `/export` | 导出 txt / docx / pdf 报告 |
| GET | `/files/{filename}` | 下载导出文件 |
| POST | `/history/add` | 勾选"采纳"入历史库 |
| GET | `/history?limit=50` | 列出最近采纳记录 |

---

## 五、前端使用

1. **直接审计**:左侧粘贴条款 → 点击「开始审计」。
2. **文件审计**:上传 txt/docx/pdf → 自动解析并审计整段。
3. **结果详情**:右侧展示风险类型/等级、修改建议、置信度、是否需复核;
   折叠面板展示 P×L×D 公式、各阶段耗时、命中规则、引用法条、相似历史。
4. **采纳入库**:确认建议有用后点击「✅ 采纳建议入库」→
   写入 `historical_adopted` collection,后续相似条款会自动检索。
5. **历史浏览**:右上「📚 历史采纳」抽屉查看全部入库记录。
6. **导出报告**:txt(纯文本)/ docx(Word 含批注)/ pdf(中文字体,三色高亮)。

---

## 六、系统演示

<video src="assets/demo.mp4" controls width="100%">
  您的浏览器不支持视频标签。
</video>

> 演示: 合同上传 → 条款自动切分 → 逐条审计 → 风险高亮 → 修订建议 → 导出报告 的完整流程。

---

## 七、风险评分公式(对应论文 3.4)

```
P = 概率系数  ∈ {2(低), 5(中), 9(高)}     # LLM 等级 + 关键词修正
L = log10(A × M) + 5                       # A=金额万元, M=放大因子(1~3)
D = 11 - E_sys - 3 × E_expert              # E_sys: 规则命中=2 否则=1
                                            # E_expert: 需复核=1 否则=0
RPN = P × L × D
等级:RPN > 343 高(红 #FFCCCC),125 < RPN ≤ 343 中(黄 #FFFFCC),
     RPN ≤ 125 低(绿 #CCFFCC)
```

---

## 八、常见问题

**Q1:启动时报 `huggingface_hub` 下载超时**
A:已默认设置 `HF_ENDPOINT=https://hf-mirror.com`。若仍超时,可手动下载
`paraphrase-MiniLM-L6-v2` 到本地后修改 `rag_retriever.py` 中 `EMBEDDING_MODEL`
为本地路径。

**Q2:LLM 返回 401/403 认证错误**
A:检查 `.env` 中的 `LLM_API_KEY` 是否有效,以及 `LLM_BASE_URL` 是否与
Key 所属平台对应(GLM 用 `https://open.bigmodel.cn/api/paas/v4/`)。

**Q3:Word 导出在 WPS 中看不到批注**
A:`add_comment` 需要 Word 2010 以上;WPS 支持但需切换到「审阅」选项卡查看。

**Q4:PDF 导出中文乱码**
A:导出模块会自动注册 `C:\Windows\Fonts\simhei.ttf / msyh.ttc / simsun.ttc`,
若上述字体均缺失,可自行将任意中文 TTF 放入该目录,或修改
`report_exporter.py` 中 `_register_chinese_font()` 的搜索路径。

**Q5:扫描版 PDF 报"未提取到文本"**
A:本系统不集成 OCR,请使用 Acrobat / WPS 将扫描件转为可复制文本的 docx
或 txt 后重试。

---

## 九、离线 CLI 自测

```bash
cd src
python step3_audit_core.py
```

会对三条示例条款执行完整审计流程,打印 RPN、命中规则、各阶段耗时,
用于无前端环境下的快速验证。
