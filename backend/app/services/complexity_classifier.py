"""复杂度分类服务 - 使用本地 qwen3-0.6B 模型进行智能分类

优化策略：
1. 双阶段分类：先判断多任务，再评估复杂度
2. 调整生成参数：temperature=0.25, top_p=0.8, top_k=20, do_sample=True
3. 增加Few-shot样例
4. 规则兜底：连续相同输出检测切换规则路由
"""
import json
import re
from enum import Enum
from typing import Optional, Tuple, Dict, Any, TypedDict
from app.core.logger import app_logger

try:
    from json_repair import repair_json
    JSON_REPAIR_AVAILABLE = True
except ImportError:
    JSON_REPAIR_AVAILABLE = False
    app_logger.warning("[COMPLEXITY] json_repair not installed, using fallback parsing")

class ComplexityLevel(str, Enum):
    """复杂度级别枚举"""
    SIMPLE = "simple"      # S: 0.0-0.3 - 简单问答
    RETRIEVAL = "retrieval" # R: 0.3-0.5 - 需要检索
    COT = "cot"          # C: 0.5-0.75 - 需要思维链
    AGENT = "agent"       # A: 0.75-1.0 - 需要ReAct代理

class ComplexityResult(TypedDict):
    """复杂度分类结果"""
    score: float
    level: ComplexityLevel
    is_multi_task: bool
    requires_retrieval: bool
    requires_reasoning: bool
    confidence: float

class MultiTaskResult(TypedDict):
    """多任务检测结果"""
    is_multi_task: bool
    confidence: float

class ComplexityClassifier:
    """复杂度分类器 - 使用本地 qwen3-0.6B 模型（双阶段分类）"""
    
    def __init__(self):
        self._tokenizer = None
        self._model = None
        self._pipeline = None
        self._initialized = False
        self._last_outputs = []  # 用于检测连续相同输出
        self._max_same_outputs = 3  # 连续相同输出阈值
    
    async def initialize(self):
        """按需初始化本地模型；依赖或模型不可用时保留规则降级。"""
        if self._initialized:
            return
        
        from app.core.config import settings
        
        try:
            # Transformers 是本地模型增强依赖，不应阻塞轻量 API、测试或规则路由。
            from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline

            model_path = settings.COMPLEXITY_MODEL_PATH
            app_logger.info(f"[COMPLEXITY] 正在加载本地模型: {model_path}")
            
            self._tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                trust_remote_code=True,
                local_files_only=True,
            )
            
            self._model = AutoModelForCausalLM.from_pretrained(
                model_path,
                trust_remote_code=True,
                local_files_only=True,
                device_map="auto",
                low_cpu_mem_usage=True
            )
            
            # 优化后的生成参数
            self._pipeline = pipeline(
                "text-generation",
                model=self._model,
                tokenizer=self._tokenizer,
                max_new_tokens=120,
                temperature=0.25,
                top_p=0.8,
                top_k=20,
                do_sample=True,
                pad_token_id=self._tokenizer.eos_token_id
            )
            
            self._initialized = True
            app_logger.info("[COMPLEXITY] 模型加载成功")
            
        except Exception as e:
            app_logger.error(f"[COMPLEXITY] 模型加载失败: {e}")
            self._initialized = False
    
    def _get_complexity_level(self, score: float) -> ComplexityLevel:
        """根据分数获取复杂度级别"""
        if score < 0.3:
            return ComplexityLevel.SIMPLE
        elif score < 0.5:
            return ComplexityLevel.RETRIEVAL
        elif score < 0.75:
            return ComplexityLevel.COT
        else:
            return ComplexityLevel.AGENT
    
    def _detect_stuck_output(self, result: dict) -> bool:
        """检测是否连续输出相同结果"""
        result_key = f"{result.get('score', 0)}-{result.get('is_multi_task', False)}"
        
        self._last_outputs.append(result_key)
        if len(self._last_outputs) > self._max_same_outputs:
            self._last_outputs.pop(0)
        
        # 检查是否连续出现相同输出
        if len(self._last_outputs) >= self._max_same_outputs:
            if all(output == self._last_outputs[0] for output in self._last_outputs):
                app_logger.warning("[COMPLEXITY] 检测到连续相同输出，切换规则路由")
                return True
        
        return False
    
    async def _detect_multi_task(self, question: str) -> MultiTaskResult:
        """第一阶段：检测是否为多任务（二分类）"""
        if not self._initialized:
            # 回退到规则检测
            return {
                "is_multi_task": self.is_multi_task(question),
                "confidence": 0.9
            }
        
        try:
            prompt = self._build_multi_task_prompt(question)
            response = self._pipeline(prompt)[0]["generated_text"]
            result = self._parse_multi_task_response(response)
            
            # 检测连续相同输出
            if self._detect_stuck_output({"is_multi_task": result["is_multi_task"], "score": 0}):
                return {
                    "is_multi_task": self.is_multi_task(question),
                    "confidence": 0.9
                }
            
            return result
        except Exception as e:
            app_logger.error(f"[COMPLEXITY] 多任务检测失败，使用回退策略: {e}")
            return {
                "is_multi_task": self.is_multi_task(question),
                "confidence": 0.9
            }
    
    async def _evaluate_complexity(self, question: str) -> Dict:
        """第二阶段：评估复杂度（0.0-1.0）"""
        if not self._initialized:
            # 回退到规则评估
            result = self._fallback_classify(question)
            return {
                "complexity": result["score"],
                "strategy": self._score_to_strategy(result["score"]),
                "requires_retrieval": result["requires_retrieval"],
                "requires_reasoning": result["requires_reasoning"],
                "confidence": result["confidence"]
            }
        
        try:
            prompt = self._build_complexity_prompt(question)
            response = self._pipeline(prompt)[0]["generated_text"]
            result = self._parse_complexity_response(response)
            
            # 检测连续相同输出
            if self._detect_stuck_output({"score": result["complexity"], "is_multi_task": False}):
                fallback = self._fallback_classify(question)
                return {
                    "complexity": fallback["score"],
                    "strategy": self._score_to_strategy(fallback["score"]),
                    "requires_retrieval": fallback["requires_retrieval"],
                    "requires_reasoning": fallback["requires_reasoning"],
                    "confidence": fallback["confidence"]
                }
            
            return result
        except Exception as e:
            app_logger.error(f"[COMPLEXITY] 复杂度评估失败，使用回退策略: {e}")
            fallback = self._fallback_classify(question)
            return {
                "complexity": fallback["score"],
                "strategy": self._score_to_strategy(fallback["score"]),
                "requires_retrieval": fallback["requires_retrieval"],
                "requires_reasoning": fallback["requires_reasoning"],
                "confidence": fallback["confidence"]
            }
    
    def _score_to_strategy(self, score: float) -> str:
        """将分数转换为策略名称"""
        if score < 0.5:
            return "Simple"
        elif score < 0.7:
            return "CoT"
        else:
            return "ReAct"
    
    async def classify(self, question: str) -> ComplexityResult:
        """对问题进行复杂度分类（双阶段）"""
        # 第一阶段：检测多任务
        multi_task_result = await self._detect_multi_task(question)
        
        # 如果是多任务，直接返回最高复杂度
        if multi_task_result["is_multi_task"]:
            return {
                "score": 0.85,
                "level": ComplexityLevel.AGENT,
                "is_multi_task": True,
                "requires_retrieval": True,
                "requires_reasoning": True,
                "confidence": multi_task_result["confidence"]
            }
        
        # 第二阶段：评估复杂度
        complexity_result = await self._evaluate_complexity(question)
        
        return {
            "score": complexity_result["complexity"],
            "level": self._get_complexity_level(complexity_result["complexity"]),
            "is_multi_task": False,
            "requires_retrieval": complexity_result["requires_retrieval"],
            "requires_reasoning": complexity_result["requires_reasoning"],
            "confidence": complexity_result["confidence"]
        }
    
    def _build_multi_task_prompt(self, question: str) -> str:
        """构建多任务检测提示词（极简二分类）"""
        return f"""请判断用户问题是否为多任务，严格输出JSON，无多余内容。
字段：is_multi_task（布尔值）
示例1：
问题：查天气并推荐景点
{{"is_multi_task": true}}
示例2：
问题：解释什么是ES集群
{{"is_multi_task": false}}
示例3：
问题：总结会议内容并提取行动项
{{"is_multi_task": true}}
示例4：
问题：分析市场趋势
{{"is_multi_task": false}}
示例5：
问题：一是总结销售数据，二是分析竞争对手，三是制定策略
{{"is_multi_task": true}}

问题：{question}
输出：""".strip()
    
    def _build_complexity_prompt(self, question: str) -> str:
        """构建复杂度评估提示词"""
        return f"""评估问题复杂度（0.0-1.0）并匹配策略，严格输出JSON，无多余内容。
规则：
0.0-0.5 → Simple（简单问题，直接回答或检索后回答）
0.5-0.7 → CoT（需要1-2步推理）
0.7-1.0 → ReAct（需要多步推理+工具调用）
字段：complexity(浮点数), strategy(字符串), requires_retrieval(布尔), requires_reasoning(布尔)
示例1：
问题：你好
{{"complexity":0.1,"strategy":"Simple","requires_retrieval":false,"requires_reasoning":false}}
示例2：
问题：2025年武汉GDP是多少
{{"complexity":0.4,"strategy":"Simple","requires_retrieval":true,"requires_reasoning":false}}
示例3：
问题：为什么天空是蓝色的
{{"complexity":0.62,"strategy":"CoT","requires_retrieval":false,"requires_reasoning":true}}
示例4：
问题：分析会议内容并提取行动项
{{"complexity":0.75,"strategy":"ReAct","requires_retrieval":true,"requires_reasoning":true}}

问题：{question}
输出：""".strip()
    
    def _extract_json_block(self, text: str) -> Optional[str]:
        """从文本中提取最后一个 JSON 块（避免提取示例中的 JSON）"""
        brace_count = 0
        start_idx = -1
        json_str = ""
        
        for i, char in enumerate(text):
            if char == "{":
                if brace_count == 0:
                    start_idx = i
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0 and start_idx != -1:
                    json_str = text[start_idx:i+1]
                    start_idx = -1
        
        if json_str:
            return json_str
        
        pattern = r'\{[^\}]+\}'
        matches = re.findall(pattern, text)
        if matches:
            return matches[-1]
        
        return None
    
    def _safe_parse_json(self, json_str: str) -> Optional[dict]:
        """安全解析 JSON"""
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        
        if JSON_REPAIR_AVAILABLE:
            try:
                repaired = repair_json(json_str)
                return json.loads(repaired)
            except Exception:
                pass
        
        try:
            fixed = re.sub(r',\s*(\]|\})', r'\1', json_str)
            fixed = fixed.replace("'", '"')
            fixed = ''.join(fixed.split())
            return json.loads(fixed)
        except Exception:
            pass
        
        return None
    
    def _parse_multi_task_response(self, response: str) -> MultiTaskResult:
        """解析多任务检测响应"""
        try:
            json_str = self._extract_json_block(response)
            if not json_str:
                return {"is_multi_task": False, "confidence": 0.5}
            
            data = self._safe_parse_json(json_str)
            if data is None:
                return {"is_multi_task": False, "confidence": 0.5}
            
            return {
                "is_multi_task": bool(data.get("is_multi_task", False)),
                "confidence": min(1.0, float(data.get("confidence", 0.8)))
            }
        except Exception:
            return {"is_multi_task": False, "confidence": 0.5}
    
    def _parse_complexity_response(self, response: str) -> Dict:
        """解析复杂度评估响应"""
        try:
            json_str = self._extract_json_block(response)
            if not json_str:
                return self._fallback_complexity()
            
            data = self._safe_parse_json(json_str)
            if data is None:
                return self._fallback_complexity()
            
            complexity = float(data.get("complexity", 0.5))
            complexity = max(0.0, min(1.0, complexity))
            
            return {
                "complexity": complexity,
                "strategy": data.get("strategy", self._score_to_strategy(complexity)),
                "requires_retrieval": bool(data.get("requires_retrieval", False)),
                "requires_reasoning": bool(data.get("requires_reasoning", False)),
                "confidence": min(1.0, float(data.get("confidence", 0.8)))
            }
        except Exception:
            return self._fallback_complexity()
    
    def _fallback_complexity(self) -> Dict:
        """复杂度评估回退"""
        return {
            "complexity": 0.5,
            "strategy": "CoT",
            "requires_retrieval": False,
            "requires_reasoning": True,
            "confidence": 0.5
        }
    
    def _fallback_classify(self, question: str) -> ComplexityResult:
        """回退分类策略 - 基于规则的分类"""
        normalized = question.strip().lower()
        score = 0.2
        is_multi_task = False
        requires_retrieval = False
        requires_reasoning = False
        
        greeting_keywords = ["你好", "hello", "hi", "您好", "嗨", "早上好", "下午好", "晚上好"]
        if any(kw in normalized for kw in greeting_keywords):
            return {
                "score": 0.1,
                "level": ComplexityLevel.SIMPLE,
                "is_multi_task": False,
                "requires_retrieval": False,
                "requires_reasoning": False,
                "confidence": 1.0
            }
        
        person_indicators = ["负责", "担任", "负责的", "负责了"]
        person_count = len([kw for kw in person_indicators if kw in normalized])
        if person_count >= 2 and "分析" not in normalized and "总结" not in normalized:
            return {
                "score": 0.15,
                "level": ComplexityLevel.SIMPLE,
                "is_multi_task": False,
                "requires_retrieval": False,
                "requires_reasoning": False,
                "confidence": 0.9
            }
        
        multi_task_keywords = ["和", "与", "以及", "同时", "分别", "各", "所有", "每个", "并"]
        multi_task_count = len([kw for kw in multi_task_keywords if kw in normalized])
        
        parallel_markers = ["一是", "二是", "三是", "首先", "其次", "再次", "最后", "第一", "第二", "第三", "然后"]
        has_parallel = any(marker in normalized for marker in parallel_markers)
        
        question_count = normalized.count("？") + normalized.count("?")
        
        if has_parallel or question_count >= 2 or (multi_task_count >= 2 and len(question) > 25):
            is_multi_task = True
            score = max(score, 0.75)
        
        sequence_markers = ["首先", "然后", "接着", "最后"]
        sequence_count = len([kw for kw in sequence_markers if kw in normalized])
        if sequence_count >= 2:
            is_multi_task = True
            score = max(score, 0.8)
        
        reasoning_keywords = ["为什么", "怎么", "如何", "分析", "总结", "比较", "对比", "原因", "解释", "论证", "推导"]
        has_reasoning = any(kw in normalized for kw in reasoning_keywords)
        if has_reasoning:
            requires_reasoning = True
            score = min(0.7, score + 0.3)
        
        retrieval_keywords = [
            "多少", "什么时间", "什么时候", "哪个", "谁", "哪一年", "价格", "数据", "统计",
            "发布时间", "日期", "金额", "数量", "排名", "比例", "增长率", "多少人"
        ]
        has_retrieval = any(kw in normalized for kw in retrieval_keywords)
        if has_retrieval:
            requires_retrieval = True
            if score < 0.3:
                score = 0.4
        
        if len(question) > 120:
            score = min(0.95, score + 0.25)
        elif len(question) > 80:
            score = min(0.8, score + 0.15)
        elif len(question) > 40:
            score = min(0.6, score + 0.1)
        
        task_actions = ["分析", "提取", "识别", "总结", "制定", "评估", "估算", "规划"]
        action_count = len([kw for kw in task_actions if kw in normalized])
        if action_count >= 3:
            is_multi_task = True
            score = max(score, 0.9)
        elif action_count >= 2:
            is_multi_task = True
            score = max(score, 0.75)
        
        confidence = 0.7
        if is_multi_task and action_count >= 2:
            confidence = 0.9
        elif has_reasoning or has_retrieval:
            confidence = 0.8
        elif len(question) < 20:
            confidence = 0.95
        
        return {
            "score": score,
            "level": self._get_complexity_level(score),
            "is_multi_task": is_multi_task,
            "requires_retrieval": requires_retrieval,
            "requires_reasoning": requires_reasoning,
            "confidence": confidence
        }
    
    def is_multi_task(self, question: str) -> bool:
        """判断是否为多任务问题"""
        normalized = question.strip().lower()
        
        multi_task_indicators = [
            "和", "与", "以及", "同时", "分别", "各", "所有", "每个",
            "还有", "另外", "除此之外", "另外", "再", "然后"
        ]
        
        question_count = normalized.count("？") + normalized.count("?")
        
        has_parallel = any(kw in normalized for kw in ["一是", "二是", "首先", "其次", "第一", "第二"])
        
        return (
            len([kw for kw in multi_task_indicators if kw in normalized]) >= 2 or
            question_count >= 2 or
            has_parallel
        )

# 全局分类器实例
_complexity_classifier = ComplexityClassifier()

async def get_complexity_classifier() -> ComplexityClassifier:
    """获取复杂度分类器实例"""
    await _complexity_classifier.initialize()
    return _complexity_classifier
