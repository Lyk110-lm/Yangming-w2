# 阳明心学咨询 W2 · 33 分钟部署公网 + 开始收费

> Vercel(静态 H5) + Railway(后端 API) + 知识星球(支付)
> 主人 33 分钟跑通,本指南每步有截图位置描述

---

## 🎯 整体架构

```
[用户手机] 
    ↓ 访问
[Vercel 公网] → 静态 H5 (index.html)
    ↓ fetch
[Railway 公网] → Python API (api_consult.py) + 弹药库
    ↓ 调
[SQLite entries.db] (跟随 Railway 实例)
    ↓ 用户付费
[知识星球"阳明先生问心室"] → 微信支付(主人提现)
```

---

## 📋 主人准备清单

- [ ] GitHub 账号(主推 Vercel/Railway 都要)
- [ ] 微信 + 知识星球 APP
- [ ] 一个新邮箱(给 API 用的,免得收垃圾)

---

## 🚀 部署 8 步(33 分钟)

### 步骤 1:创建 GitHub 仓库(2 分钟)

1. 打开 https://github.com/new
2. 仓库名:`yangming-w2`
3. 选 **Public**(Vercel/Railway 免费层要 Public)
4. **不要**勾 Add README/.gitignore(空仓库)
5. 点 Create

---

### 步骤 2:推代码到 GitHub(3 分钟)

主人在自己电脑跑:

```bash
# 解压 w2_bundle_v2.zip(本目录提供)
unzip w2_bundle_v2.zip -d yangming-w2
cd yangming-w2

git init
git add .
git commit -m "w2 部署版 v1"
git branch -M main
git remote add origin https://github.com/<主人 GitHub 用户名>/yangming-w2.git
git push -u origin main
```

> 提示:第一次 push 弹窗要输 GitHub 用户名 + Personal Access Token(不是密码)

---

### 步骤 3:部署前端 H5 到 Vercel(5 分钟)

1. 打开 https://vercel.com → **Sign Up with GitHub**
2. 第一次登录 Vercel 让绑定 GitHub,授权
3. 点 **Add New → Project**
4. 选刚才的 `yangming-w2` 仓库 → **Import**
5. 配置页:
   - Project Name: `yangming-w2`(可改,影响公网 URL)
   - Framework Preset: **Other**
   - Build Command: 留空
   - Output Directory: `.`
6. 点 **Deploy**
7. 等 1-2 分钟,看到 🎉 → 拿到 URL:`https://yangming-w2.vercel.app`

---

### 步骤 4:部署后端 API 到 Railway(8 分钟)

1. 打开 https://railway.app → **Login with GitHub**
2. 点 **New Project → Deploy from GitHub repo**
3. 选 `yangming-w2` 仓库(同一个)
4. 第一次会问选哪个目录,我们用 **Root Directory**(整仓库)
5. 部署会失败(Dockerfile 路径不对),**手动改**:
   - 点服务 → Settings → **Root Directory** 设为 `/`(就是项目根)
   - **Dockerfile Path** 默认 `Dockerfile`,OK
6. 重新 Deploy,等 2-3 分钟
7. 拿到 API URL:`https://yangming-w2-production.up.railway.app`

> Railway 默认会克隆整仓库,API 启动时把 entries.db 一起打包

---

### 步骤 5:测试 API 公网通(1 分钟)

主人在自己电脑浏览器打开:

```
https://yangming-w2-production.up.railway.app/health
```

应该看到:
```json
{"status":"ok","version":"0.4.0","concepts_count":7,"oral_map_count":770,...}
```

看到就是通了。

---

### 步骤 6:让 H5 知道 API 在哪(2 分钟)

编辑 `index.html`,找这一段:

```js
const API_BASE = (() => {
  if (location.hostname === '127.0.0.1' || location.hostname === 'localhost') {
    return 'http://127.0.0.1:5001';
  }
  // ★ 部署到 Vercel 后,改成 Railway API 公网 URL
  return 'https://yangming-api.up.railway.app';  // ← 改成主人的真实 URL
})();
```

把 `'https://yangming-api.up.railway.app'` 改成步骤 4 拿到的真实 URL,保存。

重新 push:
```bash
git add index.html
git commit -m "改 API URL"
git push
```

Vercel 自动重新部署,30 秒后生效。

---

### 步骤 7:建知识星球"阳明先生问心室"(5 分钟)

1. 打开 https://wx.zsxq.com(知识星球官网)
2. 主人微信扫码登录
3. 点 **创建星球**
4. 名称:`阳明先生问心室`
5. 简介:`修哥味心学咨询 · 每天 1 问 · 加星球享无限次 · 个人修行档案`
6. 定价:
   - 月卡:¥19.9
   - 年卡:¥199(显示"省 ¥40")
7. 封面图:主人自选(推荐米黄底 + 竹子 + 简笔古人)
8. 创建成功 → 拿到星球 ID 和二维码

---

### 步骤 8:H5 接上知识星球付费(7 分钟)

主人拿到星球二维码后,改 `index.html` 的 `pay` 函数:

```js
function pay(months, price) {
  // 改成跳到知识星球二维码
  const xsqUrl = 'https://wx.zsxq.com/dweb2/index/group/<主人的星球 ID>';
  const qrImg = 'https://主人存放星球二维码图片的 URL';
  // 简化:直接弹窗
  alert('加星球享无限次\n\n微信扫码: ' + qrImg + '\n或访问: ' + xsqUrl);
  // 演示版:不真扣费
  // 上线版:后端验证知识星球 webhook,验证通过再发卡密
}
```

(实际付费墙接 webhook 验星球身份,需要 W4 写后端,现在先用跳转)

---

## ✅ 部署完测一遍

1. 浏览器打开 `https://yangming-w2.vercel.app`
2. 输入"我执行难" → 屏 3 应该看到 3 段答案
3. 屏 4 应该看到米白手绘卡片
4. 屏 5 追问反馈
5. 测付费墙:用隐身模式开屏 1,问 1 次后刷新 → 应该看到付费墙

---

## 💰 收费流程

**当前简版(演示)**:
- 每天 1 问免费
- 超过 → 弹窗"加星球享无限次"
- 点 19.9/月或 199/年 → 弹窗二维码 + 跳知识星球
- 主人手动验证入群 → 私下给激活码

**未来 W4 版**:
- 知识星球 webhook → 后端验签 → 自动激活会员
- 全部自动化,主人不用动手

---

## 💸 成本预估

| 服务 | 免费额度 | 超出后 |
|------|---------|--------|
| Vercel | 100GB 流量/月 | $20/月(Pro) |
| Railway | $5/月额度 | 0.000463/分钟 |
| 知识星球 | 5% 抽成 | 无 |

**100 个付费用户**:¥1990/月 - 平台抽成 5% = ¥1890/月
**成本**:Vercel 免费 + Railway $5/月 + 抽成 5% = ~¥100
**净收入**:~¥1790/月

---

## 🆘 故障排查

| 问题 | 解决 |
|------|------|
| Vercel 部署 404 | 检查 Output Directory 设 `.` |
| Railway 部署失败 | 检查 Root Directory 设 `/` |
| API 5001 调不到 | 看 Railway logs,检查 `entries.db` 是否复制进去 |
| H5 显示"调不到 API" | F12 看 Console,检查 API_BASE URL 是否对 |
| 跨域报错 | api_consult.py 已开 CORS *,理论上不会 |
| Vercel URL 变了 | 在 Vercel Project → Settings → Domains 可改 |

---

## 📦 后续可做

- **W3.5**:把 H5 病根/落地招换成 LLM 生成(用 W1 API + Coze Bot)
- **W4**:接知识星球 webhook 自动激活
- **W5**:加个人修行档案(localStorage → 云端同步)
- **W6**:A/B 测试不同问句 → 不同定价

---

## 📞 主人要老李做的

主人跑通 8 步后,如果遇到问题:
- 直接发报错截图 + 步骤号
- 我立刻帮排查
