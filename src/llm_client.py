"""LLM 客户端:GLM(OpenAI 兼容)封装 + 自一致性投票(并发采样)。

对应论文 2.3 节"自一致性投票":对同一条款进行 3 次采样,
若风险类型不一致则降低置信度并提示"需人工复核"。
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from typing import Optional

import time
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI, RateLimitError


_DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
_DEFAULT_MODEL = "GLM-4.7-Flash"
_DEFAULT_API_KEY = ""


class LlmClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("LLM_API_KEY", _DEFAULT_API_KEY)
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", _DEFAULT_BASE_URL)
        self.model = model or os.environ.get("LLM_MODEL", _DEFAULT_MODEL)
        if not self.api_key:
            self._client = None
            self._err = "LLM_API_KEY 未配置"
            return
        try:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            self._err = None
        except Exception as e:
            self._client = None
            self._err = f"OpenAI 客户端初始化失败:{e}"

    def is_ready(self) -> bool:
        return self._client is not None

    def error(self) -> Optional[str]:
        return self._err

    def get_config(self) -> dict:
        """返回当前配置（API Key 脱敏处理）。"""
        key = self.api_key
        masked = key[:4] + "****" + key[-4:] if len(key) > 8 else ("****" if key else "")
        return {
            "base_url": self.base_url,
            "model": self.model,
            "api_key_masked": masked,
            "ready": self.is_ready(),
            "error": self._err,
        }

    def update_config(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> bool:
        """动态更新 LLM 配置，立即生效。"""
        if api_key is not None:
            self.api_key = api_key.strip()
        if base_url is not None:
            self.base_url = base_url.strip()
        if model is not None:
            self.model = model.strip()

        if not self.api_key:
            self._client = None
            self._err = "LLM_API_KEY 未配置"
            return False

        try:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            self._err = None
            return True
        except Exception as e:
            self._client = None
            self._err = f"OpenAI 客户端初始化失败:{e}"
            return False

    def chat(self, system: str, user: str, temperature: float = 0.2, max_tokens: int = 2048) -> str:
        if not self._client:
            return json.dumps({
                "risk_type": "其他",
                "risk_level": "中",
                "reason": f"LLM 未就绪:{self._err or '未知错误'}",
                "suggestion": "请检查 LLM_API_KEY/LLM_BASE_URL/LLM_MODEL 配置。",
                "confidence": 0.0,
            }, ensure_ascii=False)
        for attempt in range(3):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return resp.choices[0].message.content or ""
            except RateLimitError:
                if attempt < 2:
                    wait = 2 ** attempt
                    time.sleep(wait)
                    continue
                return json.dumps({
                    "_error": True,
                    "risk_type": "其他",
                    "risk_level": "中",
                    "reason": "LLM 调用触发速率限制(429),请稍后重试。",
                    "suggestion": "降低采样频率或更换付费模型。",
                    "confidence": 0.0,
                }, ensure_ascii=False)
            except Exception as e:
                return json.dumps({
                    "_error": True,
                    "risk_type": "其他",
                    "risk_level": "中",
                    "reason": f"LLM 调用异常:{type(e).__name__}:{e}",
                    "suggestion": "稍后重试或检查网络/额度。",
                    "confidence": 0.0,
                }, ensure_ascii=False)

    def chat_with_self_consistency(
        self,
        system: str,
        user: str,
        samples: int = 3,
        temperature: float = 0.3,
    ) -> dict:
        """对同一条款多次采样,投票得出最终风险类型;不一致则降置信度并标记复核。

        为降低免费模型串行延迟,使用线程池并发发起采样请求。
        """
        results = []
        if samples <= 1:
            raw = self.chat(system, user, temperature=temperature)
            parsed = _safe_parse_json(raw)
            if parsed:
                results.append(parsed)
        else:
            with ThreadPoolExecutor(max_workers=min(samples, 5)) as executor:
                futures = [
                    executor.submit(self.chat, system, user, temperature)
                    for _ in range(samples)
                ]
                for future in futures:
                    raw = future.result()
                    parsed = _safe_parse_json(raw)
                    if parsed and not parsed.get("_error"):
                        results.append(parsed)

        if not results:
            return {
                "risk_type": "其他",
                "risk_level": "中",
                "reason": "三次采样均解析失败或全部触发速率限制。",
                "suggestion": "请人工复核条款,或稍后重试。",
                "confidence": 0.0,
                "need_review": True,
            }

        types = [r.get("risk_type", "其他") for r in results]
        counter = Counter(types)
        majority_type, majority_count = counter.most_common(1)[0]
        agreement = majority_count / len(results)

        # 取多数类型对应的首个结果为基准
        chosen = next(r for r in results if r.get("risk_type") == majority_type)
        base_conf = float(chosen.get("confidence", 0.5))

        # 一致性折算:全一致保持原置信度,部分一致降到 ×0.7,严重分歧降到 ×0.5
        if agreement == 1.0:
            final_conf = base_conf
            need_review = False
        elif agreement >= 0.6:
            final_conf = round(base_conf * 0.7, 3)
            need_review = False
        else:
            final_conf = round(base_conf * 0.5, 3)
            need_review = True

        chosen["confidence"] = final_conf
        chosen["need_review"] = need_review
        chosen["voting"] = dict(counter)
        return chosen


_JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}")


def _safe_parse_json(text: str) -> Optional[dict]:
    """从 LLM 输出中宽容地抽取首个 JSON 对象。"""
    if not text:
        return None
    text = text.strip()
    # 直接尝试
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # 抽 ```json ... ``` 围栏
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        try:
            obj = json.loads(fence.group(1))
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    # 抽首个 {...}
    m = _JSON_OBJ_RE.search(text)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
    return None
