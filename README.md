# 词话 Zhargon 🦞

**中文网络梗词典 · 解码中国互联网文化**

融合了三个项目的灵感：
- [china-meme-dictionary](https://github.com/WenKanghwdd/china-meme-dictionary) — 自动更新、多语翻译的基底
- [XinbaoWiki](https://github.com/XinbaoQiao/XinbaoWiki) — 2026热梗分类体系（句式梗/社交情绪/职场生活/圈层文化/常青词/复古词）+ 安全使用评估
- [zhargon.com](https://www.zhargon.com) — 每日一词、热门榜单、随机浏览的设计

## ✨ 特点

- **分类体系** — 六大类（句式梗/社交情绪/职场生活/圈层文化/常青词/复古词）
- **安全使用标签** — 安全/慎用/背景，知道什么场合用什么词
- **每日一词** — 每天随机展示一条，一键直达详情
- **随机翻牌** — 翻到哪条看哪条
- **多语言** — 中文/English/日本語/한국어/Français
- **自动更新** — GitHub Actions 每周自动爬取新梗
- **零成本** — 纯前端，GitHub Pages 免费部署

## 数据格式

每条梗词包含：
- `chinese` — 中文词
- `pinyin` — 拼音
- `category` — 分类（句式梗/社交情绪/职场生活/圈层文化/常青词/复古词）
- `usage` — 安全使用评估（安全/慎用/背景）
- `explanations` — 多语解释（zh/en/ja/ko/fr）
- `source` — 来源
- `date` — 时间
- `is_trending` — 是否热门

## 本地运行

```bash
python3 -m http.server 8000
# 打开 http://localhost:8000
```

## 许可

MIT