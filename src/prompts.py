import json

"""提示词与小样本示例。对应论文 2.3 节与 4.3.3 节。

四类高频条款:违约责任、保密条款、不可抗力、争议解决
小样本策略:每类 10 例,共 40 例,嵌入 system 消息。
推理模板:CoT 四步(识别→检索→评估→建议)。
"""

CLAUSE_TYPES = ["违约责任", "保密条款", "不可抗力", "争议解决"]

FEW_SHOT_EXAMPLES = [
    # ===== 违约责任 (10例) =====
    {
        "type": "违约责任",
        "input": "若甲方逾期付款,应按日万分之五支付违约金。",
        "output": {
            "risk_type": "违约责任",
            "risk_level": "低",
            "reason": "违约金比例(日万分之五,折合年化约18%)在司法实务认可的合理区间内。",
            "suggestion": "建议保留,条款合规。",
            "confidence": 0.92,
        },
    },
    {
        "type": "违约责任",
        "input": "甲方违约的,应向乙方支付合同总价50%的违约金。",
        "output": {
            "risk_type": "违约责任",
            "risk_level": "高",
            "reason": "违约金过高(总价50%),依据《民法典》第585条,远超实际损失30%的司法红线,可能被法院调减。",
            "suggestion": "建议调整为总价10%-20%区间,并明确以实际损失为限。",
            "confidence": 0.95,
        },
    },
    {
        "type": "违约责任",
        "input": "任何一方违约,守约方有权解除合同并要求赔偿全部损失,包括间接损失与可得利益损失。",
        "output": {
            "risk_type": "违约责任",
            "risk_level": "中",
            "reason": "赔偿范围涵盖间接损失与可得利益损失,可能因举证困难产生争议。",
            "suggestion": "建议明确可得利益损失的计算方式与上限。",
            "confidence": 0.86,
        },
    },
    {
        "type": "违约责任",
        "input": "甲方迟延履行,自迟延之日起按未付款金额日万分之三计算违约金。",
        "output": {
            "risk_type": "违约责任",
            "risk_level": "低",
            "reason": "违约金计算基数与比例均清晰,起算时间明确。",
            "suggestion": "条款表述完整,建议保留。",
            "confidence": 0.9,
        },
    },
    {
        "type": "违约责任",
        "input": "乙方有权单方面处置甲方名下所有财产,无需经过甲方同意。",
        "output": {
            "risk_type": "违约责任",
            "risk_level": "高",
            "reason": "授予单方处置权违反《民法典》第207条物权平等保护原则,且涉嫌违反法定程序。",
            "suggestion": "应删除该条款,改为通过法院或仲裁机构申请财产保全的途径。",
            "confidence": 0.97,
        },
    },
    {
        "type": "违约责任",
        "input": "无论何种原因导致违约,违约方承担无限连带责任。",
        "output": {
            "risk_type": "违约责任",
            "risk_level": "高",
            "reason": "无限连带责任未区分过错程度,且未设上限,有违公平原则。",
            "suggestion": "建议改为按实际过错与损失比例承担,并设定责任上限。",
            "confidence": 0.94,
        },
    },
    {
        "type": "违约责任",
        "input": "本合同任一方违约,守约方应在30日内书面通知违约方,逾期不通知视为放弃追究权利。",
        "output": {
            "risk_type": "违约责任",
            "risk_level": "中",
            "reason": "30日通知期较短,且失权后果严苛,可能造成守约方权利失衡。",
            "suggestion": "建议延长通知期至60-90日,或删除失权条款。",
            "confidence": 0.85,
        },
    },
    {
        "type": "违约责任",
        "input": "甲方违约的,除支付违约金外,还应当承担乙方因此支出的律师费、诉讼费、保全费、差旅费等所有费用。",
        "output": {
            "risk_type": "违约责任",
            "risk_level": "低",
            "reason": "实现债权费用条款符合《民法典》第584条规定,合理。",
            "suggestion": "建议明确各项费用须以正式票据为凭。",
            "confidence": 0.88,
        },
    },
    {
        "type": "违约责任",
        "input": "违约责任另行协商。",
        "output": {
            "risk_type": "违约责任",
            "risk_level": "高",
            "reason": "条款空白,无任何违约后果约定,实际等同于无违约责任。",
            "suggestion": "必须补充具体违约金、赔偿方式与解除条件。",
            "confidence": 0.96,
        },
    },
    {
        "type": "违约责任",
        "input": "如因甲方原因导致项目延期超过15日,乙方有权解除合同,甲方已支付款项不予退还且应另行赔偿损失。",
        "output": {
            "risk_type": "违约责任",
            "risk_level": "中",
            "reason": "'已付款不予退还+另行赔偿'构成重复救济,可能被认定为变相高额违约金。",
            "suggestion": "建议二选一,或明确退款与赔偿的计算关系。",
            "confidence": 0.83,
        },
    },
    # ===== 保密条款 (10例) =====
    {
        "type": "保密条款",
        "input": "双方应对在合作过程中获悉的对方商业秘密承担保密义务,期限自合同签订之日起至合同终止后2年。",
        "output": {
            "risk_type": "保密条款",
            "risk_level": "低",
            "reason": "保密期限2年合理,主体与范围明确。",
            "suggestion": "建议补充保密信息的具体范围或例外情形。",
            "confidence": 0.9,
        },
    },
    {
        "type": "保密条款",
        "input": "乙方对甲方所有信息承担永久保密义务,违约赔偿不低于100万元。",
        "output": {
            "risk_type": "保密条款",
            "risk_level": "高",
            "reason": "'所有信息'范围过广,'永久'期限不合理,固定100万赔偿可能被认定为过高。",
            "suggestion": "建议限定保密信息范围(标注秘密的资料),期限改为5年内,赔偿改为按实际损失。",
            "confidence": 0.93,
        },
    },
    {
        "type": "保密条款",
        "input": "保密信息指标注为'机密'或'秘密'的书面材料,以及双方书面确认的口头信息。",
        "output": {
            "risk_type": "保密条款",
            "risk_level": "低",
            "reason": "保密信息定义清晰,有明确的识别标准。",
            "suggestion": "条款合规,建议保留。",
            "confidence": 0.91,
        },
    },
    {
        "type": "保密条款",
        "input": "下列情形不构成违约:(1)公知信息;(2)接收方独立开发;(3)依法律或政府要求披露。",
        "output": {
            "risk_type": "保密条款",
            "risk_level": "低",
            "reason": "保密例外列举完整,符合行业惯例。",
            "suggestion": "建议在依法披露后增加'及时通知对方'要求。",
            "confidence": 0.89,
        },
    },
    {
        "type": "保密条款",
        "input": "未经甲方书面同意,乙方不得将合作事宜告知任何第三方,包括但不限于关联公司、律师、会计师。",
        "output": {
            "risk_type": "保密条款",
            "risk_level": "中",
            "reason": "禁止告知律师、会计师等专业顾问过于严苛,影响乙方正常经营。",
            "suggestion": "建议允许向负有保密义务的专业顾问披露。",
            "confidence": 0.84,
        },
    },
    {
        "type": "保密条款",
        "input": "乙方员工离职后,仍应对在职期间获悉的甲方信息保密,期限不限。",
        "output": {
            "risk_type": "保密条款",
            "risk_level": "中",
            "reason": "对员工施加无期限保密义务可能违反劳动法相关规定。",
            "suggestion": "建议改为离职后5年内,且明确商业秘密的认定标准。",
            "confidence": 0.82,
        },
    },
    {
        "type": "保密条款",
        "input": "合同终止后,接收方应立即销毁或返还披露方提供的全部保密资料,并出具书面证明。",
        "output": {
            "risk_type": "保密条款",
            "risk_level": "低",
            "reason": "保密资料处置约定清晰,有书面证明便于举证。",
            "suggestion": "条款合规,建议保留。",
            "confidence": 0.93,
        },
    },
    {
        "type": "保密条款",
        "input": "甲方未约定具体保密期限和范围,但要求乙方保密。",
        "output": {
            "risk_type": "保密条款",
            "risk_level": "高",
            "reason": "保密期限与范围均不明确,实际履行中易生争议。",
            "suggestion": "必须明确保密期限(如3-5年)和保密信息范围。",
            "confidence": 0.91,
        },
    },
    {
        "type": "保密条款",
        "input": "因接收方故意泄密造成披露方损失的,接收方按实际损失赔偿,并支付不低于损失金额30%的惩罚性违约金。",
        "output": {
            "risk_type": "保密条款",
            "risk_level": "中",
            "reason": "实际损失+惩罚性违约金双重救济,但比例尚在合理区间。",
            "suggestion": "建议明确'故意'的认定标准,避免争议。",
            "confidence": 0.86,
        },
    },
    {
        "type": "保密条款",
        "input": "甲方保留所有商业秘密的所有权,乙方不得以任何方式申请专利、注册商标或主张权利。",
        "output": {
            "risk_type": "保密条款",
            "risk_level": "低",
            "reason": "知识产权归属约定明确,有效防止权利争议。",
            "suggestion": "建议补充'乙方在合作中产生的衍生成果'的归属约定。",
            "confidence": 0.88,
        },
    },
    # ===== 不可抗力 (10例) =====
    {
        "type": "不可抗力",
        "input": "因地震、洪水、战争等不可抗力导致一方不能履行合同的,部分或全部免除责任。",
        "output": {
            "risk_type": "不可抗力",
            "risk_level": "低",
            "reason": "符合《民法典》第180条规定,列举明确。",
            "suggestion": "建议补充'通知义务与证明文件'的具体要求。",
            "confidence": 0.91,
        },
    },
    {
        "type": "不可抗力",
        "input": "任何政府行为、政策变动均视为不可抗力,免除甲方所有责任。",
        "output": {
            "risk_type": "不可抗力",
            "risk_level": "高",
            "reason": "扩大不可抗力范围,把一般商业风险纳入,违反《民法典》第180条不可抗力的客观性、不可预见性、不可避免性、不可克服性要件。",
            "suggestion": "应限定为直接导致履行不能的、不可预见且不可避免的政府行为。",
            "confidence": 0.94,
        },
    },
    {
        "type": "不可抗力",
        "input": "因新冠疫情或其变种导致延迟履行,延迟期间不视为违约,但应在3日内书面通知对方。",
        "output": {
            "risk_type": "不可抗力",
            "risk_level": "低",
            "reason": "明确疫情情形与通知期限,符合最高院疫情司法解释。",
            "suggestion": "建议补充'提供主管部门证明'的要求。",
            "confidence": 0.89,
        },
    },
    {
        "type": "不可抗力",
        "input": "遭遇不可抗力的一方应在15日内通知对方并提供证明,逾期通知造成损失扩大的部分自行承担。",
        "output": {
            "risk_type": "不可抗力",
            "risk_level": "低",
            "reason": "通知期与举证责任合理,符合《民法典》第590条减损义务。",
            "suggestion": "条款规范,建议保留。",
            "confidence": 0.92,
        },
    },
    {
        "type": "不可抗力",
        "input": "不可抗力持续超过60日,任一方有权解除合同且不承担违约责任。",
        "output": {
            "risk_type": "不可抗力",
            "risk_level": "低",
            "reason": "符合《民法典》第563条法定解除权规定。",
            "suggestion": "条款合理,建议保留。",
            "confidence": 0.9,
        },
    },
    {
        "type": "不可抗力",
        "input": "甲方因供应商断货导致延迟交货,视为不可抗力。",
        "output": {
            "risk_type": "不可抗力",
            "risk_level": "高",
            "reason": "供应商断货属于一般商业风险,不构成法定不可抗力。",
            "suggestion": "应删除该约定,或改为通过转包、备选供应商保障履行。",
            "confidence": 0.93,
        },
    },
    {
        "type": "不可抗力",
        "input": "不可抗力发生时,合同自动终止,双方互不承担责任。",
        "output": {
            "risk_type": "不可抗力",
            "risk_level": "中",
            "reason": "自动终止过于绝对,未给予协商或部分履行的机会。",
            "suggestion": "建议改为'有权协商变更或解除合同',保留弹性。",
            "confidence": 0.84,
        },
    },
    {
        "type": "不可抗力",
        "input": "因不可抗力导致一方部分履行不能的,应根据影响程度部分免除责任,已履行部分仍属有效。",
        "output": {
            "risk_type": "不可抗力",
            "risk_level": "低",
            "reason": "部分免责与已履行有效的约定合理。",
            "suggestion": "条款合规,建议保留。",
            "confidence": 0.91,
        },
    },
    {
        "type": "不可抗力",
        "input": "战争、罢工、骚乱、政府征用、互联网中断均为不可抗力。",
        "output": {
            "risk_type": "不可抗力",
            "risk_level": "中",
            "reason": "罢工与互联网中断是否构成不可抗力存在争议,需结合具体情形。",
            "suggestion": "建议增加'经各方书面确认'的认定程序。",
            "confidence": 0.79,
        },
    },
    {
        "type": "不可抗力",
        "input": "本合同未约定不可抗力条款。",
        "output": {
            "risk_type": "不可抗力",
            "risk_level": "中",
            "reason": "虽未约定,但《民法典》第180条仍可适用,但缺少通知与解除程序。",
            "suggestion": "建议补充不可抗力定义、通知期限、证明文件、解除条件。",
            "confidence": 0.87,
        },
    },
    # ===== 争议解决 (10例) =====
    {
        "type": "争议解决",
        "input": "因履行本合同发生争议的,双方应友好协商;协商不成的,提交甲方所在地有管辖权的人民法院诉讼解决。",
        "output": {
            "risk_type": "争议解决",
            "risk_level": "低",
            "reason": "约定明确的管辖法院,符合《民事诉讼法》规定。",
            "suggestion": "条款合规,建议保留。",
            "confidence": 0.91,
        },
    },
    {
        "type": "争议解决",
        "input": "争议解决方式由甲方单方决定,可选择诉讼或仲裁。",
        "output": {
            "risk_type": "争议解决",
            "risk_level": "高",
            "reason": "争议解决方式不能由单方决定,涉嫌剥夺乙方诉讼权利。",
            "suggestion": "应在合同中明确约定唯一争议解决方式与机构。",
            "confidence": 0.95,
        },
    },
    {
        "type": "争议解决",
        "input": "争议提交中国国际经济贸易仲裁委员会按其现行有效规则在北京仲裁,裁决终局。",
        "output": {
            "risk_type": "争议解决",
            "risk_level": "低",
            "reason": "仲裁机构、规则、地点、终局性均明确,符合《仲裁法》第16条。",
            "suggestion": "条款合规,建议保留。",
            "confidence": 0.93,
        },
    },
    {
        "type": "争议解决",
        "input": "争议解决既可选择仲裁也可选择诉讼。",
        "output": {
            "risk_type": "争议解决",
            "risk_level": "高",
            "reason": "或裁或诉条款依据《仲裁法司法解释》第7条无效。",
            "suggestion": "必须二选一,建议明确单一争议解决方式。",
            "confidence": 0.96,
        },
    },
    {
        "type": "争议解决",
        "input": "本合同适用中华人民共和国法律,但不包括其冲突法规则。",
        "output": {
            "risk_type": "争议解决",
            "risk_level": "低",
            "reason": "法律适用条款明确,排除冲突法符合涉外合同惯例。",
            "suggestion": "条款合规,建议保留。",
            "confidence": 0.92,
        },
    },
    {
        "type": "争议解决",
        "input": "争议提交某甲所在地仲裁机构仲裁。",
        "output": {
            "risk_type": "争议解决",
            "risk_level": "高",
            "reason": "未指明具体仲裁机构,依据《仲裁法》第18条,仲裁协议无效。",
            "suggestion": "必须明确具体仲裁机构名称(如中国国际经济贸易仲裁委员会)。",
            "confidence": 0.97,
        },
    },
    {
        "type": "争议解决",
        "input": "争议解决前,双方应继续履行合同中不存在争议的部分。",
        "output": {
            "risk_type": "争议解决",
            "risk_level": "低",
            "reason": "持续履行条款符合诚信原则,有利于保护双方利益。",
            "suggestion": "条款合规,建议保留。",
            "confidence": 0.89,
        },
    },
    {
        "type": "争议解决",
        "input": "因合同发生的所有争议,均放弃通过诉讼或仲裁解决,仅可通过协商解决。",
        "output": {
            "risk_type": "争议解决",
            "risk_level": "高",
            "reason": "排除一切司法救济违反《民法典》第533条公平原则与《民事诉讼法》强制性规定。",
            "suggestion": "应删除该条款,明确可通过诉讼或仲裁解决争议。",
            "confidence": 0.96,
        },
    },
    {
        "type": "争议解决",
        "input": "争议解决期间产生的律师费、诉讼费均由败诉方承担。",
        "output": {
            "risk_type": "争议解决",
            "risk_level": "低",
            "reason": "实现债权费用由败诉方承担符合《民法典》第584条。",
            "suggestion": "建议增加'律师费以实际发生且合理为限'。",
            "confidence": 0.88,
        },
    },
    {
        "type": "争议解决",
        "input": "本合同争议由甲方法律部最终裁决。",
        "output": {
            "risk_type": "争议解决",
            "risk_level": "高",
            "reason": "甲方法律部不是法定的仲裁或司法机构,不具有强制执行力,违反公平原则。",
            "suggestion": "必须改为有管辖权的人民法院或合法仲裁机构。",
            "confidence": 0.97,
        },
    },
]


SYSTEM_PROMPT_TEMPLATE = """你是一位资深合同审核专家,精通《中华人民共和国民法典》合同编。
你的任务是依据法律条文与示例,对用户的合同条款进行结构化审计。

【四类高频条款】
- 违约责任:违约金、赔偿、解除权等
- 保密条款:商业秘密、保密期限、违约赔偿
- 不可抗力:免责情形、通知义务、解除条件
- 争议解决:管辖、仲裁、法律适用

【推理步骤(CoT)】
1. 识别:判定条款属于上述四类中的哪一类(或其他)
2. 检索:对照提供的法规条文与判例
3. 评估:从合规性、公平性、可执行性三角度分析风险
4. 建议:给出可直接采纳的修改方案

【输出要求(严格遵守)】
仅输出 JSON 对象,不要附加任何解释文字。结构如下:
{{
  "risk_type": "违约责任|保密条款|不可抗力|争议解决|其他",
  "risk_level": "高|中|低",
  "reason": "100字内,引用具体法条或判例编号",
  "suggestion": "150字内,可直接套用的修改方案",
  "confidence": 0.0-1.0
}}

【小样本示例】
{few_shot}
"""


def build_system_prompt() -> str:
    """组合 system 消息(含全部小样本)。"""
    lines = []
    for ex in FEW_SHOT_EXAMPLES:
        out_json = json.dumps(ex["output"], ensure_ascii=False)
        lines.append(f'示例[{ex["type"]}]\n输入:{ex["input"]}\n输出:{out_json}')
    few_shot = "\n\n".join(lines)
    return SYSTEM_PROMPT_TEMPLATE.format(few_shot=few_shot)


def build_user_prompt(clause: str, law_context: str, historical_context: str = "") -> str:
    """组装 user 消息。"""
    parts = [f"【相关法规条文】\n{law_context or '(无相关法规命中)'}"]
    if historical_context:
        parts.append(f"【历史采纳修改建议】\n{historical_context}")
    parts.append(f"【待审计条款】\n{clause}")
    parts.append("请严格按 JSON 格式输出审计结果:")
    return "\n\n".join(parts)
