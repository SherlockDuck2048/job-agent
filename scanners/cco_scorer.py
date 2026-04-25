"""
CCO Job Scorer - CCO岗位匹配评分算法
基于cco-scorer.js完全一致的评分逻辑
从keywords-v2.json加载配置

评分流程（两阶段）：
1. 初筛（快速）：基于title + 关键词快速排除明显不相关的岗位
2. 详评：对于通过初筛的岗位，获取JD详情后进行完整评分
"""
import json
import re
import os

# 加载keywords配置 - 优先使用job-agent本地配置，回退到ai-job-scanner
KEYWORDS_PATH_LOCAL = os.path.join(os.path.dirname(__file__), '..', 'config', 'keywords-v2.json')
KEYWORDS_PATH_FALLBACK = os.path.join(os.path.dirname(__file__), '..', '..', 'ai-job-scanner', 'config', 'keywords-v2.json')

# 全局缓存配置
_keywords_cache = None

def load_keywords():
    """加载keywords-v2.json配置 - 优先本地，其次回退"""
    global _keywords_cache
    if _keywords_cache is not None:
        return _keywords_cache

    # 尝试本地配置
    try:
        with open(KEYWORDS_PATH_LOCAL, 'r', encoding='utf-8') as f:
            _keywords_cache = json.load(f)
        return _keywords_cache
    except FileNotFoundError:
        pass

    # 尝试回退配置
    try:
        with open(KEYWORDS_PATH_FALLBACK, 'r', encoding='utf-8') as f:
            _keywords_cache = json.load(f)
        return _keywords_cache
    except FileNotFoundError:
        # 如果都找不到，使用内置默认配置
        _keywords_cache = _get_default_keywords()
        return _keywords_cache

def _get_default_keywords():
    """内置默认配置（当JSON文件不存在时使用）"""
    return {
        "job_type_scores": {
            "high_match": {
                "titles": ["AI Business Analyst", "AI Process Optimization", "Business Analyst", "Project Manager", "Product Manager"],
                "base_score": 100,
                "priority": "P0"
            },
            "medium_match": {
                "titles": ["GenAI Solution Consultant", "Digital Transformation", "Data Analyst", "AI Product Manager"],
                "base_score": 85,
                "priority": "P1"
            },
            "low_match": {
                "titles": ["AI Engineer", "Data Scientist", "ML Engineer"],
                "base_score": 60,
                "priority": "P2"
            }
        },
        "tech_penalty_keywords": {
            "high_penalty": {"keywords": ["strong proficiency in python", "tensorflow", "pytorch"], "penalty": 35, "reason": "技术要求过高，需要hands-on开发/建模"},
            "medium_penalty": {"keywords": ["python proficiency", "mlops"], "penalty": 20, "reason": "需要编程/技术能力"},
            "low_penalty": {"keywords": ["python", "sql"], "penalty": 10, "reason": "涉及技术背景"}
        },
        "exclusion_keywords": {
            "non_ai": {"keywords": ["traditional role"], "penalty": 45, "reason": "与AI无关"},
            "sales": {"keywords": ["sales role", "business development"], "penalty": 35, "reason": "销售性质岗位"}
        },
        "experience_penalty": {
            "threshold_10": {"min_years": 10, "penalty": 15, "reason": "要求10年以上经验"},
            "threshold_8": {"min_years": 8, "penalty": 10, "reason": "要求8年以上经验"}
        },
        "bonus_keywords": {
            "genai": {"keywords": ["genai", "llm", "rag"], "bonus": 10, "reason": "GenAI/LLM相关"},
            "fintech": {"keywords": ["fintech", "banking", "insurance"], "bonus": 5, "reason": "金融科技行业"},
            "hongkong": {"keywords": ["hong kong", "hk", "香港"], "bonus": 3, "reason": "香港本地"}
        },
        "good_fit_indicators": {
            "keywords": ["business analysis", "process optimization", "digital transformation"],
            "bonus": 5,
            "reason": "符合CCO核心能力"
        },
        "quick_filter": {
            "must_have_keywords": ["ai", "data", "business", "product", "project", "process", "digital", "genai", "llm", "agent", "rag", "analyst", "manager", "consultant"],
            "exclude_keywords": ["intern", "junior", "entry", "fresh graduate", "trainee"]
        }
    }


class CCOSCORER:
    """CCO岗位评分器 - 两阶段评分"""
    
    def __init__(self):
        self.keywords = load_keywords()
    
    def quick_filter(self, job):
        """
        Stage 1: Quick filter - based on title, exclude obviously irrelevant jobs
        
        Args:
            job: dict with keys: title, description (optional)
        
        Returns:
            dict: { 'passed': bool, 'reason': str }
        """
        import re
        title = job.get('title', '').lower()
        # 补充字段：URL slug 中的关键词（Workday 会把搜索词放在 URL 路径里）
        extra = job.get('_title_for_filter', '').lower()
        if extra and extra != title:
            title += ' ' + extra
        
        # If no title, reject
        if not title or len(title.strip()) == 0:
            return {'passed': False, 'reason': 'no title'}
        
        # Check must-have keywords (at least one must match)
        must_have = self.keywords.get('quick_filter', {}).get('must_have_keywords', [])
        if must_have:
            has_keyword = any(kw in title for kw in must_have)
            if not has_keyword:
                return {'passed': False, 'reason': f'title lacks key domain terms'}
        
        # Check exclude keywords (use word boundary to avoid "intern" matching "International")
        exclude_kw = self.keywords.get('quick_filter', {}).get('exclude_keywords', [])
        if exclude_kw:
            for kw in exclude_kw:
                kw_stripped = kw.strip()
                if not kw_stripped:
                    continue
                # Match as whole word: "intern" won't match "international"
                pattern = r'\b' + re.escape(kw_stripped) + r'\b'
                if re.search(pattern, title):
                    return {'passed': False, 'reason': f'exclude keyword: {kw_stripped}'}
        
        return {'passed': True, 'reason': 'passed quick filter'}
    
    def calculate_score(self, job, skip_quick_filter=False):
        """
        主评分函数（两阶段）
        
        Args:
            job: dict with keys: title, description, company, yearsRequired (optional)
            skip_quick_filter: bool, 是否跳过初筛（用于批量评分时已过滤的情况）
        
        Returns:
            dict: 评分结果
        """
        # 阶段1：快速初筛
        if not skip_quick_filter:
            filter_result = self.quick_filter(job)
            if not filter_result['passed']:
                return {
                    'score': 0,
                    'priority': 'P3',
                    'comment': f'初筛未通过: {filter_result["reason"]}',
                    'details': [],
                    'isRecommended': False,
                    'reason': filter_result['reason'],
                    'filter_stage': 'quick_filter'
                }
        
        # 阶段2：完整评分（需要description）
        title = job.get('title', '')
        description = job.get('description', '')
        text = f"{title} {description}".lower()
        
        scoring_details = []
        
        # 1. 基础分（基于岗位类型）
        base_score = self._get_base_score(title)
        scoring_details.append({
            'factor': '岗位类型基础分',
            'score': base_score,
            'reason': self._get_job_type(title)
        })
        
        # 1b. Title 年资惩罚（推断级别）
        title_penalty = self._calculate_title_penalty(title)
        scoring_details.append({
            'factor': 'Title年资级别',
            'score': -title_penalty['penalty'],
            'reason': title_penalty.get('reason', '无年资惩罚')
        })
        
        # 2. 技术强度惩罚
        tech_penalty = self._calculate_tech_penalty(text)
        scoring_details.append({
            'factor': '技术强度',
            'score': -tech_penalty['penalty'],
            'reason': tech_penalty.get('reason', '无技术惩罚')
        })
        
        # 3. 排除项惩罚
        exclusion_penalty = self._calculate_exclusion_penalty(text)
        scoring_details.append({
            'factor': '排除项',
            'score': -exclusion_penalty['penalty'],
            'reason': exclusion_penalty.get('reason', '无排除项')
        })
        
        # 4. 经验年限惩罚
        years_required = job.get('yearsRequired') or self._extract_experience_years(text)
        exp_penalty = self._calculate_experience_penalty(years_required)
        scoring_details.append({
            'factor': '经验要求',
            'score': -exp_penalty['penalty'],
            'reason': exp_penalty.get('reason', '经验要求合适')
        })
        
        # 5. 加分项
        bonus = self._calculate_bonus(text)
        scoring_details.append({
            'factor': '加分项',
            'score': bonus['bonus'],
            'reason': bonus.get('reason', '无加分')
        })
        
        # 6. 适合度指标
        fit_bonus = self._calculate_fit_bonus(text)
        scoring_details.append({
            'factor': '能力匹配',
            'score': fit_bonus['bonus'],
            'reason': fit_bonus.get('reason', '标准匹配')
        })
        
        # 计算最终分数
        final_score = (base_score 
            - title_penalty['penalty'] 
            - tech_penalty['penalty'] 
            - exclusion_penalty['penalty'] 
            - exp_penalty['penalty'] 
            + bonus['bonus'] 
            + fit_bonus['bonus'])
        
        # 限制在 50-100 范围
        final_score = max(50, min(100, final_score))
        
        # 确定优先级
        priority = self._get_priority(final_score, tech_penalty['penalty'], exclusion_penalty['penalty'], title_penalty['penalty'])
        
        # 生成评语
        comment = self._generate_comment(final_score, priority, scoring_details)
        
        return {
            'score': final_score,
            'priority': priority,
            'comment': comment,
            'details': scoring_details,
            'isRecommended': priority in ['P0', 'P1'],
            'reason': self._get_main_reason(scoring_details),
            'filter_stage': 'full_scoring'
        }
    
    def _normalize(self, text):
        """归一化标题：去除标点、转小写、压缩空格（用于关键词匹配）"""
        import re
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)   # 去除标点符号（破折号/斜杠等）
        text = re.sub(r'\s+', ' ', text).strip()  # 压缩多余空格
        return text

    def _get_base_score(self, title):
        """获取岗位基础分"""
        norm_title = self._normalize(title)
        job_types = self.keywords['job_type_scores']
        
        # 高匹配岗位
        for t in job_types['high_match']['titles']:
            if t.lower() in norm_title:
                return job_types['high_match']['base_score']
        
        # 中等匹配岗位
        for t in job_types['medium_match']['titles']:
            if t.lower() in norm_title:
                return job_types['medium_match']['base_score']
        
        # 低匹配岗位
        for t in job_types['low_match']['titles']:
            if t.lower() in norm_title:
                return job_types['low_match']['base_score']
        
        return 70  # 默认基础分
    
    def _get_job_type(self, title):
        """获取岗位类型描述"""
        norm_title = self._normalize(title)
        job_types = self.keywords['job_type_scores']
        
        if any(t.lower() in norm_title for t in job_types['high_match']['titles']):
            return '高匹配岗位'
        if any(t.lower() in norm_title for t in job_types['medium_match']['titles']):
            return '中等匹配岗位'
        if any(t.lower() in norm_title for t in job_types['low_match']['titles']):
            return '低匹配岗位'
        return '未知类型'
    
    def _calculate_tech_penalty(self, text):
        """计算技术强度惩罚"""
        max_penalty = 0
        reason = ''
        tech_keywords = self.keywords['tech_penalty_keywords']
        
        # 高惩罚关键词
        for kw in tech_keywords['high_penalty']['keywords']:
            if kw.lower() in text:
                if tech_keywords['high_penalty']['penalty'] > max_penalty:
                    max_penalty = tech_keywords['high_penalty']['penalty']
                    reason = tech_keywords['high_penalty']['reason']
        
        # 中等惩罚关键词
        if max_penalty == 0:
            for kw in tech_keywords['medium_penalty']['keywords']:
                if kw.lower() in text:
                    if tech_keywords['medium_penalty']['penalty'] > max_penalty:
                        max_penalty = tech_keywords['medium_penalty']['penalty']
                        reason = tech_keywords['medium_penalty']['reason']
        
        # 低惩罚关键词
        if max_penalty == 0:
            for kw in tech_keywords['low_penalty']['keywords']:
                if kw.lower() in text:
                    if tech_keywords['low_penalty']['penalty'] > max_penalty:
                        max_penalty = tech_keywords['low_penalty']['penalty']
                        reason = tech_keywords['low_penalty']['reason']
        
        return {'penalty': max_penalty, 'reason': reason}
    
    def _calculate_exclusion_penalty(self, text):
        """计算排除项惩罚"""
        max_penalty = 0
        reason = ''
        exclusion = self.keywords['exclusion_keywords']
        
        for category in ['non_ai', 'sales']:
            config = exclusion[category]
            for kw in config['keywords']:
                if kw.lower() in text:
                    if config['penalty'] > max_penalty:
                        max_penalty = config['penalty']
                        reason = config['reason']
        
        return {'penalty': max_penalty, 'reason': reason}
    
    def _calculate_experience_penalty(self, years_required):
        """计算经验年限惩罚"""
        # 如果没有明确的 years_required，尝试从 title 中推断
        if not years_required:
            # 高级别关键词暗示高年限要求（隐性惩罚）
            title_lower = ''  # 需要外部传入 title，暂用启发式
            return {'penalty': 0, 'reason': ''}
        
        exp_config = self.keywords['experience_penalty']
        
        if years_required >= exp_config['threshold_10']['min_years']:
            return {
                'penalty': exp_config['threshold_10']['penalty'],
                'reason': exp_config['threshold_10']['reason']
            }
        
        if years_required >= exp_config['threshold_8']['min_years']:
            return {
                'penalty': exp_config['threshold_8']['penalty'],
                'reason': exp_config['threshold_8']['reason']
            }
        
        return {'penalty': 0, 'reason': ''}
    
    def _calculate_title_penalty(self, title):
        """
        从 title 推断经验级别惩罚（辅助判断 seniority）。
        CCO 定位：中级（5-8 年），排除过度 senior 的岗位。
        """
        t = title.lower()
        # 极高年资关键词（直接 P3 或额外 -20）
        if any(k in t for k in ['svp', 'senior vice president', 'managing director', 'executive director']):
            return {'penalty': 20, 'reason': 'title暗示要求10年以上高层管理经验'}
        if any(k in t for k in ['vp ', ' vice president', 'avp', 'assistant vice president', 'director']):
            return {'penalty': 10, 'reason': 'title暗示要求8-10年中高层管理经验'}
        if any(k in t for k in ['senior manager', 'principal', 'head of']):
            return {'penalty': 5, 'reason': 'title暗示要求高级经验'}
        return {'penalty': 0, 'reason': ''}
    
    def _calculate_bonus(self, text):
        """计算加分项"""
        total_bonus = 0
        reasons = []
        bonus_keywords = self.keywords['bonus_keywords']
        
        for category in ['genai', 'fintech', 'hongkong']:
            config = bonus_keywords[category]
            for kw in config['keywords']:
                if kw.lower() in text:
                    total_bonus += config['bonus']
                    reasons.append(config['reason'])
                    break  # 每个类别只加一次
        
        return {
            'bonus': total_bonus,
            'reason': '、'.join(reasons) if reasons else '无加分'
        }
    
    def _calculate_fit_bonus(self, text):
        """计算适合度加分"""
        match_count = 0
        indicators = self.keywords['good_fit_indicators']
        
        for kw in indicators['keywords']:
            if kw.lower() in text:
                match_count += 1
        
        # 每匹配一个关键词加1分，最多加5分
        bonus = min(match_count, 5)
        
        return {
            'bonus': bonus,
            'reason': f'匹配{match_count}个核心能力关键词' if bonus > 0 else '标准匹配'
        }
    
    def _get_priority(self, score, tech_penalty, exclusion_penalty, title_penalty=0):
        """确定优先级"""
        # 如果有严重排除项，直接P3
        if exclusion_penalty >= 35:
            return 'P3'
        
        # 如果技术惩罚或Title年资惩罚过高，降级
        if tech_penalty >= 30:
            return 'P3' if score < 80 else 'P2'
        if title_penalty >= 20:
            return 'P3' if score < 85 else 'P2'
        
        if score >= 90:
            return 'P0'
        if score >= 75:
            return 'P1'
        if score >= 60:
            return 'P2'
        return 'P3'
    
    def _generate_comment(self, score, priority, details):
        """生成评语"""
        if priority == 'P0':
            return '这个岗位适合我'
        
        if priority == 'P1':
            return '该岗位比较合适，值得投递'
        
        # 找出主要问题
        negative_factors = [d for d in details if d['score'] < 0]
        if negative_factors:
            main_issue = negative_factors[0]
            return f"一般合适，原因：{main_issue['reason']}"
        
        return '匹配度一般'
    
    def _get_main_reason(self, details):
        """获取主要原因"""
        negative = [d for d in details if d['score'] < 0]
        if negative:
            return negative[0]['reason']
        return '适合'
    
    def _extract_experience_years(self, text):
        """从文本中提取经验年限"""
        patterns = [
            r'(\d+)\+?\s*years?\s*(?:of\s*)?experience',
            r'(\d+)\+?\s*yrs?\s*(?:of\s*)?exp',
            r'minimum\s*(\d+)\s*years?',
            r'at\s*least\s*(\d+)\s*years?'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                return int(match.group(1))
        return None


# 便捷函数（兼容简单调用）
def score_job(job):
    """
    便捷评分函数
    
    Args:
        job: dict with job data, or can pass individual fields:
             score_job({'title': '...', 'description': '...'})
    
    Returns:
        dict: 评分结果（包含原始job数据 + 评分字段）
    """
    scorer = CCOSCORER()
    result = scorer.calculate_score(job)
    
    # Build match_reason
    if result['isRecommended']:
        match_reason = f"{result['priority']} - {result['comment']}"
    else:
        # For non-recommended jobs, explain why
        negative_factors = [d for d in result['details'] if d['score'] < 0]
        if negative_factors:
            match_reason = f"{result['priority']} - " + ", ".join([d['reason'] for d in negative_factors[:2]])
        else:
            match_reason = f"{result['priority']} - 分数未达P1阈值"
    
    # 合并原始job数据和评分结果
    output = job.copy()
    output.update({
        'score': result['score'],
        'priority': result['priority'],
        'comment': result['comment'],
        'isRecommended': result['isRecommended'],
        'reason': result['reason'],
        'match_reason': match_reason,
        'scoringDetails': result['details']
    })
    
    return output


def get_priority(score):
    """根据分数获取优先级"""
    if score >= 90:
        return 'P0'
    if score >= 75:
        return 'P1'
    if score >= 60:
        return 'P2'
    return 'P3'


# 测试代码
if __name__ == '__main__':
    print('=== CCO Scorer Test (Python v2) ===\n')
    
    test_jobs = [
        {
            'title': 'AI Business Analyst',
            'description': 'Translate business requirements into AI solutions. Work with stakeholders to identify opportunities.',
            'company': 'Tech Corp'
        },
        {
            'title': 'Data Scientist',
            'description': 'Strong proficiency in Python, TensorFlow. Develop and deploy ML models.',
            'company': 'Bank'
        },
        {
            'title': 'AI Product Manager',
            'description': 'Hands-on coding experience in Python required. Build AI products.',
            'company': 'Startup'
        }
    ]
    
    for job in test_jobs:
        result = score_job(job)
        print(f"职位: {job['title']}")
        print(f"匹配度: {result['score']} | 优先级: {result['priority']}")
        print(f"评语: {result['comment']}")
        print(f"推荐: {'是' if result['isRecommended'] else '否'}")
        print('---')
