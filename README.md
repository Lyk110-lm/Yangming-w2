# 阳明心学咨询 W2 · 本地启动指南

> 单文件 H5 + 本地 API,3 分钟跑起来,手机能访问

---

## 1. 文件清单

确保工作目录有以下文件(同目录):

```
.
├── index.html              # 5 屏 H5(13KB)
├── api_consult.py          # W1 v0.4 API(7.4KB)
├── oral_to_concept.json    # 口语桥 770 词(46KB)
├── entries.db              # 弹药库 SQLite(传习录+心学 770 段)
└── README.md               # 本文件
```

## 2. 启动步骤(2 个窗口)

### 窗口 1 — 启 API

```bash
cd <工作目录>
python3 -u api_consult.py --port 5001
```

看到 `Uvicorn running on http://127.0.0.1:5001` 就 OK。

测一下:浏览器打开 `http://127.0.0.1:5001/health` 应该看到 JSON:
```json
{"status":"ok","version":"0.4.0","concepts_count":7,"oral_map_count":770,...}
```

### 窗口 2 — 启 H5

```bash
cd <工作目录>
python3 -m http.server 8080
```

看到 `Serving HTTP on 0.0.0.0 port 8080` 就 OK。

## 3. 电脑访问

浏览器打开:
```
http://127.0.0.1:8080/index.html
```

## 4. 手机访问(同 WiFi)

1. 电脑查 IP(Mac 终端:`ifconfig | grep "inet " | grep -v 127.0.0.1`;Win 终端:`ipconfig`)
2. 找到 `192.168.x.x` 这种局域网 IP
3. 手机浏览器打开:`http://192.168.x.x:8080/index.html`

注意:手机和电脑必须连同一个 WiFi。

## 5. 5 屏功能

| 屏 | 功能 |
|---|------|
| 1 | 输入框 + 4 个快捷问句 + localStorage 历史 |
| 2 | 转圈 2 秒(轮播翻书/找话/挑段/排列文案) |
| 3 | 3 段答案:病根 / 阳明说 / 落地招 |
| 4 | Canvas 画米白手绘卡片(可下载 PNG) |
| 5 | 4 选 1 追问反馈 |

## 6. 故障排查

| 问题 | 解决 |
|------|------|
| API 调不到 | 检查 5001 窗口是否还在;`curl http://127.0.0.1:5001/health` 测 |
| H5 白屏 | 浏览器 F12 看 Console;检查 Tailwind CDN 是否能连外网 |
| 手机访问 404 | 检查防火墙(Mac:`系统设置 → 网络 → 防火墙` 关闭) |
| 跨网访问 | 改用 Vercel/Netlify 部署公网(需要账号) |

## 7. 公网部署(W3 后续)

需要主人注册:
- **Vercel** https://vercel.com(推荐,免费,GitHub 登录)
- **Netlify** https://netlify.com(免费)

或者用 Cloudflare Tunnel(免账号但需装客户端):
- 装 `cloudflared` 二进制
- 跑 `cloudflared tunnel --url http://127.0.0.1:8080` 拿临时域名

## 8. 已知限制

- H5 的病根/落地招目前是写死 7 条模板,**未来 W3 接入 LLM 生成**(更准)
- 弹药库 7 概念加权召回 v0.4,top_k=5 覆盖 5-6 概念
- 修哥味硬规则已内化(反差金句/短句/对话感/钩子/红色高亮)




