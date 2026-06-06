import re
import jieba
from typing import List, Tuple, Dict, Optional
from collections import Counter
from app.core.logger import app_logger
from app.core.config import settings

class TextProcessService:
    """文本预处理服务"""

    # 语气词列表（用于过滤无意义内容）
    TONE_WORDS = {
        '嗯', '啊', '哦', '唉', '对', '好', '是', '呃', '哎', '额', '行',
        '嗯哼', '啊哈', '对对对', '嗯嗯', '嗯嗯嗯', '是吧', '好的', '是的',
        '对对', '嗯哪', '哎呀', '哎哟', '哇', '哈', '哈哈哈', '嘿嘿',
        '那个', '然后', '就是说', '就是', '这个', '什么', '怎么', '为什么'
    }

    def __init__(self):
        # 从配置中获取切片参数
        self.chunk_size = settings.CHUNK_SIZE
        self.chunk_overlap = settings.CHUNK_OVERLAP
        
        # 停用词列表（中文常用停用词）
        self.stopwords = set([
            '的', '了', '和', '是', '就', '都', '而', '及', '与', '着', '或',
            '一个', '没有', '我们', '你们', '他们', '它们', '这个', '那个',
            '什么', '怎么', '如何', '为什么', '因为', '所以', '但是', '然而',
            '可以', '可能', '应该', '必须', '需要', '要', '会', '能', '不能',
            '在', '上', '下', '左', '右', '前', '后', '中', '间', '内', '外',
            '有', '无', '不', '也', '还', '很', '太', '非常', '最', '更',
            '这', '那', '此', '其', '某', '每', '各', '所有', '任何', '一些',
            '等', '等等', '例如', '比如', '包括', '以及', '通过', '根据',
            '表示', '认为', '指出', '说明', '提到', '强调', '建议', '要求',
            '会议', '讨论', '决定', '同意', '反对', '问题', '意见', '建议'
        ])

    def is_tone_only(self, content: str) -> bool:
        """
        判断内容是否为纯语气词（无实质信息）
        用于2x3因子实验的最佳实践：过滤纯语气词内容
        """
        if not content or len(content) < 3:
            return True

        # 去除标点
        content_clean = re.sub(r'[。！？，、；：""''（）()【】\\s]+', '', content)
        if not content_clean:
            return True

        # 去除语气词
        for tone in self.TONE_WORDS:
            content_clean = content_clean.replace(tone, '')

        return len(content_clean) == 0

    def filter_tone_speeches(self, speeches: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """
        过滤纯语气词和无意义发言
        基于2x3因子实验结果：过滤后chunk质量显著提升
        """
        filtered = []
        for speech in speeches:
            content = speech.get('content', '')
            # 跳过纯语气词
            if self.is_tone_only(content):
                continue
            # 跳过太短的内容（<3字符）
            if len(content.strip()) < 3:
                continue
            filtered.append(speech)
        return filtered

    def clean_text(self, text: str) -> str:
        """
        基础文本清洗
        - 去除多余空格、换行符
        - 去除特殊字符
        - 统一全角半角
        """
        if not text:
            return ""
        
        # 去除多余空格和换行
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 去除特殊字符（保留中文、英文、数字、基本标点）
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9，。！？、；：""''（）()【】 \\t\\n\\r]', '', text)
        
        # 全角转半角
        text = self._full_to_half(text)
        
        return text

    def _full_to_half(self, text: str) -> str:
        """全角字符转半角字符"""
        result = []
        for char in text:
            code = ord(char)
            if code == 0x3000:  # 全角空格
                result.append(' ')
            elif 0xFF01 <= code <= 0xFF5E:  # 全角ASCII字符
                result.append(chr(code - 0xFEE0))
            else:
                result.append(char)
        return ''.join(result)

    def split_sentences(self, text: str) -> List[str]:
        """
        分句处理
        将文本按中文标点符号切分为句子
        """
        if not text:
            return []
        
        # 按句号、问号、感叹号分句
        sentences = re.split(r'([。！？])', text)
        
        # 重组句子（保留标点）
        result = []
        for i in range(0, len(sentences)-1, 2):
            sentence = (sentences[i] + sentences[i+1]).strip()
            if sentence:
                result.append(sentence)
        
        # 处理最后一个没有标点的部分
        if len(sentences) % 2 == 1 and sentences[-1].strip():
            result.append(sentences[-1].strip())
        
        return result

    def split_chunks(self, text: str, chunk_size: Optional[int] = None, overlap: Optional[int] = None) -> List[str]:
        """
        基础文本切片
        将长文本切分为固定大小的片段，支持重叠
        
        Args:
            text: 原始文本
            chunk_size: 每个片段的最大字符数（默认为配置中的值）
            overlap: 相邻片段的重叠字符数（默认为配置中的值）
        
        Returns:
            切片后的文本片段列表
        """
        # 使用配置中的默认值，如果传入参数则使用传入的值
        chunk_size = chunk_size if chunk_size is not None else self.chunk_size
        overlap = overlap if overlap is not None else self.chunk_overlap
        
        if not text:
            return []
        
        sentences = self.split_sentences(text)
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sentence_len = len(sentence)
            
            # 如果当前片段加上新句子超过限制且已有内容，先保存当前片段
            if current_length + sentence_len > chunk_size and current_chunk:
                chunks.append(''.join(current_chunk))
                
                # 计算需要保留的重叠部分
                overlap_text = ''.join(current_chunk)[-overlap:] if overlap > 0 else ''
                current_chunk = [overlap_text] if overlap_text else []
                current_length = len(overlap_text)
            
            current_chunk.append(sentence)
            current_length += sentence_len
        
        # 保存最后一个片段
        if current_chunk:
            chunks.append(''.join(current_chunk))
        
        return chunks

    def extract_keywords(self, text: str, top_n: int = 10) -> List[Tuple[str, int]]:
        """
        简单关键词提取（基于词频）
        
        Args:
            text: 文本内容
            top_n: 返回前N个关键词
        
        Returns:
            关键词列表，每个元素为(关键词, 词频)
        """
        if not text:
            return []
        
        # 分词
        words = jieba.lcut(text)
        
        # 过滤停用词和单字
        filtered_words = [
            word for word in words 
            if word not in self.stopwords and len(word) > 1
        ]
        
        # 统计词频
        word_counts = Counter(filtered_words)
        
        # 返回前N个关键词
        return word_counts.most_common(top_n)

    def generate_summary(self, text: str, max_length: int = 300) -> str:
        """
        基础摘要生成（基于关键句提取）
        
        Args:
            text: 原始文本
            max_length: 摘要最大长度
        
        Returns:
            生成的摘要文本
        """
        if not text:
            return ""
        
        sentences = self.split_sentences(text)
        if not sentences:
            return ""
        
        # 提取关键词
        keywords = [word for word, _ in self.extract_keywords(text, top_n=20)]
        
        # 计算每个句子的关键词覆盖率（作为重要性评分）
        sentence_scores = []
        for idx, sentence in enumerate(sentences):
            score = sum(1 for kw in keywords if kw in sentence)
            sentence_scores.append((idx, sentence, score))
        
        # 按评分排序
        sentence_scores.sort(key=lambda x: x[2], reverse=True)
        
        # 选取关键句子生成摘要
        summary = []
        current_length = 0
        
        for idx, sentence, score in sentence_scores:
            if score > 0 and current_length + len(sentence) <= max_length:
                summary.append((idx, sentence))
                current_length += len(sentence)
        
        # 按原顺序排列
        summary.sort(key=lambda x: x[0])
        
        return ''.join([s for _, s in summary])

    def parse_meeting_text(self, file_content: str, file_type: str = 'txt') -> Dict[str, any]:
        """
        解析会议文本/录音转写文本
        
        Args:
            file_content: 文件内容
            file_type: 文件类型（txt/md等）
        
        Returns:
            解析结果字典，包含：
            - original_text: 原始文本
            - cleaned_text: 清洗后的文本
            - sentences: 分句结果
            - chunks: 切片结果
            - keywords: 关键词列表
            - summary: 摘要
        """
        try:
            # 清洗文本
            cleaned_text = self.clean_text(file_content)
            
            # 分句
            sentences = self.split_sentences(cleaned_text)
            
            # 切片
            chunks = self.split_chunks(cleaned_text)
            
            # 提取关键词
            keywords = self.extract_keywords(cleaned_text)
            
            # 生成摘要
            summary = self.generate_summary(cleaned_text)
            
            return {
                'original_text': file_content,
                'cleaned_text': cleaned_text,
                'sentences': sentences,
                'chunks': chunks,
                'keywords': [{'word': kw[0], 'count': kw[1]} for kw in keywords],
                'summary': summary,
                'sentence_count': len(sentences),
                'chunk_count': len(chunks),
                'word_count': len(cleaned_text)
            }
        
        except Exception as e:
            app_logger.error(f"会议文本解析失败: {e}")
            raise

    def parse_speech_text(self, text: str) -> List[Dict[str, any]]:
        """
        解析带说话人信息的会议文本
        
        支持的格式:
        1. "[时间戳] 说话人: 内容"
        2. "说话人: 内容"
        3. "【说话人】内容"
        4. "时间戳 说话人：内容"
        
        Args:
            text: 会议文本内容
        
        Returns:
            发言记录列表，每个元素包含 speaker_name, content, timestamp, start_time_offset
        """
        if not text:
            return []
        
        speech_patterns = [
            # 模式1: [00:00:00] 说话人: 内容
            r'^\[(\d{2}:\d{2}:\d{2})\]\s*([^\s:：]+)\s*[:：]\s*(.+)$',
            # 模式2: [00:00] 说话人: 内容
            r'^\[(\d{2}:\d{2})\]\s*([^\s:：]+)\s*[:：]\s*(.+)$',
            # 模式3: 00:00:00 说话人: 内容
            r'^(\d{2}:\d{2}:\d{2})\s+([^\s:：]+)\s*[:：]\s*(.+)$',
            # 模式4: 说话人: 内容
            r'^([^\s:：]+)\s*[:：]\s*(.+)$',
            # 模式5: 【说话人】内容
            r'^【([^】]+)】\s*(.+)$',
        ]
        
        lines = text.split('\n')
        speeches = []
        current_speaker = None
        current_content = []
        current_timestamp = None
        current_time_offset = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            matched = False
            for pattern in speech_patterns:
                match = re.match(pattern, line)
                if match:
                    # 先保存上一个说话人的内容
                    if current_speaker and current_content:
                        speeches.append({
                            'speaker_name': current_speaker,
                            'content': '\n'.join(current_content).strip(),
                            'timestamp': current_timestamp,
                            'start_time_offset': current_time_offset,
                        })
                    
                    # 解析新的发言
                    groups = match.groups()
                    if len(groups) == 3:
                        current_timestamp = groups[0]
                        current_speaker = groups[1]
                        content = groups[2]
                        current_time_offset = self._parse_timestamp(current_timestamp)
                    elif len(groups) == 2:
                        # 检查第一个组是否是时间戳
                        if re.match(r'^\d{2}:\d{2}(:\d{2})?$', groups[0]):
                            current_timestamp = groups[0]
                            current_speaker = groups[1]
                            content = ""
                            current_time_offset = self._parse_timestamp(current_timestamp)
                        else:
                            current_timestamp = None
                            current_speaker = groups[0]
                            content = groups[1]
                            current_time_offset = None
                    
                    current_content = [content] if content else []
                    matched = True
                    break
            
            if not matched and current_speaker:
                current_content.append(line)
        
        # 保存最后一个说话人的内容
        if current_speaker and current_content:
            speeches.append({
                'speaker_name': current_speaker,
                'content': '\n'.join(current_content).strip(),
                'timestamp': current_timestamp,
                'start_time_offset': current_time_offset,
            })
        
        # 对发言按时间排序（如果有时间信息）
        speeches.sort(key=lambda x: x['start_time_offset'] if x['start_time_offset'] is not None else 0)

        # 合并过短的发言，避免碎片化 chunk
        min_size = settings.SPEAKER_MIN_CHUNK_SIZE
        if min_size > 0:
            speeches = self._merge_short_speeches(speeches, min_size)

        return speeches

    def _merge_short_speeches(self, speeches: List[Dict], min_size: int) -> List[Dict]:
        """
        合并连续的短发言，直到累积内容达到 min_size 字符。
        保留第一条发言的说话人、时间戳作为合并块的元数据。
        """
        if not speeches:
            return speeches

        merged = []
        buf_content = []
        buf_speaker = None
        buf_timestamp = None
        buf_time_offset = None

        for speech in speeches:
            if buf_speaker is None:
                buf_speaker = speech['speaker_name']
                buf_timestamp = speech['timestamp']
                buf_time_offset = speech['start_time_offset']

            buf_content.append(speech['content'])

            if len('\n'.join(buf_content)) >= min_size:
                merged.append({
                    'speaker_name': buf_speaker,
                    'content': '\n'.join(buf_content).strip(),
                    'timestamp': buf_timestamp,
                    'start_time_offset': buf_time_offset,
                })
                buf_content = []
                buf_speaker = None
                buf_timestamp = None
                buf_time_offset = None

        # 将剩余不足 min_size 的内容追加到最后一个 chunk，或单独成块
        if buf_content:
            if merged:
                last = merged[-1]
                last['content'] = (last['content'] + '\n' + '\n'.join(buf_content)).strip()
            else:
                merged.append({
                    'speaker_name': buf_speaker,
                    'content': '\n'.join(buf_content).strip(),
                    'timestamp': buf_timestamp,
                    'start_time_offset': buf_time_offset,
                })

        return merged
    
    def _parse_timestamp(self, timestamp: str) -> Optional[float]:
        """
        解析时间戳字符串为秒数
        
        Args:
            timestamp: 时间戳字符串，格式如 "00:00:00" 或 "00:00"
        
        Returns:
            秒数，解析失败返回 None
        """
        try:
            parts = timestamp.split(':')
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
        except (ValueError, IndexError):
            pass
        return None

    def extract_todo_items(self, text: str) -> List[Dict[str, str]]:
        """
        从会议文本中提取待办事项
        
        Args:
            text: 会议文本内容
        
        Returns:
            待办事项列表，每个元素包含 title 和 assignee
        """
        if not text:
            return []
        
        todo_patterns = [
            r'(需要|要|应该|必须)\s*(做|完成|提交|编写|修改|确认|跟进)\s*(.+?)(。|！|\?|$)',
            r'(待办|任务|行动项|下一步)\s*[：:]\s*(.+?)(。|！|\?|$)',
            r'([\u4e00-\u9fa5a-zA-Z0-9]+)\s*(负责|牵头|承担)\s*(.+?)(。|！|\?|$)',
        ]
        
        todo_items = []
        seen = set()
        
        for pattern in todo_patterns:
            matches = re.findall(pattern, text, re.MULTILINE)
            for match in matches:
                # 提取任务内容（根据不同模式取不同组）
                if len(match) >= 3:
                    task = match[-2].strip()
                    if task and task not in seen and len(task) > 2:
                        seen.add(task)
                        todo_items.append({
                            'title': task,
                            'assignee': None  # 后续可通过NLP识别负责人
                        })
        
        return todo_items[:20]  # 最多返回20个待办事项