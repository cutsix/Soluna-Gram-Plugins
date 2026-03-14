# cosplay

随机获取 `cosplaytele.com` 的套图图片。

## 命令

```text
,cosplay [数量]
,cos [数量]
```

## 说明

- 默认发送 1 张，最大支持 10 张。
- 每次会随机命中一个套图，并从中抽取指定数量的图片。
- 发送时默认启用防剧透。
- 依赖 `beautifulsoup4` 和 `pillow`，插件会自行处理 Python 依赖安装。
