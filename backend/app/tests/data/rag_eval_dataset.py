"""RAG 评估测试数据集 - 完整版

包含263个问题，覆盖会议智能助手的各个方面。

数据格式：
- question: 用户问题
- expected_answer: 期望的正确回答
- relevant_doc_ids: 相关文档ID列表
- difficulty: 难度级别 (easy/medium/hard)
- category: 问题类别
- question_type: 问题类型
"""

RAG_EVAL_DATASET = [
    # === 功能介绍类 ===
    {
        "id": "q1",
        "question": "会议智能助手的主要功能有哪些？",
        "expected_answer": "会议智能助手主要功能包括：实时语音转写、会议内容结构化整理、自动生成会议纪要、待办事项抽取、历史会议知识库问答、参会人情绪分析等。",
        "relevant_doc_ids": [1, 2],
        "difficulty": "easy",
        "category": "功能介绍",
        "question_type": "事实型"
    },
    {
        "id": "q2",
        "question": "系统支持哪些语言的语音转写？",
        "expected_answer": "系统支持的语音转写语言包括：中文（普通话、粤语、闽南语）、英文（美式英语、英式英语）、日语、韩语、西班牙语等。",
        "relevant_doc_ids": [1, 4],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q3",
        "question": "语音转写的准确率是多少？",
        "expected_answer": "语音转写准确率：普通话98.5%、英文97.8%、粤语96.2%。",
        "relevant_doc_ids": [4],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q4",
        "question": "会议纪要可以导出为哪些格式？",
        "expected_answer": "会议纪要支持导出为Markdown、PDF、Word、HTML等格式，可以导出到本地文件、企业云盘、邮件发送或消息通知。",
        "relevant_doc_ids": [1, 5],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q5",
        "question": "待办事项有哪些状态？",
        "expected_answer": "待办事项支持以下状态：待处理、进行中、已完成、已取消、延期。",
        "relevant_doc_ids": [6],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q6",
        "question": "最多支持多少人参会？",
        "expected_answer": "语音转写功能支持最多10个说话人同时识别。",
        "relevant_doc_ids": [4],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q7",
        "question": "会议纪要可以编辑吗？",
        "expected_answer": "是的，自动生成的会议纪要可以在页面上直接编辑修改。",
        "relevant_doc_ids": [5],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q8",
        "question": "待办事项支持哪些提醒方式？",
        "expected_answer": "待办事项支持系统通知、邮件提醒、消息推送、日历同步等多种提醒方式。",
        "relevant_doc_ids": [6],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q9",
        "question": "会议纪要可以自定义模板吗？",
        "expected_answer": "是的，系统支持创建自定义纪要模板，包括公司特定格式、部门专用模板和项目模板。",
        "relevant_doc_ids": [5],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q10",
        "question": "语音转写有哪些特色功能？",
        "expected_answer": "语音转写特色功能包括：多语言支持、高准确率（普通话98.5%）、说话人分离（最大支持10人）、实时延迟小于500ms、AI降噪处理（背景噪音过滤、回声消除、语音增强）。",
        "relevant_doc_ids": [1, 4],
        "difficulty": "medium",
        "category": "功能说明",
        "question_type": "事实型"
    },
    # === 概念解释类 ===
    {
        "id": "q11",
        "question": "什么是 RAG 技术？",
        "expected_answer": "RAG（Retrieval-Augmented Generation）是一种结合检索和生成的AI技术，先从知识库检索相关信息，再基于检索结果生成回答。",
        "relevant_doc_ids": [2, 16],
        "difficulty": "easy",
        "category": "概念解释",
        "question_type": "定义型"
    },
    {
        "id": "q12",
        "question": "会议时序分层检索是什么？",
        "expected_answer": "会议时序分层检索是针对会议场景优化的RAG技术，按时间节点和发言人物双层切片，优先召回同时间段的关联发言内容。",
        "relevant_doc_ids": [2],
        "difficulty": "medium",
        "category": "概念解释",
        "question_type": "定义型"
    },
    {
        "id": "q13",
        "question": "什么是向量检索？",
        "expected_answer": "向量检索是一种基于语义相似度的检索技术，将文本转换为向量表示，通过计算向量之间的相似度来匹配相关文档。",
        "relevant_doc_ids": [2, 16],
        "difficulty": "medium",
        "category": "概念解释",
        "question_type": "定义型"
    },
    {
        "id": "q14",
        "question": "什么是文本向量化？",
        "expected_answer": "文本向量化是将自然语言转换为数值向量的过程，使计算机能够理解和比较文本语义。",
        "relevant_doc_ids": [16],
        "difficulty": "easy",
        "category": "概念解释",
        "question_type": "定义型"
    },
    {
        "id": "q15",
        "question": "什么是余弦相似度？",
        "expected_answer": "余弦相似度是衡量两个向量方向差异的度量方法，取值范围[-1,1]，值越大表示方向越相似。",
        "relevant_doc_ids": [16],
        "difficulty": "easy",
        "category": "概念解释",
        "question_type": "定义型"
    },
    # === 技术说明类 ===
    {
        "id": "q16",
        "question": "向量检索有哪两种模式？",
        "expected_answer": "本系统支持两种向量检索模式：pgvector模式（使用PostgreSQL扩展进行向量运算）和轻量模式（在Python内存中计算余弦相似度）。",
        "relevant_doc_ids": [2],
        "difficulty": "easy",
        "category": "技术说明",
        "question_type": "事实型"
    },
    {
        "id": "q17",
        "question": "系统采用什么技术架构？",
        "expected_answer": "系统采用微服务架构，主要包含：语音处理模块、文本分析模块、向量检索模块、LLM集成模块、数据存储模块。",
        "relevant_doc_ids": [1, 14],
        "difficulty": "medium",
        "category": "技术说明",
        "question_type": "事实型"
    },
    {
        "id": "q18",
        "question": "常用的Embedding模型有哪些？",
        "expected_answer": "常用的Embedding模型包括：all-MiniLM-L6-v2（384维，通用场景）、text-embedding-ada-002（1536维，高精度）、BERT-base-chinese（768维，中文优化）。",
        "relevant_doc_ids": [16],
        "difficulty": "medium",
        "category": "技术说明",
        "question_type": "事实型"
    },
    {
        "id": "q19",
        "question": "如何提高向量检索的准确性？",
        "expected_answer": "可以通过以下方式提高向量检索准确性：使用合适的向量化模型、优化文本切片策略、添加检索重排、调整相似度阈值、使用混合检索等方法。",
        "relevant_doc_ids": [2, 16],
        "difficulty": "medium",
        "category": "技术优化",
        "question_type": "推理型"
    },
    {
        "id": "q20",
        "question": "RAG的工作流程是什么？",
        "expected_answer": "RAG工作流程包括：索引构建阶段（文档上传、文本切片、向量化处理、向量存储）、查询阶段（查询向量化、向量检索、结果排序、上下文构建）、生成阶段（Prompt构建、LLM调用、结果生成、后处理）。",
        "relevant_doc_ids": [16],
        "difficulty": "medium",
        "category": "技术说明",
        "question_type": "事实型"
    },
    # === 操作指南类 ===
    {
        "id": "q21",
        "question": "系统支持哪些文件格式的上传？",
        "expected_answer": "系统支持的文件格式包括：TXT、PDF、DOCX、DOC、MD。",
        "relevant_doc_ids": [3],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q22",
        "question": "文档上传的步骤是什么？",
        "expected_answer": "文档上传步骤：1)进入文档库页面；2)点击上传按钮；3)选择文件；4)填写元数据（可选）；5)确认上传。",
        "relevant_doc_ids": [3, 17],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q23",
        "question": "如何创建会议？",
        "expected_answer": "创建会议步骤：1)点击'新建会议'菜单；2)填写会议标题；3)设置会议时间；4)添加参会人员；5)点击'创建'。",
        "relevant_doc_ids": [17],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q24",
        "question": "如何进行高级检索？",
        "expected_answer": "高级检索技巧：使用引号进行精确匹配、使用减号排除关键词、使用OR连接多个条件。",
        "relevant_doc_ids": [17],
        "difficulty": "medium",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q25",
        "question": "文档上传失败怎么办？",
        "expected_answer": "文档上传失败可能原因：文件大小超过限制（最大50MB）、文件格式不支持、网络超时、文件内容损坏。",
        "relevant_doc_ids": [3, 9],
        "difficulty": "medium",
        "category": "操作指南",
        "question_type": "推理型"
    },
    {
        "id": "q26",
        "question": "文档上传后多久可以检索？",
        "expected_answer": "文档上传后系统会自动解析并生成向量索引，通常需要10-30秒，大文件可能需要更长时间。",
        "relevant_doc_ids": [9],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    # === API文档类 ===
    {
        "id": "q27",
        "question": "登录接口的请求格式是什么？",
        "expected_answer": "POST /api/v1/auth/login，请求体包含username和password字段。",
        "relevant_doc_ids": [7],
        "difficulty": "easy",
        "category": "API文档",
        "question_type": "事实型"
    },
    {
        "id": "q28",
        "question": "上传文档接口需要什么请求头？",
        "expected_answer": "上传文档需要Authorization: Bearer <token>和Content-Type: multipart/form-data请求头。",
        "relevant_doc_ids": [7],
        "difficulty": "medium",
        "category": "API文档",
        "question_type": "事实型"
    },
    {
        "id": "q29",
        "question": "向量检索接口的请求参数有哪些？",
        "expected_answer": "向量检索接口POST /api/v1/vector-search/search的请求参数包括：query（查询文本）、top_k（返回数量）、mode（检索模式）。",
        "relevant_doc_ids": [7],
        "difficulty": "easy",
        "category": "API文档",
        "question_type": "事实型"
    },
    {
        "id": "q30",
        "question": "创建会议接口的请求体包含哪些字段？",
        "expected_answer": "创建会议接口POST /api/v1/meetings的请求体包含：title、description、start_time、end_time、participants、department字段。",
        "relevant_doc_ids": [7],
        "difficulty": "medium",
        "category": "API文档",
        "question_type": "事实型"
    },
    # === 配置与部署类 ===
    {
        "id": "q31",
        "question": "数据库连接需要哪些环境变量？",
        "expected_answer": "数据库连接需要POSTGRES_HOST、POSTGRES_PORT、POSTGRES_USER、POSTGRES_PASSWORD、POSTGRES_DB环境变量。",
        "relevant_doc_ids": [8],
        "difficulty": "easy",
        "category": "配置部署",
        "question_type": "事实型"
    },
    {
        "id": "q32",
        "question": "LLM配置包含哪些参数？",
        "expected_answer": "LLM配置包含LLM_API_KEY、LLM_MODEL、LLM_TEMPERATURE、LLM_MAX_TOKENS等参数。",
        "relevant_doc_ids": [8],
        "difficulty": "easy",
        "category": "配置部署",
        "question_type": "事实型"
    },
    {
        "id": "q33",
        "question": "开发环境如何启动服务？",
        "expected_answer": "开发环境启动命令：cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload。",
        "relevant_doc_ids": [8],
        "difficulty": "easy",
        "category": "配置部署",
        "question_type": "事实型"
    },
    {
        "id": "q34",
        "question": "默认的文本切片大小是多少？",
        "expected_answer": "默认的文本切片大小chunk_size为512，切片重叠大小chunk_overlap为64。",
        "relevant_doc_ids": [8],
        "difficulty": "easy",
        "category": "配置部署",
        "question_type": "事实型"
    },
    {
        "id": "q35",
        "question": "默认的检索返回数量是多少？",
        "expected_answer": "默认的检索返回数量top_k为5，相似度阈值similarity_threshold为0.5。",
        "relevant_doc_ids": [8],
        "difficulty": "easy",
        "category": "配置部署",
        "question_type": "事实型"
    },
    # === 权限管理类 ===
    {
        "id": "q36",
        "question": "系统有哪些用户角色？",
        "expected_answer": "系统用户角色包括：管理员、部门管理员、普通用户、访客用户。",
        "relevant_doc_ids": [19],
        "difficulty": "easy",
        "category": "权限管理",
        "question_type": "事实型"
    },
    {
        "id": "q37",
        "question": "管理员有哪些权限？",
        "expected_answer": "管理员可以管理所有用户、所有文档、所有会议，并可以配置系统参数。",
        "relevant_doc_ids": [19],
        "difficulty": "easy",
        "category": "权限管理",
        "question_type": "事实型"
    },
    {
        "id": "q38",
        "question": "普通用户可以查看哪些文档？",
        "expected_answer": "普通用户可以查看和管理自己创建的文档，以及查看公共文档。",
        "relevant_doc_ids": [19],
        "difficulty": "easy",
        "category": "权限管理",
        "question_type": "事实型"
    },
    {
        "id": "q39",
        "question": "访客用户有哪些限制？",
        "expected_answer": "访客用户只能查看公共文档，不能创建文档或会议，查询权限有限。",
        "relevant_doc_ids": [19],
        "difficulty": "easy",
        "category": "权限管理",
        "question_type": "事实型"
    },
    {
        "id": "q40",
        "question": "权限变更流程是什么？",
        "expected_answer": "权限变更流程：1)用户提交权限变更申请；2)部门管理员审核（部门内变更）；3)管理员审核（跨部门或升级变更）；4)系统更新权限；5)通知用户变更结果。",
        "relevant_doc_ids": [19],
        "difficulty": "medium",
        "category": "权限管理",
        "question_type": "事实型"
    },
    # === 安全合规类 ===
    {
        "id": "q41",
        "question": "数据加密方式有哪些？",
        "expected_answer": "数据加密方式包括：传输加密（HTTPS/TLS 1.3）、存储加密（AES-256）、数据库加密（透明数据加密）。",
        "relevant_doc_ids": [13],
        "difficulty": "medium",
        "category": "安全合规",
        "question_type": "事实型"
    },
    {
        "id": "q42",
        "question": "访问控制采用什么原则？",
        "expected_answer": "访问控制采用基于角色的访问控制（RBAC），遵循最小权限原则，并定期进行权限审计。",
        "relevant_doc_ids": [13],
        "difficulty": "medium",
        "category": "安全合规",
        "question_type": "事实型"
    },
    {
        "id": "q43",
        "question": "数据备份策略是什么？",
        "expected_answer": "数据备份策略：每日增量备份、每周全量备份、异地灾备。",
        "relevant_doc_ids": [13],
        "difficulty": "easy",
        "category": "安全合规",
        "question_type": "事实型"
    },
    {
        "id": "q44",
        "question": "安全事件响应流程是什么？",
        "expected_answer": "安全事件响应流程：1)发现安全事件；2)评估影响范围；3)采取应急措施；4)调查根因；5)恢复服务；6)报告与总结。",
        "relevant_doc_ids": [13],
        "difficulty": "medium",
        "category": "安全合规",
        "question_type": "事实型"
    },
    # === 性能优化类 ===
    {
        "id": "q45",
        "question": "系统采用哪些缓存策略？",
        "expected_answer": "系统采用Redis缓存热点数据、多级缓存架构、缓存一致性保证等缓存策略。",
        "relevant_doc_ids": [14],
        "difficulty": "medium",
        "category": "性能优化",
        "question_type": "事实型"
    },
    {
        "id": "q46",
        "question": "向量索引优化方法有哪些？",
        "expected_answer": "向量索引优化方法包括：IVF索引加速、HNSW算法应用、量化压缩技术。",
        "relevant_doc_ids": [14],
        "difficulty": "medium",
        "category": "性能优化",
        "question_type": "事实型"
    },
    {
        "id": "q47",
        "question": "文档检索的P95响应时间目标是多少？",
        "expected_answer": "文档检索的P95响应时间目标是小于300ms，P99响应时间目标是小于500ms。",
        "relevant_doc_ids": [14],
        "difficulty": "easy",
        "category": "性能优化",
        "question_type": "事实型"
    },
    {
        "id": "q48",
        "question": "服务可用性目标是多少？",
        "expected_answer": "服务可用性目标是99.9%，数据持久性目标是99.999%。",
        "relevant_doc_ids": [14],
        "difficulty": "easy",
        "category": "性能优化",
        "question_type": "事实型"
    },
    # === 综合问题类 ===
    {
        "id": "q49",
        "question": "会议智能助手和RAG技术有什么关系？",
        "expected_answer": "会议智能助手使用RAG技术实现历史会议知识库问答功能，通过向量检索从知识库中获取相关信息，再结合LLM生成准确的回答。",
        "relevant_doc_ids": [1, 2, 16],
        "difficulty": "hard",
        "category": "综合问题",
        "question_type": "推理型"
    },
    {
        "id": "q50",
        "question": "文档管理和向量检索是如何配合工作的？",
        "expected_answer": "文档上传后会自动生成向量索引，当用户进行检索时，系统会根据查询向量与文档向量的相似度进行匹配，返回最相关的文档内容。",
        "relevant_doc_ids": [2, 3, 16],
        "difficulty": "hard",
        "category": "综合问题",
        "question_type": "推理型"
    },
    {
        "id": "q51",
        "question": "待办事项是如何从会议中自动抽取的？",
        "expected_answer": "待办事项抽取功能通过识别动词开头的句子、包含'需要'/'必须'/'应该'等关键词的语句、时间相关表述和责任分配语句来自动识别行动项。",
        "relevant_doc_ids": [1, 6],
        "difficulty": "medium",
        "category": "综合问题",
        "question_type": "推理型"
    },
    {
        "id": "q52",
        "question": "系统的核心功能与技术架构有什么关系？",
        "expected_answer": "系统的核心功能（语音转写、纪要生成、待办抽取、知识库问答）分别对应技术架构中的语音处理模块、文本分析模块、LLM集成模块和向量检索模块。",
        "relevant_doc_ids": [1, 2, 4, 5, 6],
        "difficulty": "hard",
        "category": "综合问题",
        "question_type": "推理型"
    },
    {
        "id": "q53",
        "question": "如何将会议内容转化为可执行的待办事项？",
        "expected_answer": "系统通过语音转写将会议语音转为文本，然后自动抽取待办事项（识别动词句、关键词等），最后分配责任人和截止日期，形成可追踪的任务。",
        "relevant_doc_ids": [1, 4, 6],
        "difficulty": "hard",
        "category": "综合问题",
        "question_type": "推理型"
    },
    # === 比较型问题 ===
    {
        "id": "q54",
        "question": "pgvector模式和轻量模式有什么区别？",
        "expected_answer": "pgvector模式使用PostgreSQL扩展进行向量运算，适合大规模数据和生产环境；轻量模式在Python内存中计算余弦相似度，适合小规模数据和开发测试环境。",
        "relevant_doc_ids": [2],
        "difficulty": "medium",
        "category": "技术说明",
        "question_type": "比较型"
    },
    {
        "id": "q55",
        "question": "管理员和部门管理员有什么区别？",
        "expected_answer": "管理员可以管理所有用户、文档、会议并配置系统；部门管理员只能管理本部门的用户、文档和会议，不能管理系统配置。",
        "relevant_doc_ids": [19],
        "difficulty": "medium",
        "category": "权限管理",
        "question_type": "比较型"
    },
    {
        "id": "q56",
        "question": "余弦相似度和欧氏距离有什么区别？",
        "expected_answer": "余弦相似度衡量向量方向差异，不受向量长度影响；欧氏距离衡量向量空间距离，受向量长度影响。",
        "relevant_doc_ids": [16],
        "difficulty": "medium",
        "category": "技术说明",
        "question_type": "比较型"
    },
    # === 否定型问题 ===
    {
        "id": "q57",
        "question": "系统不支持哪些文件格式？",
        "expected_answer": "系统支持TXT、PDF、DOCX、DOC、MD格式，不支持的格式包括：XLSX、PPT、图片格式（JPG/PNG）、音频视频格式等。",
        "relevant_doc_ids": [3],
        "difficulty": "medium",
        "category": "操作指南",
        "question_type": "否定型"
    },
    {
        "id": "q58",
        "question": "普通用户不能做什么？",
        "expected_answer": "普通用户不能管理其他用户、不能管理不属于自己的文档和会议、不能配置系统参数。",
        "relevant_doc_ids": [19],
        "difficulty": "medium",
        "category": "权限管理",
        "question_type": "否定型"
    },
    # === 多跳型问题 ===
    {
        "id": "q59",
        "question": "语音转写功能使用的技术架构是什么？",
        "expected_answer": "语音转写功能使用系统的语音处理模块，该模块是微服务架构的一部分，支持多语言识别和实时转写。",
        "relevant_doc_ids": [1, 14],
        "difficulty": "hard",
        "category": "综合问题",
        "question_type": "多跳型"
    },
    {
        "id": "q60",
        "question": "文档上传后如何被用于智能查询？",
        "expected_answer": "文档上传后经过解析、切片、向量化处理，生成向量索引存储；当用户进行智能查询时，系统将查询向量化，通过向量检索找到相关文档，再结合LLM生成回答。",
        "relevant_doc_ids": [2, 3, 16],
        "difficulty": "hard",
        "category": "综合问题",
        "question_type": "多跳型"
    },
    # === 更多功能说明问题 ===
    {
        "id": "q61",
        "question": "登录失败怎么办？",
        "expected_answer": "登录失败请检查：确认用户名和密码正确、检查网络连接是否正常、确认账户未被锁定、尝试清除浏览器缓存后重新登录。",
        "relevant_doc_ids": [9],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "推理型"
    },
    {
        "id": "q62",
        "question": "忘记密码怎么办？",
        "expected_answer": "点击登录页面的'忘记密码'链接，按照提示输入注册邮箱，系统会发送重置密码邮件。",
        "relevant_doc_ids": [9, 17],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q63",
        "question": "为什么看不到某些文档？",
        "expected_answer": "文档有权限控制：部门文档只能被同部门用户查看、个人文档只能被创建者查看、管理员可以查看所有文档。",
        "relevant_doc_ids": [9, 19],
        "difficulty": "medium",
        "category": "权限管理",
        "question_type": "推理型"
    },
    {
        "id": "q64",
        "question": "检索结果不准确怎么办？",
        "expected_answer": "检索结果不准确可以尝试：使用更精确的关键词、调整检索模式（pgvector/lightweight）、增加返回结果数量、检查文档是否已正确上传。",
        "relevant_doc_ids": [9],
        "difficulty": "medium",
        "category": "操作指南",
        "question_type": "推理型"
    },
    {
        "id": "q65",
        "question": "检索速度慢怎么办？",
        "expected_answer": "首次检索可能较慢，系统会自动缓存热门查询。如果持续慢，可以检查网络连接或联系管理员。",
        "relevant_doc_ids": [9],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "推理型"
    },
    # === 更多技术说明问题 ===
    {
        "id": "q66",
        "question": "什么是IVF索引？",
        "expected_answer": "IVF（Inverted File）索引是一种向量索引加速技术，通过将向量空间划分为多个聚类，查询时只在相关聚类中搜索，从而提高检索速度。",
        "relevant_doc_ids": [14],
        "difficulty": "medium",
        "category": "技术说明",
        "question_type": "定义型"
    },
    {
        "id": "q67",
        "question": "什么是HNSW算法？",
        "expected_answer": "HNSW（Hierarchical Navigable Small Worlds）是一种高效的近似最近邻搜索算法，通过构建多层图结构实现快速检索。",
        "relevant_doc_ids": [14],
        "difficulty": "medium",
        "category": "技术说明",
        "question_type": "定义型"
    },
    {
        "id": "q68",
        "question": "什么是量化压缩技术？",
        "expected_answer": "量化压缩技术是将高精度向量（如FP32）转换为低精度表示（如INT8），以减少存储空间和提高检索速度。",
        "relevant_doc_ids": [14],
        "difficulty": "medium",
        "category": "技术说明",
        "question_type": "定义型"
    },
    # === 更多综合问题 ===
    {
        "id": "q69",
        "question": "RAG技术如何提升会议问答的准确性？",
        "expected_answer": "RAG技术通过向量检索从知识库中获取相关上下文，LLM基于这些上下文生成回答，避免了幻觉问题，提高了回答的准确性和可验证性。",
        "relevant_doc_ids": [2, 16],
        "difficulty": "hard",
        "category": "综合问题",
        "question_type": "推理型"
    },
    {
        "id": "q70",
        "question": "数据安全措施如何保护用户隐私？",
        "expected_answer": "数据安全措施包括传输加密、存储加密、访问控制、定期备份等，确保用户数据在传输和存储过程中的安全性，符合GDPR和等保要求。",
        "relevant_doc_ids": [13],
        "difficulty": "medium",
        "category": "综合问题",
        "question_type": "推理型"
    },
    # === 更多操作指南问题 ===
    {
        "id": "q71",
        "question": "如何获取更高权限？",
        "expected_answer": "联系系统管理员申请权限变更，提交权限变更申请，经过审核后系统会更新权限。",
        "relevant_doc_ids": [9, 19],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q72",
        "question": "系统支持哪些浏览器？",
        "expected_answer": "系统支持Chrome、Firefox、Safari、Edge等现代浏览器。",
        "relevant_doc_ids": [9],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q73",
        "question": "移动端可以使用吗？",
        "expected_answer": "目前主要支持桌面端，移动端功能正在开发中，计划在Q1 2024完成移动端适配。",
        "relevant_doc_ids": [9],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q74",
        "question": "会议可以提前结束吗？",
        "expected_answer": "可以，主持人可以随时结束会议。",
        "relevant_doc_ids": [9],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    # === 更多API问题 ===
    {
        "id": "q75",
        "question": "登出接口需要什么请求头？",
        "expected_answer": "登出接口POST /api/v1/auth/logout需要Authorization: Bearer <token>请求头。",
        "relevant_doc_ids": [7],
        "difficulty": "easy",
        "category": "API文档",
        "question_type": "事实型"
    },
    {
        "id": "q76",
        "question": "获取文档详情接口的路径参数是什么？",
        "expected_answer": "GET /api/v1/documents/{id}的路径参数是id，表示文档ID。",
        "relevant_doc_ids": [7],
        "difficulty": "easy",
        "category": "API文档",
        "question_type": "事实型"
    },
    # === 更多配置问题 ===
    {
        "id": "q77",
        "question": "向量数据库的维度配置是多少？",
        "expected_answer": "向量数据库维度PGVECTOR_DIMENSION默认是384，与all-MiniLM-L6-v2模型维度对应。",
        "relevant_doc_ids": [8],
        "difficulty": "easy",
        "category": "配置部署",
        "question_type": "事实型"
    },
    {
        "id": "q78",
        "question": "生产环境如何部署？",
        "expected_answer": "生产环境使用docker-compose部署：docker-compose up -d。",
        "relevant_doc_ids": [8],
        "difficulty": "easy",
        "category": "配置部署",
        "question_type": "事实型"
    },
    # === 更多统计问题 ===
    {
        "id": "q79",
        "question": "文档类型分布情况如何？",
        "expected_answer": "文档类型分布：会议纪要40%、技术文档30%、操作指南20%、其他10%。",
        "relevant_doc_ids": [21],
        "difficulty": "easy",
        "category": "数据统计",
        "question_type": "事实型"
    },
    {
        "id": "q80",
        "question": "会议类型分布情况如何？",
        "expected_answer": "会议类型分布：部门会议50%、项目会议30%、跨部门会议15%、其他5%。",
        "relevant_doc_ids": [21],
        "difficulty": "easy",
        "category": "数据统计",
        "question_type": "事实型"
    },
    {
        "id": "q81",
        "question": "会议时长分布情况如何？",
        "expected_answer": "会议时长分布：30分钟以下20%、30-60分钟50%、60-90分钟20%、90分钟以上10%。",
        "relevant_doc_ids": [21],
        "difficulty": "easy",
        "category": "数据统计",
        "question_type": "事实型"
    },
    {
        "id": "q82",
        "question": "检索成功率是多少？",
        "expected_answer": "检索平均成功率95%，精确匹配率85%，模糊匹配率15%。",
        "relevant_doc_ids": [21],
        "difficulty": "easy",
        "category": "数据统计",
        "question_type": "事实型"
    },
    # === 更多市场调研问题 ===
    {
        "id": "q83",
        "question": "2024年全球智能会议市场规模是多少？",
        "expected_answer": "2024年全球智能会议市场规模预计达到500亿美元，年增长率约15%。",
        "relevant_doc_ids": [10],
        "difficulty": "easy",
        "category": "市场分析",
        "question_type": "事实型"
    },
    {
        "id": "q84",
        "question": "智能会议市场的主要玩家有哪些？",
        "expected_answer": "智能会议市场主要玩家包括：Zoom（25%市场份额）、Microsoft Teams（20%）、Google Meet（15%）、Cisco Webex（10%）。",
        "relevant_doc_ids": [10],
        "difficulty": "easy",
        "category": "市场分析",
        "question_type": "事实型"
    },
    # === 继续扩展问题 ===
    {
        "id": "q85",
        "question": "系统的快捷键Ctrl+K有什么作用？",
        "expected_answer": "Ctrl+K快捷键用于打开全局搜索功能。",
        "relevant_doc_ids": [17],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q86",
        "question": "系统的快捷键Ctrl+S有什么作用？",
        "expected_answer": "Ctrl+S快捷键用于保存当前内容。",
        "relevant_doc_ids": [17],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q87",
        "question": "页面加载缓慢怎么办？",
        "expected_answer": "页面加载缓慢可以尝试：刷新页面、清除浏览器缓存、检查网络连接、联系IT支持。",
        "relevant_doc_ids": [17],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "推理型"
    },
    {
        "id": "q88",
        "question": "什么是GDPR合规？",
        "expected_answer": "GDPR合规要求包括：用户数据可删除、数据处理透明、隐私政策明确等。",
        "relevant_doc_ids": [13],
        "difficulty": "medium",
        "category": "安全合规",
        "question_type": "定义型"
    },
    {
        "id": "q89",
        "question": "什么是网络安全等级保护？",
        "expected_answer": "网络安全等级保护包括三级等保认证、安全审计日志、入侵检测系统等要求。",
        "relevant_doc_ids": [13],
        "difficulty": "medium",
        "category": "安全合规",
        "question_type": "定义型"
    },
    {
        "id": "q90",
        "question": "系统的微服务架构包含哪些通信机制？",
        "expected_answer": "系统微服务架构的通信机制包括gRPC和REST。",
        "relevant_doc_ids": [14],
        "difficulty": "easy",
        "category": "技术说明",
        "question_type": "事实型"
    },
    {
        "id": "q91",
        "question": "什么是服务注册与发现？",
        "expected_answer": "服务注册与发现是微服务架构中的一种机制，用于管理服务实例的注册、发现和负载均衡。",
        "relevant_doc_ids": [14],
        "difficulty": "medium",
        "category": "技术说明",
        "question_type": "定义型"
    },
    {
        "id": "q92",
        "question": "什么是查询缓存机制？",
        "expected_answer": "查询缓存机制是将频繁查询的结果存储在缓存中，减少重复计算，提高响应速度。",
        "relevant_doc_ids": [14],
        "difficulty": "medium",
        "category": "技术说明",
        "question_type": "定义型"
    },
    {
        "id": "q93",
        "question": "语音转写的降噪处理包含哪些功能？",
        "expected_answer": "语音转写的降噪处理包含背景噪音过滤、回声消除、语音增强等功能。",
        "relevant_doc_ids": [4],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q94",
        "question": "说话人分离功能支持多少个说话人？",
        "expected_answer": "说话人分离功能最大支持10个说话人自动识别。",
        "relevant_doc_ids": [4],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q95",
        "question": "待办事项包含哪些属性？",
        "expected_answer": "待办事项包含：任务描述、责任人、截止日期、优先级、关联会议、状态等属性。",
        "relevant_doc_ids": [6],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q96",
        "question": "待办事项的优先级如何设置？",
        "expected_answer": "待办事项的优先级可以在创建或编辑待办时设置，通常分为高、中、低三个级别。",
        "relevant_doc_ids": [6],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q97",
        "question": "待办事项统计分析包含哪些内容？",
        "expected_answer": "待办事项统计分析包含：按状态分布、按责任人统计、按时效分析、完成率报告等。",
        "relevant_doc_ids": [6],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q98",
        "question": "会议纪要的智能排版包含哪些功能？",
        "expected_answer": "会议纪要的智能排版包含：多级标题、列表项、表格支持、代码块高亮等功能。",
        "relevant_doc_ids": [5],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q99",
        "question": "会议纪要可以导出到哪些地方？",
        "expected_answer": "会议纪要可以导出到本地文件、企业云盘、邮件发送、消息通知。",
        "relevant_doc_ids": [5],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q100",
        "question": "什么是召回率？",
        "expected_answer": "召回率（Recall@k）是指检索到的相关文档数与总相关文档数的比值，衡量系统找到所有相关信息的能力。",
        "relevant_doc_ids": [2],
        "difficulty": "easy",
        "category": "评估指标",
        "question_type": "定义型"
    },
    {
        "id": "q101",
        "question": "什么是精确率？",
        "expected_answer": "精确率（Precision@k）是指检索到的相关文档数与检索结果总数的比值，衡量系统只返回相关信息的能力。",
        "relevant_doc_ids": [2],
        "difficulty": "easy",
        "category": "评估指标",
        "question_type": "定义型"
    },
    {
        "id": "q102",
        "question": "什么是MRR？",
        "expected_answer": "MRR（Mean Reciprocal Rank）是首次命中相关文档位置的倒数的平均值，衡量相关文档在检索结果中的排名位置。",
        "relevant_doc_ids": [2],
        "difficulty": "medium",
        "category": "评估指标",
        "question_type": "定义型"
    },
    {
        "id": "q103",
        "question": "文档上传的最大文件大小是多少？",
        "expected_answer": "文档上传的最大文件大小是50MB。",
        "relevant_doc_ids": [3, 9],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q104",
        "question": "会议纪要的自定义模板包含哪些类型？",
        "expected_answer": "会议纪要的自定义模板包含：公司特定格式、部门专用模板、项目模板。",
        "relevant_doc_ids": [5],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q105",
        "question": "什么是向量语义检索？",
        "expected_answer": "向量语义检索是一种基于文本向量表示的检索技术，通过计算查询向量与文档向量的语义相似度来匹配相关内容。",
        "relevant_doc_ids": [2, 16],
        "difficulty": "medium",
        "category": "概念解释",
        "question_type": "定义型"
    },
    {
        "id": "q106",
        "question": "向量检索的两种模式分别适合什么场景？",
        "expected_answer": "pgvector模式适合大规模数据和生产环境；轻量模式适合小规模数据和开发测试环境。",
        "relevant_doc_ids": [2],
        "difficulty": "medium",
        "category": "技术说明",
        "question_type": "比较型"
    },
    {
        "id": "q107",
        "question": "如何设置会议的参会人员？",
        "expected_answer": "创建会议时在participants字段中添加参会人员邮箱列表。",
        "relevant_doc_ids": [7],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q108",
        "question": "如何关联会议和文档？",
        "expected_answer": "上传文档时可以通过meeting_id参数关联到特定会议。",
        "relevant_doc_ids": [7],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q109",
        "question": "文档上传接口支持哪些可选参数？",
        "expected_answer": "文档上传接口POST /api/v1/documents/upload的可选参数包括meeting_id（关联会议ID）和department（部门名称）。",
        "relevant_doc_ids": [7],
        "difficulty": "easy",
        "category": "API文档",
        "question_type": "事实型"
    },
    {
        "id": "q110",
        "question": "向量检索接口的响应格式是什么？",
        "expected_answer": "向量检索接口返回包含query和results字段的JSON，results是包含document_id、chunk_text、similarity的对象数组。",
        "relevant_doc_ids": [7],
        "difficulty": "medium",
        "category": "API文档",
        "question_type": "事实型"
    },
    {
        "id": "q111",
        "question": "什么是文本切片？",
        "expected_answer": "文本切片（Chunking）是将长文档分割成较小文本片段的过程，便于向量化处理和检索。",
        "relevant_doc_ids": [16],
        "difficulty": "easy",
        "category": "技术说明",
        "question_type": "定义型"
    },
    {
        "id": "q112",
        "question": "文本切片的默认重叠大小是多少？",
        "expected_answer": "文本切片的默认重叠大小chunk_overlap是64。",
        "relevant_doc_ids": [8],
        "difficulty": "easy",
        "category": "配置部署",
        "question_type": "事实型"
    },
    {
        "id": "q113",
        "question": "什么是链式思考？",
        "expected_answer": "链式思考（Chain of Thought）是一种提示词工程技术，通过引导LLM逐步推理来生成更准确的回答。",
        "relevant_doc_ids": [16],
        "difficulty": "medium",
        "category": "技术说明",
        "question_type": "定义型"
    },
    {
        "id": "q114",
        "question": "什么是上下文压缩？",
        "expected_answer": "上下文压缩是在将检索结果传给LLM之前，对上下文进行精简和优化，以适应LLM的上下文窗口限制。",
        "relevant_doc_ids": [16],
        "difficulty": "medium",
        "category": "技术说明",
        "question_type": "定义型"
    },
    {
        "id": "q115",
        "question": "日志格式包含哪些信息？",
        "expected_answer": "日志格式包含时间戳、日志名称、日志级别、日志消息等信息，格式为：%(asctime)s - %(name)s - %(levelname)s - %(message)s。",
        "relevant_doc_ids": [8],
        "difficulty": "medium",
        "category": "配置部署",
        "question_type": "事实型"
    },
    {
        "id": "q116",
        "question": "什么是透明数据加密？",
        "expected_answer": "透明数据加密（TDE）是一种数据库加密技术，在数据写入磁盘时自动加密，读取时自动解密，对应用程序透明。",
        "relevant_doc_ids": [13],
        "difficulty": "medium",
        "category": "安全合规",
        "question_type": "定义型"
    },
    {
        "id": "q117",
        "question": "什么是最小权限原则？",
        "expected_answer": "最小权限原则是指用户只被授予完成其工作所需的最小权限，以减少安全风险。",
        "relevant_doc_ids": [13, 19],
        "difficulty": "easy",
        "category": "安全合规",
        "question_type": "定义型"
    },
    {
        "id": "q118",
        "question": "什么是基于角色的访问控制？",
        "expected_answer": "基于角色的访问控制（RBAC）是一种权限管理机制，通过为角色分配权限，再将角色分配给用户来控制访问。",
        "relevant_doc_ids": [13, 19],
        "difficulty": "easy",
        "category": "安全合规",
        "question_type": "定义型"
    },
    {
        "id": "q119",
        "question": "用户调研中需求优先级最高的是什么？",
        "expected_answer": "用户调研中需求优先级最高的是会议纪要自动生成（85%）。",
        "relevant_doc_ids": [10],
        "difficulty": "easy",
        "category": "市场分析",
        "question_type": "事实型"
    },
    {
        "id": "q120",
        "question": "市场竞争的优势是什么？",
        "expected_answer": "市场竞争优势包括：专注会议场景的垂直解决方案、深度集成语音转写和纪要生成、灵活的部署方式。",
        "relevant_doc_ids": [10],
        "difficulty": "easy",
        "category": "市场分析",
        "question_type": "事实型"
    },
    {
        "id": "q121",
        "question": "市场竞争的挑战是什么？",
        "expected_answer": "市场竞争挑战包括：巨头竞争激烈、用户习惯培养需要时间、技术门槛较高。",
        "relevant_doc_ids": [10],
        "difficulty": "easy",
        "category": "市场分析",
        "question_type": "事实型"
    },
    {
        "id": "q122",
        "question": "智能会议市场的趋势预测是什么？",
        "expected_answer": "智能会议市场趋势预测：AI驱动的智能助手将成为标配、实时翻译功能需求增长、会议数据分析成为新热点。",
        "relevant_doc_ids": [10],
        "difficulty": "easy",
        "category": "市场分析",
        "question_type": "事实型"
    },
    {
        "id": "q123",
        "question": "用户调研中的价格敏感度如何？",
        "expected_answer": "用户调研显示：愿意为优质功能付费、中小企业更关注性价比、大型企业重视安全性。",
        "relevant_doc_ids": [10],
        "difficulty": "easy",
        "category": "市场分析",
        "question_type": "事实型"
    },
    {
        "id": "q124",
        "question": "系统的日均活跃用户数是多少？",
        "expected_answer": "系统的日均活跃用户数约为500人。",
        "relevant_doc_ids": [21],
        "difficulty": "easy",
        "category": "数据统计",
        "question_type": "事实型"
    },
    {
        "id": "q125",
        "question": "系统的总文档数是多少？",
        "expected_answer": "系统的总文档数超过5000篇。",
        "relevant_doc_ids": [21],
        "difficulty": "easy",
        "category": "数据统计",
        "question_type": "事实型"
    },
    {
        "id": "q126",
        "question": "系统的日均上传文档数是多少？",
        "expected_answer": "系统的日均上传文档数约为50篇。",
        "relevant_doc_ids": [21],
        "difficulty": "easy",
        "category": "数据统计",
        "question_type": "事实型"
    },
    {
        "id": "q127",
        "question": "查询类型分布情况如何？",
        "expected_answer": "查询类型分布：事实查询40%、文档检索30%、问题解答20%、其他10%。",
        "relevant_doc_ids": [21],
        "difficulty": "easy",
        "category": "数据统计",
        "question_type": "事实型"
    },
    {
        "id": "q128",
        "question": "默认的LLM温度参数是多少？",
        "expected_answer": "默认的LLM温度参数LLM_TEMPERATURE是0.7。",
        "relevant_doc_ids": [8],
        "difficulty": "easy",
        "category": "配置部署",
        "question_type": "事实型"
    },
    {
        "id": "q129",
        "question": "API访问令牌过期时间是多少？",
        "expected_answer": "API访问令牌过期时间ACCESS_TOKEN_EXPIRE_MINUTES是30分钟。",
        "relevant_doc_ids": [8],
        "difficulty": "easy",
        "category": "配置部署",
        "question_type": "事实型"
    },
    {
        "id": "q130",
        "question": "系统支持的日志级别有哪些？",
        "expected_answer": "系统支持的日志级别包括：DEBUG、INFO、WARNING、ERROR。",
        "relevant_doc_ids": [8],
        "difficulty": "easy",
        "category": "配置部署",
        "question_type": "事实型"
    },
    {
        "id": "q131",
        "question": "语音转写的实时延迟是多少？",
        "expected_answer": "语音转写的实时延迟小于500ms，满足实时会议场景需求。",
        "relevant_doc_ids": [4],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q132",
        "question": "文档状态有哪些？",
        "expected_answer": "文档状态包括：已上传（文件已成功上传但尚未解析）、已解析（文件内容已提取并生成向量索引）、解析失败（文件解析过程中发生错误）。",
        "relevant_doc_ids": [3],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q133",
        "question": "RAG系统的评估指标有哪些？",
        "expected_answer": "RAG系统常用评估指标包括：Recall@k（召回率）、Precision@k（精确率）、MRR（平均倒数排名）、答案相关性、事实准确性等。",
        "relevant_doc_ids": [2],
        "difficulty": "medium",
        "category": "评估指标",
        "question_type": "事实型"
    },
    {
        "id": "q134",
        "question": "文档的权限隔离是如何实现的？",
        "expected_answer": "权限隔离包括：部门隔离（不同部门文档相互隔离）、角色权限（管理员、部门管理员、普通用户）、公共文档（标记为公开可被所有用户访问）。",
        "relevant_doc_ids": [3],
        "difficulty": "medium",
        "category": "权限管理",
        "question_type": "事实型"
    },
    {
        "id": "q135",
        "question": "会议纪要包含哪些内容？",
        "expected_answer": "会议纪要包含会议基本信息（主题、时间地点、参会人员、时长）、会议内容摘要（讨论要点、决策事项、行动项列表、待跟进事项）等结构化内容。",
        "relevant_doc_ids": [1, 5],
        "difficulty": "medium",
        "category": "综合问题",
        "question_type": "事实型"
    },
    {
        "id": "q136",
        "question": "文档上传和待办事项有什么关联？",
        "expected_answer": "上传的文档可以被检索用于回答问题，待办事项可以关联到特定会议，而会议可以关联文档，形成完整的知识管理闭环。",
        "relevant_doc_ids": [3, 6],
        "difficulty": "hard",
        "category": "综合问题",
        "question_type": "推理型"
    },
    {
        "id": "q137",
        "question": "权限变更申请需要经过哪些人的审核？",
        "expected_answer": "部门内权限变更需要部门管理员审核；跨部门或升级变更需要部门管理员和管理员两级审核。",
        "relevant_doc_ids": [19],
        "difficulty": "medium",
        "category": "权限管理",
        "question_type": "多跳型"
    },
    {
        "id": "q138",
        "question": "会议时序分层检索如何优化检索效果？",
        "expected_answer": "会议时序分层检索按时间节点和发言人物双层切片，优先召回同时间段的关联发言内容，提高了检索的相关性和上下文一致性。",
        "relevant_doc_ids": [2],
        "difficulty": "hard",
        "category": "综合问题",
        "question_type": "推理型"
    },
    {
        "id": "q139",
        "question": "文档检索的P99响应时间目标是多少？",
        "expected_answer": "文档检索的P99响应时间目标是小于500ms。",
        "relevant_doc_ids": [14],
        "difficulty": "easy",
        "category": "性能优化",
        "question_type": "事实型"
    },
    {
        "id": "q140",
        "question": "数据持久性目标是多少？",
        "expected_answer": "数据持久性目标是99.999%。",
        "relevant_doc_ids": [14],
        "difficulty": "easy",
        "category": "性能优化",
        "question_type": "事实型"
    },
    {
        "id": "q141",
        "question": "文档平均大小是多少？",
        "expected_answer": "平均文档大小为20KB。",
        "relevant_doc_ids": [21],
        "difficulty": "easy",
        "category": "数据统计",
        "question_type": "事实型"
    },
    {
        "id": "q142",
        "question": "周活跃用户数是多少？",
        "expected_answer": "周活跃用户数约为800人。",
        "relevant_doc_ids": [21],
        "difficulty": "easy",
        "category": "数据统计",
        "question_type": "事实型"
    },
    {
        "id": "q143",
        "question": "月活跃用户数是多少？",
        "expected_answer": "月活跃用户数约为1000人。",
        "relevant_doc_ids": [21],
        "difficulty": "easy",
        "category": "数据统计",
        "question_type": "事实型"
    },
    {
        "id": "q144",
        "question": "部门管理员可以管理哪些内容？",
        "expected_answer": "部门管理员可以管理本部门用户、本部门文档、本部门会议，但不能管理系统配置。",
        "relevant_doc_ids": [19],
        "difficulty": "easy",
        "category": "权限管理",
        "question_type": "事实型"
    },
    {
        "id": "q145",
        "question": "文档上传接口的必填参数是什么？",
        "expected_answer": "文档上传接口POST /api/v1/documents/upload的必填参数是file（文档文件）。",
        "relevant_doc_ids": [7],
        "difficulty": "easy",
        "category": "API文档",
        "question_type": "事实型"
    },
    {
        "id": "q146",
        "question": "创建会议接口的成功响应状态码是多少？",
        "expected_answer": "创建会议接口POST /api/v1/meetings的成功响应状态码是201。",
        "relevant_doc_ids": [7],
        "difficulty": "easy",
        "category": "API文档",
        "question_type": "事实型"
    },
    # === 新文档相关问题 ===
    # 会议流程管理规范 (22.md)
    {
        "id": "q147",
        "question": "会议前需要做哪些准备工作？",
        "expected_answer": "会前准备包括：确定会议主题和目标、选择参会人员、安排会议时间和地点、准备会议材料、提前24小时发送会议邀请并包含议程。",
        "relevant_doc_ids": [22],
        "difficulty": "easy",
        "category": "会议管理",
        "question_type": "事实型"
    },
    {
        "id": "q148",
        "question": "会议纪要应该在什么时候发送？",
        "expected_answer": "会议纪要应该在会议结束后2小时内完成并发送给所有参会人员。",
        "relevant_doc_ids": [22],
        "difficulty": "easy",
        "category": "会议管理",
        "question_type": "事实型"
    },
    {
        "id": "q149",
        "question": "日常例会的主要目的是什么？",
        "expected_answer": "日常例会主要用于汇报工作进展、协调资源分配，通常每周固定时间召开。",
        "relevant_doc_ids": [22],
        "difficulty": "easy",
        "category": "会议管理",
        "question_type": "事实型"
    },
    # 数据分析报告模板 (23.md)
    {
        "id": "q150",
        "question": "月度数据分析报告包含哪些部分？",
        "expected_answer": "月度数据分析报告包含报告概览、关键指标、趋势分析、问题与建议、下一步计划等部分。",
        "relevant_doc_ids": [23],
        "difficulty": "easy",
        "category": "数据分析",
        "question_type": "事实型"
    },
    {
        "id": "q151",
        "question": "用户指标包括哪些内容？",
        "expected_answer": "用户指标包括活跃用户数、新用户注册、用户留存率等。",
        "relevant_doc_ids": [23],
        "difficulty": "easy",
        "category": "数据分析",
        "question_type": "事实型"
    },
    {
        "id": "q152",
        "question": "业务指标包括哪些内容？",
        "expected_answer": "业务指标包括会议总数、文档上传量、检索次数等。",
        "relevant_doc_ids": [23],
        "difficulty": "easy",
        "category": "数据分析",
        "question_type": "事实型"
    },
    # 系统维护手册 (24.md)
    {
        "id": "q153",
        "question": "服务器监控的阈值是多少？",
        "expected_answer": "服务器监控阈值：CPU使用率80%、内存使用率85%、磁盘空间90%。",
        "relevant_doc_ids": [24],
        "difficulty": "easy",
        "category": "系统维护",
        "question_type": "事实型"
    },
    {
        "id": "q154",
        "question": "操作日志保留多久？",
        "expected_answer": "操作日志保留90天。",
        "relevant_doc_ids": [24],
        "difficulty": "easy",
        "category": "系统维护",
        "question_type": "事实型"
    },
    {
        "id": "q155",
        "question": "服务宕机应该如何处理？",
        "expected_answer": "服务宕机处理步骤：检查进程状态，重启服务。",
        "relevant_doc_ids": [24],
        "difficulty": "easy",
        "category": "系统维护",
        "question_type": "推理型"
    },
    # 会议礼仪指南 (25.md)
    {
        "id": "q156",
        "question": "参加会议应该提前多久到达？",
        "expected_answer": "参加会议应该提前5分钟进入会议室。",
        "relevant_doc_ids": [25],
        "difficulty": "easy",
        "category": "会议礼仪",
        "question_type": "事实型"
    },
    {
        "id": "q157",
        "question": "会议期间手机应该如何处理？",
        "expected_answer": "会议期间手机应调至静音，紧急情况外出接听，避免频繁查看手机。",
        "relevant_doc_ids": [25],
        "difficulty": "easy",
        "category": "会议礼仪",
        "question_type": "事实型"
    },
    # API使用指南 (26.md)
    {
        "id": "q158",
        "question": "如何获取API访问令牌？",
        "expected_answer": "通过POST /api/v1/auth/login接口，传入username和password获取Token。",
        "relevant_doc_ids": [26],
        "difficulty": "easy",
        "category": "API文档",
        "question_type": "事实型"
    },
    {
        "id": "q159",
        "question": "常见的HTTP错误码有哪些？",
        "expected_answer": "常见HTTP错误码：400请求参数错误、401未授权访问、403权限不足、404资源不存在、500服务器内部错误。",
        "relevant_doc_ids": [26],
        "difficulty": "easy",
        "category": "API文档",
        "question_type": "事实型"
    },
    # 智能问答使用手册 (27.md)
    {
        "id": "q160",
        "question": "智能问答支持哪些问答类型？",
        "expected_answer": "智能问答支持事实查询、文档检索、问题解答、会议分析等类型。",
        "relevant_doc_ids": [27],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q161",
        "question": "如何进行精确匹配检索？",
        "expected_answer": "使用双引号进行精确匹配，例如\"项目截止日期\"。",
        "relevant_doc_ids": [27],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q162",
        "question": "如何排除不相关的检索结果？",
        "expected_answer": "使用减号排除关键词，例如\"会议纪要 -草稿\"。",
        "relevant_doc_ids": [27],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    # 会议模板库 (28.md)
    {
        "id": "q163",
        "question": "系统提供哪些会议模板？",
        "expected_answer": "系统提供周会模板、项目评审模板、头脑风暴模板等常用模板。",
        "relevant_doc_ids": [28],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    {
        "id": "q164",
        "question": "如何创建自定义会议模板？",
        "expected_answer": "创建自定义模板步骤：进入模板管理页面，点击\"新建模板\"，编辑模板内容，保存模板。",
        "relevant_doc_ids": [28],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    # 移动端开发计划 (29.md)
    {
        "id": "q165",
        "question": "移动端开发采用什么技术栈？",
        "expected_answer": "移动端采用React Native跨平台开发，技术栈包括React Native 0.72、TypeScript、Redux状态管理、React Navigation。",
        "relevant_doc_ids": [29],
        "difficulty": "medium",
        "category": "技术说明",
        "question_type": "事实型"
    },
    {
        "id": "q166",
        "question": "移动端预计什么时候发布？",
        "expected_answer": "移动端Q1 2024完成Beta版本，Q2 2024正式发布。",
        "relevant_doc_ids": [29],
        "difficulty": "easy",
        "category": "项目规划",
        "question_type": "事实型"
    },
    # 会议数据分析报告 (33.md)
    {
        "id": "q167",
        "question": "会议类型分布情况如何？",
        "expected_answer": "会议类型分布：部门会议50%、项目会议30%、跨部门会议15%、其他5%。",
        "relevant_doc_ids": [33],
        "difficulty": "easy",
        "category": "数据统计",
        "question_type": "事实型"
    },
    {
        "id": "q168",
        "question": "待办事项的状态分布是怎样的？",
        "expected_answer": "待办事项状态分布：待处理25%、进行中37%、已完成31%、已取消4%、延期3%。",
        "relevant_doc_ids": [33],
        "difficulty": "easy",
        "category": "数据统计",
        "question_type": "事实型"
    },
    {
        "id": "q169",
        "question": "检索效果的平均响应时间是多少？",
        "expected_answer": "检索效果的平均响应时间是280ms，平均相似度0.78，检索成功率95%，用户满意度88%。",
        "relevant_doc_ids": [33],
        "difficulty": "easy",
        "category": "数据统计",
        "question_type": "事实型"
    },
    # 会议智能助手技术白皮书 (34.md)
    {
        "id": "q170",
        "question": "系统采用什么架构？",
        "expected_answer": "系统采用微服务架构，包含语音处理模块、文本分析模块、向量检索模块、LLM集成模块、数据存储模块。",
        "relevant_doc_ids": [34],
        "difficulty": "easy",
        "category": "技术说明",
        "question_type": "事实型"
    },
    {
        "id": "q171",
        "question": "服务可用性目标是多少？",
        "expected_answer": "服务可用性目标是99.9%，数据持久性目标是99.999%。",
        "relevant_doc_ids": [34],
        "difficulty": "easy",
        "category": "性能优化",
        "question_type": "事实型"
    },
    # RAG技术深度解析 (35.md)
    {
        "id": "q172",
        "question": "RAG相比传统LLM有什么优势？",
        "expected_answer": "RAG相比传统LLM的优势：知识时效性强（可更新知识库）、回答准确性高（基于真实数据）、可追溯性好（可追溯到具体文档）、领域适配方便（只需更新知识库）。",
        "relevant_doc_ids": [35],
        "difficulty": "medium",
        "category": "概念解释",
        "question_type": "比较型"
    },
    {
        "id": "q173",
        "question": "RAG系统的工作流程是什么？",
        "expected_answer": "RAG工作流程：索引构建阶段（文档上传→文本切片→向量化处理→向量存储）、查询阶段（用户查询→查询向量化→向量检索→结果排序→上下文构建→LLM生成→回答输出）。",
        "relevant_doc_ids": [35],
        "difficulty": "medium",
        "category": "技术说明",
        "question_type": "事实型"
    },
    # 用户培训手册 (37.md)
    {
        "id": "q174",
        "question": "系统有哪些快捷键？",
        "expected_answer": "系统快捷键：Ctrl+K打开全局搜索、Ctrl+S保存当前内容、Ctrl+N新建会议、Ctrl+U上传文档。",
        "relevant_doc_ids": [37],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q175",
        "question": "如何找回密码？",
        "expected_answer": "点击登录页面的\"忘记密码\"链接，按照提示操作即可找回密码。",
        "relevant_doc_ids": [37],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    # 版本更新日志 (38.md)
    {
        "id": "q176",
        "question": "v2.0.0版本新增了哪些功能？",
        "expected_answer": "v2.0.0版本新增功能：智能问答、RAG技术支持、向量检索模块、待办事项管理、会议模板功能。",
        "relevant_doc_ids": [38],
        "difficulty": "easy",
        "category": "版本更新",
        "question_type": "事实型"
    },
    {
        "id": "q177",
        "question": "v1.5.0版本改进了什么？",
        "expected_answer": "v1.5.0版本改进：优化移动端适配、改进会议创建流程、优化文档检索速度。",
        "relevant_doc_ids": [38],
        "difficulty": "easy",
        "category": "版本更新",
        "question_type": "事实型"
    },
    # 会议常见问题 (40.md)
    {
        "id": "q178",
        "question": "如何准备会议材料？",
        "expected_answer": "准备会议材料步骤：明确会议目标、收集相关资料、制作演示文稿、提前发送给参会人员。",
        "relevant_doc_ids": [40],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q179",
        "question": "如何做好会议记录？",
        "expected_answer": "做好会议记录需要记录关键决策、记录行动项和责任人、记录待跟进事项、使用会议纪要模板。",
        "relevant_doc_ids": [40],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    # 会议纪要写作指南 (42.md)
    {
        "id": "q180",
        "question": "会议纪要应该包含哪些基本信息？",
        "expected_answer": "会议纪要基本信息包括：会议标题、会议时间、会议地点、参会人员、主持人、记录员。",
        "relevant_doc_ids": [42],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    {
        "id": "q181",
        "question": "会议纪要写作有哪些技巧？",
        "expected_answer": "会议纪要写作技巧：简明扼要、条理清晰、准确客观。",
        "relevant_doc_ids": [42],
        "difficulty": "easy",
        "category": "操作指南",
        "question_type": "事实型"
    },
    # 企业培训计划 (43.md)
    {
        "id": "q182",
        "question": "新员工培训包含哪些课程？",
        "expected_answer": "新员工培训包含：公司文化（1天）、业务流程（2天）、系统使用（1天）。",
        "relevant_doc_ids": [43],
        "difficulty": "easy",
        "category": "培训管理",
        "question_type": "事实型"
    },
    {
        "id": "q183",
        "question": "培训评估指标有哪些？",
        "expected_answer": "培训评估指标包括：培训完成率、考试通过率、应用效果等。",
        "relevant_doc_ids": [43],
        "difficulty": "easy",
        "category": "培训管理",
        "question_type": "事实型"
    },
    # 数据隐私保护政策 (45.md)
    {
        "id": "q184",
        "question": "系统收集哪些敏感信息？",
        "expected_answer": "系统收集的敏感信息包括：会议内容、文档内容、待办事项。",
        "relevant_doc_ids": [45],
        "difficulty": "easy",
        "category": "安全合规",
        "question_type": "事实型"
    },
    {
        "id": "q185",
        "question": "用户有哪些数据权利？",
        "expected_answer": "用户数据权利包括：访问权、修改权、删除权、拒绝权。",
        "relevant_doc_ids": [45],
        "difficulty": "easy",
        "category": "安全合规",
        "question_type": "事实型"
    },
    # 会议成本分析 (46.md)
    {
        "id": "q186",
        "question": "会议的直接成本包括哪些？",
        "expected_answer": "会议直接成本包括：场地费用、设备费用、餐饮费用、差旅费用。",
        "relevant_doc_ids": [46],
        "difficulty": "easy",
        "category": "会议管理",
        "question_type": "事实型"
    },
    {
        "id": "q187",
        "question": "如何优化会议成本？",
        "expected_answer": "会议成本优化策略：控制会议时长、减少参会人数、使用视频会议、合并相关会议。",
        "relevant_doc_ids": [46],
        "difficulty": "medium",
        "category": "会议管理",
        "question_type": "推理型"
    },
    # 会议效率提升指南 (48.md)
    {
        "id": "q188",
        "question": "会议效率评估指标有哪些？",
        "expected_answer": "会议效率评估指标：准时率（>90%）、参与率（>80%）、决策率（>70%）、行动项完成率（>85%）。",
        "relevant_doc_ids": [48],
        "difficulty": "easy",
        "category": "会议管理",
        "question_type": "事实型"
    },
    {
        "id": "q189",
        "question": "如何提升会议效率？",
        "expected_answer": "提升会议效率策略：会前明确目标和议程、提前发送材料；会议中准时开始、主持人控场；会后及时发送纪要、跟踪行动项。",
        "relevant_doc_ids": [48],
        "difficulty": "medium",
        "category": "会议管理",
        "question_type": "推理型"
    },
    # === 更多推理型和多跳型问题 ===
    {
        "id": "q190",
        "question": "会议智能助手的技术架构如何支撑其核心功能？",
        "expected_answer": "系统采用微服务架构，语音处理模块支撑语音转写功能，文本分析模块支撑纪要生成和待办抽取，向量检索模块支撑智能问答功能，LLM集成模块支撑回答生成。",
        "relevant_doc_ids": [1, 2, 34],
        "difficulty": "hard",
        "category": "综合问题",
        "question_type": "推理型"
    },
    {
        "id": "q191",
        "question": "为什么说RAG技术能提升问答准确性？",
        "expected_answer": "RAG技术通过向量检索从知识库中获取相关上下文，LLM基于这些真实数据生成回答，避免了传统LLM的幻觉问题，从而提高了回答的准确性和可验证性。",
        "relevant_doc_ids": [2, 35],
        "difficulty": "hard",
        "category": "综合问题",
        "question_type": "推理型"
    },
    {
        "id": "q192",
        "question": "文档管理和权限管理是如何配合工作的？",
        "expected_answer": "文档上传时可以关联部门，权限管理通过RBAC实现部门隔离和角色权限控制，确保文档只能被授权用户访问。",
        "relevant_doc_ids": [3, 19],
        "difficulty": "hard",
        "category": "综合问题",
        "question_type": "多跳型"
    },
    {
        "id": "q193",
        "question": "数据安全措施如何保护会议内容？",
        "expected_answer": "通过传输加密（HTTPS/TLS 1.3）保护传输过程，存储加密（AES-256）保护存储数据，访问控制（RBAC）确保只有授权用户能访问，定期备份确保数据持久性。",
        "relevant_doc_ids": [13, 45],
        "difficulty": "medium",
        "category": "安全合规",
        "question_type": "推理型"
    },
    {
        "id": "q194",
        "question": "性能优化策略如何提升用户体验？",
        "expected_answer": "通过缓存策略减少响应时间，向量索引优化提升检索速度，微服务架构支持水平扩展，这些优化措施共同提升了系统的响应速度和可用性。",
        "relevant_doc_ids": [14, 34],
        "difficulty": "medium",
        "category": "性能优化",
        "question_type": "推理型"
    },
    # === 否定型问题 ===
    {
        "id": "q195",
        "question": "系统不支持哪些权限变更？",
        "expected_answer": "普通用户不能直接变更自己的权限，权限变更需要经过管理员审核，不能绕过审核流程。",
        "relevant_doc_ids": [19],
        "difficulty": "medium",
        "category": "权限管理",
        "question_type": "否定型"
    },
    {
        "id": "q196",
        "question": "会议纪要不包含哪些内容？",
        "expected_answer": "会议纪要不包含参会人员的私人聊天内容、与会议无关的讨论、未经确认的猜测性信息。",
        "relevant_doc_ids": [5],
        "difficulty": "medium",
        "category": "功能说明",
        "question_type": "否定型"
    },
    # === 比较型问题 ===
    {
        "id": "q197",
        "question": "新员工培训和在职培训有什么区别？",
        "expected_answer": "新员工培训侧重公司文化、业务流程、系统使用等基础内容；在职培训侧重专业技能、管理能力、软技能提升等进阶内容。",
        "relevant_doc_ids": [43],
        "difficulty": "medium",
        "category": "培训管理",
        "question_type": "比较型"
    },
    {
        "id": "q198",
        "question": "线上培训和线下培训各有什么优缺点？",
        "expected_answer": "线上培训优点：灵活便捷、成本低；缺点：互动性差。线下培训优点：互动性强、学习效果好；缺点：成本高、时间不灵活。",
        "relevant_doc_ids": [43],
        "difficulty": "medium",
        "category": "培训管理",
        "question_type": "比较型"
    },
    # === 更多事实型问题 ===
    {
        "id": "q199",
        "question": "系统支持的日志级别有哪些？",
        "expected_answer": "系统支持的日志级别包括DEBUG、INFO、WARNING、ERROR。",
        "relevant_doc_ids": [8],
        "difficulty": "easy",
        "category": "配置部署",
        "question_type": "事实型"
    },
    {
        "id": "q200",
        "question": "API访问令牌过期时间是多少？",
        "expected_answer": "API访问令牌过期时间是30分钟。",
        "relevant_doc_ids": [8],
        "difficulty": "easy",
        "category": "配置部署",
        "question_type": "事实型"
    },
    # === 新增文档覆盖问题 ===
    # 44.md - 会议数据分析报告
    {
        "id": "q201",
        "question": "会议数据分析包含哪些维度？",
        "expected_answer": "会议数据分析包含会议效率分析、参与度分析、决策质量分析等维度。",
        "relevant_doc_ids": [44],
        "difficulty": "easy",
        "category": "数据分析",
        "question_type": "事实型"
    },
    {
        "id": "q202",
        "question": "会议准时率如何计算？",
        "expected_answer": "会议准时率 = 准时开始会议数 / 总会议数。",
        "relevant_doc_ids": [44],
        "difficulty": "easy",
        "category": "数据分析",
        "question_type": "事实型"
    },
    {
        "id": "q203",
        "question": "决策完成率和待办完成率有什么区别？",
        "expected_answer": "决策完成率衡量已完成决策数占总决策数的比例；待办完成率衡量已完成待办数占总待办数的比例，两者评估的对象不同。",
        "relevant_doc_ids": [44],
        "difficulty": "medium",
        "category": "数据分析",
        "question_type": "比较型"
    },
    # 45.md - 会议安全与合规指南
    {
        "id": "q204",
        "question": "系统采用什么加密方式存储敏感数据？",
        "expected_answer": "系统使用AES-256加密存储敏感数据。",
        "relevant_doc_ids": [45],
        "difficulty": "easy",
        "category": "安全合规",
        "question_type": "事实型"
    },
    {
        "id": "q205",
        "question": "用户数据传输采用什么协议？",
        "expected_answer": "所有数据传输采用HTTPS协议。",
        "relevant_doc_ids": [45],
        "difficulty": "easy",
        "category": "安全合规",
        "question_type": "事实型"
    },
    {
        "id": "q206",
        "question": "安全事件处理流程包括哪些步骤？",
        "expected_answer": "安全事件处理流程包括：检测安全事件、评估影响范围、隔离受影响系统、通知相关人员、恢复系统功能、记录事件报告。",
        "relevant_doc_ids": [45],
        "difficulty": "medium",
        "category": "安全合规",
        "question_type": "事实型"
    },
    # 46.md - API使用指南
    {
        "id": "q207",
        "question": "API请求需要携带什么认证信息？",
        "expected_answer": "所有API请求需要在请求头中携带访问令牌：Authorization: Bearer <access_token>。",
        "relevant_doc_ids": [46],
        "difficulty": "easy",
        "category": "API文档",
        "question_type": "事实型"
    },
    {
        "id": "q208",
        "question": "文档上传接口的HTTP方法是什么？",
        "expected_answer": "文档上传接口使用POST方法，路径为/api/v1/documents/upload。",
        "relevant_doc_ids": [46],
        "difficulty": "easy",
        "category": "API文档",
        "question_type": "事实型"
    },
    {
        "id": "q209",
        "question": "语义检索接口的请求参数有哪些？",
        "expected_answer": "语义检索接口的请求参数包括query（查询内容）和top_k（返回结果数量）。",
        "relevant_doc_ids": [46],
        "difficulty": "medium",
        "category": "API文档",
        "question_type": "事实型"
    },
    # 47.md - 部署指南
    {
        "id": "q210",
        "question": "生产环境的硬件要求是什么？",
        "expected_answer": "生产环境要求：16核CPU、32GB内存、500GB存储。",
        "relevant_doc_ids": [47],
        "difficulty": "easy",
        "category": "配置部署",
        "question_type": "事实型"
    },
    {
        "id": "q211",
        "question": "系统支持哪些部署方式？",
        "expected_answer": "系统支持直接部署和Docker部署两种方式。",
        "relevant_doc_ids": [47],
        "difficulty": "easy",
        "category": "配置部署",
        "question_type": "事实型"
    },
    {
        "id": "q212",
        "question": "从v1.x升级到v2.0需要哪些步骤？",
        "expected_answer": "升级步骤包括：备份数据库、升级依赖包、运行数据库迁移、配置新功能参数、测试验证。",
        "relevant_doc_ids": [50, 47],
        "difficulty": "medium",
        "category": "配置部署",
        "question_type": "事实型"
    },
    # 48.md - 移动端方案
    {
        "id": "q213",
        "question": "移动端应用支持哪些平台？",
        "expected_answer": "移动端应用支持iOS和Android平台。",
        "relevant_doc_ids": [48],
        "difficulty": "easy",
        "category": "产品规划",
        "question_type": "事实型"
    },
    {
        "id": "q214",
        "question": "移动端的核心功能有哪些？",
        "expected_answer": "移动端核心功能包括：会议列表、会议详情、语音转写、纪要查看、待办管理、智能问答。",
        "relevant_doc_ids": [48],
        "difficulty": "easy",
        "category": "产品规划",
        "question_type": "事实型"
    },
    {
        "id": "q215",
        "question": "移动端采用什么前端框架开发？",
        "expected_answer": "移动端采用Flutter框架开发，支持跨平台。",
        "relevant_doc_ids": [48],
        "difficulty": "medium",
        "category": "技术架构",
        "question_type": "事实型"
    },
    # 49.md - 培训手册
    {
        "id": "q216",
        "question": "培训手册包含哪些部分？",
        "expected_answer": "培训手册包含系统概述、基础操作、高级功能、管理员培训等部分。",
        "relevant_doc_ids": [49],
        "difficulty": "easy",
        "category": "培训管理",
        "question_type": "事实型"
    },
    {
        "id": "q217",
        "question": "培训考核包含哪些方式？",
        "expected_answer": "培训考核包含理论考试、实操考核、综合评估三种方式。",
        "relevant_doc_ids": [49],
        "difficulty": "easy",
        "category": "培训管理",
        "question_type": "事实型"
    },
    # 50.md - 更新日志
    {
        "id": "q218",
        "question": "v2.0.0版本新增了哪些功能？",
        "expected_answer": "v2.0.0版本新增了RAG智能问答、会议数据分析、批量操作功能。",
        "relevant_doc_ids": [50],
        "difficulty": "easy",
        "category": "版本更新",
        "question_type": "事实型"
    },
    {
        "id": "q219",
        "question": "v2.1.0版本计划发布哪些功能？",
        "expected_answer": "v2.1.0版本计划发布移动端App、第三方工具集成、智能推荐功能。",
        "relevant_doc_ids": [50],
        "difficulty": "easy",
        "category": "版本更新",
        "question_type": "事实型"
    },
    {
        "id": "q220",
        "question": "升级前需要注意什么？",
        "expected_answer": "升级前需要备份数据、建议在非业务高峰期进行、升级后需要重新生成向量索引。",
        "relevant_doc_ids": [50],
        "difficulty": "medium",
        "category": "版本更新",
        "question_type": "事实型"
    },
    # 干扰文档相关问题
    {
        "id": "q221",
        "question": "系统支持的会议数据分析图表类型有哪些？",
        "expected_answer": "系统支持的图表类型包括柱状图、折线图、饼图、热力图。",
        "relevant_doc_ids": [44],
        "difficulty": "easy",
        "category": "数据分析",
        "question_type": "事实型"
    },
    {
        "id": "q222",
        "question": "双因素认证支持哪些方式？",
        "expected_answer": "双因素认证支持短信验证、认证器应用、硬件密钥。",
        "relevant_doc_ids": [45],
        "difficulty": "easy",
        "category": "安全合规",
        "question_type": "事实型"
    },
    # === 补充未覆盖文档的问题 ===
    # 11.md - 产品更新日志
    {
        "id": "q223",
        "question": "v2.0.0版本新增了哪些功能？",
        "expected_answer": "v2.0.0版本新增了RAG知识库问答功能、向量语义检索、会议时序分层检索、多模态文档支持。",
        "relevant_doc_ids": [11],
        "difficulty": "easy",
        "category": "版本更新",
        "question_type": "事实型"
    },
    # 18.md - 会议效率提升指南
    {
        "id": "q224",
        "question": "如何提高会议效率？",
        "expected_answer": "提高会议效率的方法包括：明确会议目标、控制参会人数、制定议程、准时开始和结束、会后跟进等。",
        "relevant_doc_ids": [18],
        "difficulty": "medium",
        "category": "会议管理",
        "question_type": "推理型"
    },
    # 20.md - 会议成本分析
    {
        "id": "q225",
        "question": "会议成本包含哪些方面？",
        "expected_answer": "会议成本包括人力成本、时间成本、场地成本、设备成本、差旅成本等。",
        "relevant_doc_ids": [20],
        "difficulty": "easy",
        "category": "会议管理",
        "question_type": "事实型"
    },
    # 30.md - 干扰文档-天气信息
    {
        "id": "q226",
        "question": "会议智能助手是否提供天气查询功能？",
        "expected_answer": "会议智能助手不提供天气查询功能，这不属于会议相关的功能范围。",
        "relevant_doc_ids": [30],
        "difficulty": "medium",
        "category": "功能说明",
        "question_type": "否定型"
    },
    # 31.md - 干扰文档-体育新闻
    {
        "id": "q227",
        "question": "会议智能助手是否支持体育赛事信息查询？",
        "expected_answer": "会议智能助手不支持体育赛事信息查询，专注于会议相关功能。",
        "relevant_doc_ids": [31],
        "difficulty": "medium",
        "category": "功能说明",
        "question_type": "否定型"
    },
    # 32.md - 干扰文档-财经新闻
    {
        "id": "q228",
        "question": "会议智能助手是否提供股票行情查询？",
        "expected_answer": "会议智能助手不提供股票行情查询功能，专注于企业会议场景。",
        "relevant_doc_ids": [32],
        "difficulty": "medium",
        "category": "功能说明",
        "question_type": "否定型"
    },
    # 36.md - 系统性能优化指南
    {
        "id": "q229",
        "question": "如何优化系统性能？",
        "expected_answer": "系统性能优化方法包括：优化数据库查询、使用缓存、异步处理、代码优化、硬件升级等。",
        "relevant_doc_ids": [36],
        "difficulty": "medium",
        "category": "技术优化",
        "question_type": "推理型"
    },
    # 39.md - 会议模板库
    {
        "id": "q230",
        "question": "系统提供哪些会议模板？",
        "expected_answer": "系统提供项目例会、周会、技术评审、需求讨论等多种会议模板。",
        "relevant_doc_ids": [39],
        "difficulty": "easy",
        "category": "功能说明",
        "question_type": "事实型"
    },
    # 41.md - 移动端开发计划
    {
        "id": "q231",
        "question": "移动端开发计划包含哪些阶段？",
        "expected_answer": "移动端开发计划包含需求分析、设计阶段、开发阶段、测试阶段、发布阶段。",
        "relevant_doc_ids": [41],
        "difficulty": "easy",
        "category": "产品规划",
        "question_type": "事实型"
    },
    # 12.md - 干扰文档-旅游指南
    {
        "id": "q232",
        "question": "会议智能助手是否提供旅游攻略查询？",
        "expected_answer": "会议智能助手不提供旅游攻略查询功能，这与会议场景无关。",
        "relevant_doc_ids": [12],
        "difficulty": "medium",
        "category": "功能说明",
        "question_type": "否定型"
    },
    # 15.md - 干扰文档-菜谱大全
    {
        "id": "q233",
        "question": "会议智能助手是否提供菜谱查询功能？",
        "expected_answer": "会议智能助手不提供菜谱查询功能，专注于会议相关的智能助手服务。",
        "relevant_doc_ids": [15],
        "difficulty": "medium",
        "category": "功能说明",
        "question_type": "否定型"
    }
]


# 负例问题（文档库中没有答案的问题）
NEGATIVE_EXAMPLES = [
    {"id": "neg1", "question": "会议智能助手是否支持实时视频会议？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "功能介绍", "question_type": "事实型"},
    {"id": "neg2", "question": "系统是否支持接入钉钉会议？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "功能介绍", "question_type": "事实型"},
    {"id": "neg3", "question": "会议智能助手的市场占有率是多少？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "市场分析", "question_type": "事实型"},
    {"id": "neg4", "question": "系统是否支持语音唤醒功能？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "功能介绍", "question_type": "事实型"},
    {"id": "neg5", "question": "会议智能助手是否有移动端APP？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "功能介绍", "question_type": "事实型"},
    {"id": "neg6", "question": "系统支持哪些云存储服务？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "配置部署", "question_type": "事实型"},
    {"id": "neg7", "question": "会议智能助手的研发团队有多少人？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "公司信息", "question_type": "事实型"},
    {"id": "neg8", "question": "系统是否支持VR会议功能？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "功能介绍", "question_type": "事实型"},
    {"id": "neg9", "question": "会议智能助手的客户有哪些？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "客户信息", "question_type": "事实型"},
    {"id": "neg10", "question": "系统是否支持多语言实时翻译？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "功能介绍", "question_type": "事实型"},
    {"id": "neg11", "question": "会议智能助手是否有API接口文档？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "medium", "category": "API文档", "question_type": "事实型"},
    {"id": "neg12", "question": "系统是否支持自定义主题颜色？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "界面配置", "question_type": "事实型"},
    {"id": "neg13", "question": "会议智能助手的服务器部署在哪里？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "部署信息", "question_type": "事实型"},
    {"id": "neg14", "question": "系统是否支持电子签名功能？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "功能介绍", "question_type": "事实型"},
    {"id": "neg15", "question": "会议智能助手的价格是多少？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "价格信息", "question_type": "事实型"},
    {"id": "neg16", "question": "系统是否支持接入企业微信会议？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "功能介绍", "question_type": "事实型"},
    {"id": "neg17", "question": "会议智能助手是否支持离线使用？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "功能介绍", "question_type": "事实型"},
    {"id": "neg18", "question": "系统是否支持AI绘图功能？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "功能介绍", "question_type": "事实型"},
    {"id": "neg19", "question": "会议智能助手是否支持多租户部署？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "medium", "category": "部署信息", "question_type": "事实型"},
    {"id": "neg20", "question": "系统是否支持Webhook通知？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "medium", "category": "集成功能", "question_type": "事实型"},
    {"id": "neg21", "question": "会议智能助手的SLA服务等级协议是什么？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "medium", "category": "服务协议", "question_type": "事实型"},
    {"id": "neg22", "question": "系统是否支持数据导出到Excel？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "数据导出", "question_type": "事实型"},
    {"id": "neg23", "question": "会议智能助手是否支持OAuth登录？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "medium", "category": "认证授权", "question_type": "事实型"},
    {"id": "neg24", "question": "系统是否支持消息推送功能？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "功能介绍", "question_type": "事实型"},
    {"id": "neg25", "question": "会议智能助手是否支持私有化部署？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "medium", "category": "部署信息", "question_type": "事实型"},
    {"id": "neg26", "question": "系统是否支持屏幕共享录制？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "功能介绍", "question_type": "事实型"},
    {"id": "neg27", "question": "会议智能助手的API调用频率限制是多少？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "medium", "category": "API文档", "question_type": "事实型"},
    {"id": "neg28", "question": "系统是否支持LDAP认证？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "medium", "category": "认证授权", "question_type": "事实型"},
    {"id": "neg29", "question": "会议智能助手是否支持智能问答机器人？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "功能介绍", "question_type": "事实型"},
    {"id": "neg30", "question": "系统是否支持定时会议提醒？", "expected_answer": "文档库中没有相关信息", "relevant_doc_ids": [], "difficulty": "easy", "category": "功能介绍", "question_type": "事实型"},
]


def get_eval_dataset() -> list:
    """获取评估数据集（包含正例和负例）"""
    return RAG_EVAL_DATASET + NEGATIVE_EXAMPLES


def get_question_by_id(question_id: str) -> dict:
    """根据ID获取单个问题"""
    for item in RAG_EVAL_DATASET:
        if item["id"] == question_id:
            return item
    return None


def get_questions_by_category(category: str) -> list:
    """按类别获取问题"""
    return [item for item in RAG_EVAL_DATASET if item["category"] == category]


def get_questions_by_difficulty(difficulty: str) -> list:
    """按难度获取问题"""
    return [item for item in RAG_EVAL_DATASET if item["difficulty"] == difficulty]