#!/usr/bin/env python3
"""
China Meme Dictionary — Automatic Scraper & Translator

Fetches trending Chinese terms from multiple hot-search APIs,
generates multi-language explanations, and merges with existing data.
If scraping yields few results, falls back to a curated archive of
historical Chinese internet memes with original popularity dates.
"""

import json
import os
import re
import sys
import time
import hashlib
import base64
from datetime import datetime, timezone, timedelta
from urllib.parse import quote, urlencode

try:
    import requests
except ImportError:
    print("ERROR: requests library not found. Run: pip install requests")
    sys.exit(1)

# ── Paths ──────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
DATA_FILE = os.path.join(REPO_ROOT, 'data', 'memes.json')

# ── User-Agent rotation ────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

def get_headers():
    return {
        "User-Agent": USER_AGENTS[int(time.time()) % len(USER_AGENTS)],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://weibo.com/",
    }

# ── Source API endpoints ───────────────────────────────────
# Using free public hot-list aggregator APIs (no API key needed)
SOURCES = [
    {
        "name": "weibo",
        "url": "https://api-hot.imsyy.top/hot/weibo",
        "parser": "imsyy_generic",
    },
    {
        "name": "baidu",
        "url": "https://api-hot.imsyy.top/hot/baidu",
        "parser": "imsyy_generic",
    },
    {
        "name": "zhihu",
        "url": "https://api-hot.imsyy.top/hot/zhihu",
        "parser": "imsyy_generic",
    },
]

# ── Heuristics: filter out pure news headlines ─────────────
# If a term matches these patterns, it's probably news, not a meme
NEWS_KEYWORDS = [
    "死亡", "事故", "车祸", "地震", "台风", "洪水", "暴雨",
    "遇难", "受伤", "逮捕", "拘留", "审判", "判决", "起诉",
    "爆炸", "火灾", "塌方", "坠楼", "枪击", "刺杀",
    "新冠", "确诊", "新增", "阳性", "疫苗", "核酸",
    "总统", "首相", "外长", "外交部", "发言人",
    "声明", "抗议", "制裁", "战争", "冲突", "袭击",
    "财报", "涨跌", "股市", "期货", "黄金", "利率",
    "GDP", "CPI", "通胀",
]

def is_likely_meme(word):
    """Return True if the term looks like a meme/slang rather than a news event."""
    # Longer text is more likely to be a news headline
    if len(word) > 20:
        return False
    # Very short text (2-3 chars) could be meme shorthand
    # Check for news keywords
    for kw in NEWS_KEYWORDS:
        if kw in word:
            return False
    # Meme/slang often contains certain patterns
    meme_patterns = [
        r'了$',         # ends with 了 (破防了, emo了)
        r'子$',         # ends with 子 (绝绝子)
        r'人$',         # ends with 人 (社恐→社恐人)
        r'[A-Za-z]+$',  # contains English letters (YYDS, emo, 栓Q)
        r'的[^的]+$',   # 的xx pattern
    ]
    for pat in meme_patterns:
        if re.search(pat, word):
            return True
    # Fuzzy: short, vivid phrasing is meme-like
    if len(word) <= 8 and not any(kw in word for kw in ["中国", "美国", "日本", "俄罗斯", "报道", "发布", "宣布"]):
        return True
    return False

# ── Pinyin generation (simple fallback) ────────────────────
# NOTE: For proper pinyin, we'd use pypinyin; here we use a basic lookup.
# The github workflow can optionally install pypinyin for better results.
SIMPLE_PINYIN = {}

def simple_pinyin(text):
    """Generate basic pinyin using rules. Returns lowercase."""
    # Known pinyins for common slang characters
    known = {
        '内': 'nei', '卷': 'juan', '躺': 'tang', '平': 'ping',
        '芭': 'ba', '比': 'bi', 'Q': 'Q', '了': 'le',
        '社': 'she', '恐': 'kong', '绝': 'jue', '子': 'zi',
        '永': 'yong', '远': 'yuan', '的': 'de', '神': 'shen',
        '破': 'po', '防': 'fang', '凡': 'fan', '尔': 'er', '赛': 'sai',
        'e': 'yī', 'm': 'mó', 'o': 'ōu',
        '栓': 'shuan',
        '无': 'wu', '语': 'yu',
        '显': 'xian', '眼': 'yan', '包': 'bao',
        '遥': 'yao', '领': 'ling', '先': 'xian',
        '小': 'xiao', '土': 'tu', '豆': 'dou',
        '泼': 'po', '天': 'tian', '富': 'fu', '贵': 'gui',
        '太': 'tai', '酷': 'ku', '辣': 'la',
        '脆': 'cui', '皮': 'pi', '大': 'da', '学': 'xue', '生': 'sheng',
        '情': 'qing', '绪': 'xu', '价': 'jia', '值': 'zhi',
        '科': 'ke', '目': 'mu', '三': 'san',
    }
    result = []
    for ch in text:
        if ch in known:
            result.append(known[ch])
        elif re.match(r'[a-zA-Z]', ch):
            result.append(ch.lower())
        else:
            result.append(ch)
    return ' '.join(result)

# ── GitHub config ───────────────────────────────────────────
GITHUB_OWNER = 'lfiona244-beep'
GITHUB_REPO = 'china-meme-dictionary'
# Token is read from GITHUB_TOKEN env var (set in workflow)

def get_github_token():
    token = os.environ.get('GITHUB_TOKEN_MEME', '') or os.environ.get('GITHUB_TOKEN', '')
    if not token:
        print("  [WARN] No GITHUB_TOKEN found, issue processing disabled.")
    return token

def fetch_suggestion_issues():
    """Fetch open issues labeled 'meme-suggestion' from the repo."""
    token = get_github_token()
    if not token:
        return []
    try:
        url = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues'
        params = {'labels': 'meme-suggestion', 'state': 'open', 'per_page': 20}
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'china-meme-dict/1.0',
        }
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            issues = resp.json()
            print(f"  Found {len(issues)} open suggestion issues.")
            return issues
        else:
            print(f"  [WARN] GitHub API returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  [WARN] Failed to fetch issues: {e}")
    return []

def extract_term_from_issue(issue):
    """Extract the suggested Chinese term from an issue title or body."""
    title = issue.get('title', '')
    body = issue.get('body', '')
    # Title pattern: "Suggest: XXX"
    m = re.search(r'Suggest:\s*(.+)', title)
    if m:
        return m.group(1).strip()
    # Body pattern: "**Term:** XXX"
    m = re.search(r'\*\*Term:\*\*\s*(.+)', body)
    if m:
        return m.group(1).strip()
    return None

def close_issue(issue_number):
    """Close a GitHub issue and add comment."""
    token = get_github_token()
    if not token:
        return False
    try:
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'china-meme-dict/1.0',
        }
        # Add closing comment
        comment_url = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues/{issue_number}/comments'
        comment_data = {
            'body': '✅ This meme has been added to the dictionary! Thanks for the suggestion.'
        }
        requests.post(comment_url, json=comment_data, headers=headers, timeout=10)

        # Close the issue
        close_url = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues/{issue_number}'
        close_data = {'state': 'closed', 'labels': ['meme-suggestion', 'added']}
        resp = requests.patch(close_url, json=close_data, headers=headers, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"  [WARN] Failed to close issue #{issue_number}: {e}")
        return False

# ── Translation engine ─────────────────────────────────────
# Built-in explanation templates for common patterns
EXPLANATION_TEMPLATES = {
    "en": (
        "Trending term on Chinese social media. {context} "
        "Often used in memes and casual online conversations among Chinese netizens."
    ),
    "ja": (
        "中国のSNSで流行中の用語。{context} "
        "中国のネットユーザーの間でミームやカジュアルな会話でよく使われます。"
    ),
    "ko": (
        "중국 SNS에서 유행하는 용어입니다. {context} "
        "중국 네티즌들 사이에서 밈과 일상 대화에 자주 사용됩니다."
    ),
    "fr": (
        "Terme tendance sur les réseaux sociaux chinois. {context} "
        "Souvent utilisé dans les mèmes et les conversations en ligne informelles."
    ),
    "zh": (
        "中文网络流行语。{zh_context}"
    ),
}

# Specific generated context per term (fallback)
# ── Historical Meme Archive (curated, with original popularity dates) ──
# Used as fallback when live scraping returns fewer than 5 meme-like terms.
# Each entry: (chinese, pinyin, en_explanation, ja_explanation, ko_explanation, fr_explanation, zh_explanation, period_label, source)
# period_label e.g. "2020-03" (year-month the meme peaked)
HISTORICAL_MEMES = [
    # ── 2020 ──
    ("有内味了", "yǒu nèi wèi le",
     "'That's the vibe' — Used when something has that authentic, characteristic feel. Originated from gaming/ACG culture.",
     "「それっぽい」 — 本物らしい雰囲気を持つときに使う。ゲーム・ACG文化から。",
     "'그 맛이야' — 진짜 그 느낌이 난다는 뜻. 게임/ACG 문화에서 유래.",
     "'Ça a cette vibe' — Utilisé pour dire que quelque chose a ce feeling authentique. Issu de la culture gaming.",
     "有内味了意思是『有那种感觉了』『到位了』。内味是『那一味』的北方方言连读。出自电竞直播，当选手打出精彩操作时观众就会刷『有内味了』。后来推广到各种『对味』的场景。",
     "2020-03", "weibo"),
    ("我太难了", "wǒ tài nán le",
     "'I'm too difficult/My life is so hard' — A popular lament expressing frustration with life's struggles. Often used humorously.",
     "「俺、難しすぎる」 — 人生の苦労を嘆く表現。よく冗談交じりに使われる。",
     "'나 너무 힘들어' — 인생의 고난에 대한 불평을 표현. 주로 유머러스하게 사용.",
     "'C'est trop dur' — Exprime la frustration face aux difficultés de la vie. Souvent utilisé avec humour.",
     "我太难了是2019年前后走红的网络用语，表达对生活压力的吐槽和无奈。常配合夸张的表情包使用，既有真实发泄也有自嘲调侃的成分。",
     "2020-04", "weibo"),
    ("黑人抬棺", "hēi rén tái guān",
     "'Black Men Carrying Coffins' — A viral meme featuring Ghanaian pallbearers dancing with a coffin. Used to signify 'game over' or epic failure.",
     "「黒人葬儀ダンス」 — ガーナの葬儀屋が棺桶を担いで踊る動画。大失敗・終了のミーム。",
     "'흑인 관 운반' — 가나의 장의사들이 관을 메고 춤추는 바이럴 영상. '게임 오버'를 상징.",
     "'Porteurs de cercueil noirs' — Méme viral de porteurs ghanéens dansant avec un cercueil. Signifie 'game over'.",
     "黑人抬棺源自一段加纳殡葬团队的视频：他们抬着棺材跳着欢快的舞蹈送葬。网友将其用于配合『计划失败』『游戏结束』等场景，成为全球性的网络迷因。",
     "2020-04", "weibo"),
    ("一起爬山吗", "yì qǐ pá shān ma",
     "'Wanna go hiking?' — A sinister meme from the drama 'The Bad Kids'. Said by a murderer to his victims. Became a dark humor meme.",
     "「一緒に山登りしない？」 — ドラマ『隠秘的角落』から。殺人鬼の台詞で、ダークジョークとして。",
     "'같이 등산할래?' — 드라마 '은밀한 각도'에서 유래. 살인자의 대사로 암흑 유머로 사용.",
     "'On va faire de la randonnée ?' — Méme noir du drama 'The Bad Kids'. Phrase d'un meurtrier devenue virale.",
     "一起爬山吗出自2020年的悬疑剧《隐秘的角落》。剧中张东升带岳父母爬山时将他们推下山崖，这句话因此成为暗含杀机的经典台词。网上用来开玩笑地威胁或调侃。",
     "2020-06", "baidu"),
    ("爷青回", "yé qīng huí",
     "'My Youth Has Returned' — Abbreviation of 爷的青春回来了. Used when something nostalgic comes back, triggering childhood memories.",
     "「俺の青春が戻ってきた」 — 懐かしいものが復活した時の感動を表す略語。",
     "'내 청춘이 돌아왔다' — 향수를 불러일으키는 무언가가 돌아왔을 때의 감동을 표현.",
     "'Ma jeunesse est de retour' — Abréviation utilisée quand quelque chose de nostalgique fait son retour.",
     "爷青回是『爷的青春回来了』的缩写。当看到童年回忆中的动漫、游戏、影视剧重新出现时，网友就会刷『爷青回』来表达激动和怀旧之情。",
     "2020-09", "weibo"),
    ("打工人", "dǎ gōng rén",
     "'Wage Worker' — A self-deprecating term for office workers/employees who are tired of the grind. Became a rallying cry for the working class.",
     "「労働者」 — サラリーマンや労働者が自己卑下する言葉。労働者階級の合言葉に。",
     "'월급쟁이' — 직장인의 자조적 표현. 노동자 계급의 구호가 됨.",
     "'Travailleur salarié' — Terme d'autodérision pour les employés, cri de ralliement de la classe ouvrière.",
     "打工人是上班族的自嘲式自称，强调自己是『打工』的普通人。这个词在2020年秋天引爆网络，表达了年轻人对工作压力的吐槽，也带有一丝彼此鼓励的温暖。",
     "2020-10", "weibo"),

    # ── 2021 ──
    ("蚌埠住了", "bèng bù zhù le",
     "'Can't Hold It' — A pun on '崩不住了' (can't hold it together), using the city name Bengbu. Means 'I can't stop laughing / I'm losing it'.",
     "「笑いが止まらない」 — 「崩不住了（我慢できない）」の駄洒落。笑いが止まらない時の表現。",
     "'참을 수 없어' — '崩不住了(참을 수 없다)'의 말장난. 웃음을 참을 수 없을 때 사용.",
     "'J'en peux plus' — Jeu de mots sur l'expression 'je craque'. Montre qu'on n'en peut plus de rire.",
     "蚌埠住了是『崩不住了』的谐音双关，借用了安徽城市蚌埠的名字。意指忍不住笑了、绷不住了。在网络评论区高频使用，常配合搞笑段子出现。",
     "2021-01", "weibo"),
    ("小丑竟是我自己", "xiǎo chǒu jìng shì wǒ zì jǐ",
     "'The Joker Is Me' — A self-mocking phrase used when you realize you've been the fool in a situation. Based on the Joker character.",
     "「ピエロは私だった」 — 自分が笑い者だったと気づいた時の自嘲的な言葉。ジョーカーから。",
     "'광대는 바로 나' — 자신이 바보였다는 걸 깨달았을 때의 자조적 표현. 조커 캐릭터에서 유래.",
     "'Le clown, c'est moi' — Phrase d'autodérision quand on réalise qu'on a été le dindon de la farce.",
     "小丑竟是我自己出自蝙蝠侠系列中的角色小丑。当一个人意识到自己在一段关系或事件中是被耍的那个——不是笑看别人的小丑，而是小丑本人——就会用这句话来自嘲。",
     "2021-03", "weibo"),
]

# ── Historical meme lookup ─────────────────────────────────
HISTORICAL_MAP = {}
for h in HISTORICAL_MEMES:
    HISTORICAL_MAP[h[0]] = h


def build_context(text):
    """Build a differentiated English context sentence for any term."""
    if re.search(r'[A-Za-z]', text) and not re.search(r'[\u4e00-\u9fff]', text):
        return "It contains English letters and is often used as internet shorthand."
    if text.endswith('了'):
        stem = text[:-1]
        return f'Literally "{stem} happened", expressing a change of state or emotional reaction.'
    if text.endswith('子'):
        return 'The suffix "子" adds a cute or exaggerated tone typical of youth slang.'
    if text.endswith('人'):
        return f'Literally "{text} person", used to categorize a type of person in internet culture.'
    if len(text) <= 3:
        return 'A concise slang term expressing a complex modern emotion or social phenomenon.'
    if len(text) <= 6:
        return 'A vivid expression that captures a specific mood or situation in modern Chinese life.'
    return 'An emerging internet expression reflecting contemporary Chinese youth culture.'

def build_zh_context(text):
    """Build a Chinese-language explanation for any term."""
    if re.search(r'[A-Za-z]', text) and not re.search(r'[\u4e00-\u9fff]', text):
        return f'「{text}」是中文互联网上常用的字母缩写或外来语。具体含义取决于具体语境，常用于网络社交平台。'
    if text.endswith('了'):
        stem = text[:-1]
        return f'「{text}」表示一种状态的变化或情绪反应。其中「{stem}」是核心语义，「了」表示已经发生。是网络流行语中常见的表达方式。'
    if text.endswith('子'):
        return f'「{text}」是网络流行语，后缀「子」带有可爱或夸张的语气，是年轻人网络语言的特征之一。'
    if len(text) <= 4:
        return f'「{text}」是中文网络流行语，简洁地表达了一种现代情感或社会现象，在社交媒体上广泛使用。'
    return f'「{text}」是中文网络上流行的表达方式，反映了当代年轻人的生活态度和文化趣味。具体含义请结合使用场景理解。'

def generate_explanations(text):
    """Generate multi-language explanations for a trending term."""
    ctx = build_context(text)
    zh_ctx = build_zh_context(text)
    exp = {}
    for lang, template in EXPLANATION_TEMPLATES.items():
        if lang == 'zh':
            exp[lang] = template.format(zh_context=zh_ctx)
        else:
            exp[lang] = template.format(context=ctx)
    return exp

# ── Try MyMemory API for better translations ───────────────
def try_mymemory_translate(text, source_lang='zh-CN', target_lang='en'):
    """Attempt to translate via MyMemory API free tier. Returns None on failure."""
    try:
        url = "https://api.mymemory.translated.net/get"
        params = {
            'q': text,
            'langpair': f'{source_lang}|{target_lang}',
            'de': 'china-meme-dict@github',
        }
        resp = requests.get(url, params=params, timeout=8,
                            headers={'User-Agent': USER_AGENTS[0]})
        if resp.status_code == 200:
            data = resp.json()
            if data.get('responseStatus') == 200:
                translated = data.get('responseData', {}).get('translatedText', '')
                if translated and translated != text and translated.lower() != 'no match':
                    return translated
    except Exception as e:
        pass  # Fall through to built-in
    return None

def enhance_with_translation(text, explanations):
    """Try to improve explanations using free translation APIs."""
    # Try English translation via MyMemory
    en_trans = try_mymemory_translate(text, 'zh-CN', 'en')
    if en_trans and en_trans != text:
        # Replace generic explanation with the actual translation + context
        explanations['en'] = (
            f'"{en_trans}" — Literal translation of this trending Chinese term. '
            f'Originally from Chinese social media, it has become a widely used internet meme.'
        )
    # Try other languages (via English as pivot or direct)
    for lang in ['ja', 'ko', 'fr']:
        target_map = {'ja': 'ja', 'ko': 'ko', 'fr': 'fr'}
        # Try direct translation
        trans = try_mymemory_translate(text, 'zh-CN', target_map[lang])
        if trans and trans != text and 'NO MATCH' not in trans.upper():
            explanations[lang] = (
                f'"{trans}" — 中国のSNSで使われる流行語。'
                if lang == 'ja' else
                f'"{trans}" — 중국 SNS에서 사용되는 유행어.'
                if lang == 'ko' else
                f'"{trans}" — Terme tendance sur les réseaux sociaux chinois.'
            )

# ── API parsers ────────────────────────────────────────────
def parse_imsyy_generic(data, source_name):
    """Parse the free hot-list API response format."""
    results = []
    try:
        items = data.get('data', [])
        for item in items[:15]:  # Take top 15 from each source
            title = item.get('title', '') or item.get('word', '') or ''
            title = re.sub(r'#[^#]+#', '', title).strip()  # Remove hashtags
            title = re.sub(r'\[.*?\]', '', title).strip()
            if not title:
                continue
            hot = item.get('hot', 0) or item.get('count', 0) or 0
            results.append({'title': title, 'hot': hot})
    except Exception as e:
        print(f"  [WARN] Parse error for {source_name}: {e}")
    return results

def fetch_source(source):
    """Fetch one hot-list source and return extracted terms."""
    name = source['name']
    url = source['url']
    print(f"  Fetching {name}...")

    try:
        resp = requests.get(url, headers=get_headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if source['parser'] == 'imsyy_generic':
            return parse_imsyy_generic(data, name)
        else:
            print(f"  [WARN] Unknown parser: {source['parser']}")
            return []
    except requests.exceptions.Timeout:
        print(f"  [WARN] {name} timed out.")
    except requests.exceptions.RequestException as e:
        print(f"  [WARN] {name} request failed: {e}")
    except json.JSONDecodeError:
        print(f"  [WARN] {name} returned invalid JSON.")
    except Exception as e:
        print(f"  [WARN] {name} error: {e}")
    return []

# ── Category classifier ────────────────────────────────────
CATEGORY_KEYWORDS = {
    '句式梗': ['了', '吗', '呢', '吧', '啊', '吗', '我', '你', '他', '什么', '怎么', '不', '是', '的', '就', '有', '没', 'Q', '吗'],
    '社交情绪': ['恐', '感', '情', '心', '爱', '恨', '伤', '哭', '笑', '怒', '怕', '烦', '累', '社', 'emo', '破防', '凡尔赛', '小土豆'],
    '职场生活': ['工', '班', '卷', '躺', '薪', '资', '钱', '富', '贵', '穷', '买', '房', '内卷', '躺平', '打工人', '泼天富贵'],
    '圈层文化': ['领', '先', '神', '绝', '黑', '抬', '棺', '遥遥领先', '黑人', '梗', '圈', '粉', '谷子', '痛文化', 'AI', '人格', '抽象'],
    '常青词': ['YYDS', '666', '无语', 'XSWL', 'U1S1', 'NSDD', 'AWSL', '摸鱼', '社死', '拿捏', '好家伙', '稳了', '安排'],
    '复古词': ['爷', '青', '回', '886', '踩', '冒', '泡', '路', '过', '沙发', '顶', '火钳', '刘明', 'QQ', '空间', '留言板'],
}

def guess_category(text):
    """Guess meme category based on keyword matching."""
    scores = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in text)
        if score > 0:
            scores[cat] = score
    if scores:
        return max(scores, key=scores.get)
    # Default fallback
    if re.search(r'[A-Za-z]', text) and not re.search(r'[\u4e00-\u9fff]', text):
        return '常青词'
    if text.endswith('了') or text.endswith('吗') or text.endswith('吧'):
        return '句式梗'
    if len(text) <= 4:
        return '社交情绪'
    return '圈层文化'

# ── Main logic ─────────────────────────────────────────────
def load_existing_data():
    """Load existing memes.json. Return (classics, trending, all_ids, existing_map)."""
    classics = []
    trending = []
    existing_map = {}  # chinese → meme object

    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for meme in data:
                existing_map[meme['chinese']] = meme
                if meme.get('is_trending'):
                    trending.append(meme)
                else:
                    classics.append(meme)
            print(f"  Loaded existing data: {len(classics)} classics, {len(trending)} trending")
        except Exception as e:
            print(f"  [WARN] Failed to load existing data: {e}")
    else:
        print(f"  No existing data file found at {DATA_FILE}")

    return classics, trending, existing_map

def deduplicate_terms(terms, existing_map):
    """Remove terms that already exist in the database and filter out non-memes."""
    unique = []
    seen = set()
    for term in terms:
        chinese = term['chinese']
        if chinese in seen:
            continue
        seen.add(chinese)
        # Skip if already a classic meme
        if chinese in existing_map and not existing_map[chinese].get('is_trending'):
            print(f"  Skipping (already classic): {chinese}")
            continue
        # Filter news-like terms
        if not is_likely_meme(chinese):
            print(f"  Filtered out (news-like): {chinese}")
            continue
        unique.append(term)
    return unique

def assign_ids(new_terms, existing_ids):
    """Assign unique IDs to new terms."""
    max_id = max(existing_ids) if existing_ids else 0
    for term in new_terms:
        max_id += 1
        term['id'] = max_id
    return new_terms

def build_new_meme(chinese, source, date_str):
    """Build a complete meme object with auto-generated translations."""
    pinyin = simple_pinyin(chinese)
    exps = generate_explanations(chinese)
    # Try to enhance with real translations
    enhance_with_translation(chinese, exps)

    return {
        'chinese': chinese,
        'pinyin': pinyin,
        'category': guess_category(chinese),
        'usage': '安全',
        'explanations': exps,
        'source': source or 'web',
        'date': date_str,
        'is_trending': True,
    }

def main():
    print("=" * 50)
    print("词话 Zhargon — Scraper v2.0")
    print(f"Date: {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    # 1. Load existing data
    classics, old_trending, existing_map = load_existing_data()
    all_existing = classics + old_trending
    existing_ids = set(m.get('id', 0) for m in all_existing if m.get('id'))
    today = datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d')

    # 2. Process user-submitted suggestions from GitHub Issues
    open_issues = fetch_suggestion_issues()
    user_suggested = []
    for issue in open_issues:
        term = extract_term_from_issue(issue)
        if not term:
            continue
        issue_num = issue['number']
        print(f"  Issue #{issue_num}: Suggest '{term}'")
        if term in existing_map:
            print(f"    Already in DB, closing issue #{issue_num}")
            close_issue(issue_num)
            continue
        if term in HISTORICAL_MAP:
            print(f"    In history archive. Closing #{issue_num}")
            close_issue(issue_num)
            continue
        user_suggested.append({'term': term, 'issue_number': issue_num})

    # 3. Scrape all sources for current trending
    all_raw = []
    for src in SOURCES:
        terms = fetch_source(src)
        print(f"    Got {len(terms)} terms from {src['name']}")
        all_raw.extend(terms)
        time.sleep(1.5)

    # 4. Extract unique chinese terms, sorted by popularity
    seen_titles = set()
    deduped_raw = []
    for t in all_raw:
        title = t['title'].strip()
        if title and title not in seen_titles:
            seen_titles.add(title)
            deduped_raw.append(t)

    # 5. Filter and deduplicate
    candidate_terms = [{'chinese': t['title'], 'hot': t['hot']} for t in deduped_raw]
    filtered = deduplicate_terms(candidate_terms, existing_map)

    # 6. Take top from live scrape
    live_trending = filtered[:10]

    # 7. Build new trending list
    TARGET_COUNT = 8
    new_trending = []

    # 7a. Add user-suggested terms first
    for item in user_suggested:
        meme = build_new_meme(item['term'], 'user-suggestion', today)
        new_trending.append(meme)
        existing_map[meme['chinese']] = meme
        print(f"  User suggestion: {item['term']}")
        close_issue(item['issue_number'])

    # 7b. Add live-scraped terms
    for ft in live_trending:
        if len(new_trending) >= TARGET_COUNT:
            break
        if ft['chinese'] in existing_map and existing_map[ft['chinese']].get('is_trending'):
            existing = existing_map[ft['chinese']]
            existing['date'] = today
            new_trending.append(existing)
            print(f"  Updated trending: {ft['chinese']}")
        else:
            meme = build_new_meme(ft['chinese'], 'web', today)
            new_trending.append(meme)
            print(f"  New trending: {ft['chinese']}")

    # 7c. Preserve old trending if live scrape found nothing
    if len(new_trending) == 0 and old_trending:
        print(f"  No new trending found. Preserving {len(old_trending)} existing trending entries.")
        for m in old_trending:
            m['date'] = m.get('date', today)
            new_trending.append(m)

    # 7d. Supplement with historical archive
    if len(new_trending) < TARGET_COUNT:
        need = TARGET_COUNT - len(new_trending)
        print(f"  Supplementing with {need} from history archive...")
        for h in HISTORICAL_MEMES:
            if need <= 0:
                break
            chinese = h[0]
            if chinese in existing_map or any(m['chinese'] == chinese for m in new_trending):
                continue
            chinese, pinyin, en, ja, ko, fr, zh, period_label, source = h
            meme = {
                'chinese': chinese, 'pinyin': pinyin,
                'category': guess_category(chinese),
                'usage': '安全',
                'explanations': {'en': en, 'ja': ja, 'ko': ko, 'fr': fr, 'zh': zh},
                'source': source, 'date': period_label,
                'is_trending': True,
            }
            new_trending.append(meme)
            print(f"  + History ({period_label}): {chinese}")
            need -= 1

    # 8. Assign IDs to entries without one
    new_trending = assign_ids(new_trending, existing_ids)

    # 9. Ensure all classics have correct flags
    for c in classics:
        c['is_trending'] = False
        c.pop('_historical', None)
        # Ensure category and usage exist
        if 'category' not in c:
            c['category'] = guess_category(c['chinese'])
        if 'usage' not in c:
            c['usage'] = '安全'

    for nt in new_trending:
        nt.pop('_historical', None)

    # 10. Merge
    output = classics + new_trending
    output.sort(key=lambda x: x.get('id', 9999))

    # 11. Write
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 50}")
    print(f"Done! Written {len(output)} entries to {DATA_FILE}")
    print(f"  {len(classics)} classics + {len(new_trending)} trending")
    print(f"{'=' * 50}")

if __name__ == '__main__':
    main()
