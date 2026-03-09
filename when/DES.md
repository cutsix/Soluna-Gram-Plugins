# when

查询账号年龄、注册年月和共同群组。

## 命令

```text
,when [username/id]
```

## 说明

- 支持回复用户消息或直接输入用户名 / ID。
- 优先使用 Telegram 官方返回的注册月份信息。
- 若官方未返回注册月份，会基于 `user_id` 做本地线性插值估算兜底。
- 官方命中时会异步上报 `check_data:<user_id>:<YYYY-MM>` 到 `@solunagram_bot`。
