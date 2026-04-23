# speed_maomi

运行 Speedtest CLI 测速。

## 命令

```text
,sv
,sv list
,sv <server id>
,sv set <server id>
,sv set clear
```

## 说明

- 首次运行会自动下载 Speedtest CLI 到插件目录。
- 支持查看附近测速节点并指定节点测速。
- 支持设置默认测速节点，设置后直接执行 `,sv` 会优先使用该节点。
- 结果会附带测速图。
