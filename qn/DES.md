# qn

把消息生成引用贴纸。

## 命令

```text
,qn [n]
,qnset [add/del/list] [自定义用户名]
```

## 说明

- 将回复的消息生成引用贴纸，支持多条合并。
- 支持自定义用户名管理。
- 依赖 `pillow`、`cairocffi`、`pangocairocffi`、`aiohttp`。
- 若系统缺少 Cairo/Pango 相关依赖，需先按环境补齐系统库。

