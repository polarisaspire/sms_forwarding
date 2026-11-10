# v1.1.7 本地修复（1.1.7-fix.6）

基于 v1.1.7（d4271d46f40bca215d2fba966b83051a1a4460be），包含以下修复。

## 推送签名和飞书回执

使用 ESP-IDF 6 的 PSA Crypto HMAC-SHA256，检查初始化、密钥导入、MAC 计算和 Base64 编码错误，释放临时密钥。签名失败时停止发送，避免发送全零摘要。该共享签名函数同时用于飞书和钉钉。

WiFi 飞书 HTTP 回执最多缓存 2048 字节，并检查 JSON code/StatusCode。HTTP 200 不再等同于业务成功；拒绝错误码会显示在测试结果中。蜂窝 HTTP 路径仍沿用原业务回执逻辑。

## 模组启动射频恢复

启动及软/硬复位后检查 CFUN，恢复完整功能。部分 ML307A 在即时确认 CFUN=1 后仍会异步回落到 0，因此首次注册成功前继续恢复；SIM 暂时报错时也可通过独立的后台入口重试。正常运行后不持续覆盖手动飞行模式，后台恢复保留 CFUN=4，并遵守 AT/eSIM 空闲限制。

PDP 配置前查询实时 CEREG，仅在 1/5 时下发。等待驻网不消耗 PDP 失败次数。后台恢复射频后重新安排数据模式配置。

## 验证

- ESP-IDF v6.0.2 和仓库管理的 SDK 补丁构建通过。
- test_modem_radio_startup.py、test_modem_uart.py、test_modem_refresh.py、test_sim_credentials.py、test_push_signing.py、test_push_response.py 通过；网页资源校验通过。
- 签名主机测试模拟 PSA 接口，验证参数和失败路径；实际摘要另经实机与标准 HMAC 比对。
- 回执测试使用 cJSON v1.7.19 源码，运行时设置 CJSON_SOURCE 为包含 cJSON.c/cJSON.h 的目录。
- 实机软件重启及模组硬重启自动驻网，CFUN=1、CEREG=1；配置保留。曾实测运营商长短信合并及飞书转发成功。

## 已知限制

模组接受 CGACT=0,1 后可能自行重新激活默认 CID1。不能据此保证蜂窝数据持续关闭。整机人工拔电重插尚未测试。蜂窝 HTTP 回执的业务码解析不在此次修复范围。
