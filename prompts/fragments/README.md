# Prompt 题材片段（按需注入）

此目录用于按题材（genre）按需注入 Agent system prompt 的专项片段，避免 `writer_system.txt` / `style_advisor_system.txt` 等基础 prompt 体积膨胀。

## 命名规则

```
prompts/fragments/<agent_name>/<genre_keyword>.txt
```

- `<agent_name>`：与 `BaseAgent._agent_name()` 返回值一致（如 `writer`, `style_advisor`, `plotter`）
- `<genre_keyword>`：题材关键词。BaseAgent 用子串匹配（`stem in genre`）找到对应文件，因此可命名为 `悬疑`、`奇幻`、`古风` 等。

## 加载时机

`BaseAgent.apply_style()` 调用时，若 `style_guide.setting.genre` 包含某个 fragment 的 stem，则把该文件内容追加到 system prompt 末尾，section 标题为 `## 题材专项指引（<stem>）`。

## 不存在时的行为

目录为空 → 不注入 → behavior 与改造前完全一致。

## 后续 prompt 瘦身路径

未来若要把 `writer_system.txt` 中的"分题材扩充策略（D2）"等段落剥离，把对应段落迁到 `writer/悬疑.txt`、`writer/言情.txt` 等，然后从主 prompt 删除即可。
