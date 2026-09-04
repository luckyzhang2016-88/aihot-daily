# AI 晨报 · 每日定时生成

每天北京时间 09:00 自动抓取 [AI HOT](https://aihot.virxact.com) 日报，生成一个单文件 HTML 晨报仪表盘，
发布到 GitHub Pages（手机浏览器可随时访问），并可选发一份到邮箱。

电脑关机也不影响：调度跑在 GitHub Actions 上，与本机无关。

---

## 一、落地步骤（约 5 分钟）

### 1. 推代码到已有仓库

仓库 <https://github.com/luckyzhang2016-88/aihot-daily> 已建好（含 GitHub 自动生成的初始 README）。
本目录已是一个 git 仓库、已提交，领先 `origin/main` 一个提交，直接推送即可：

```bash
cd aihot-daily-repo
git push -u origin main
```

推送时若弹出登录：**用户名**填 `luckyzhang2016-88`，**密码**填一个 **Personal Access Token**
（不是 GitHub 登录密码；在 GitHub → Settings → Developer settings → Personal access tokens 生成一个带 `repo` 权限的 token）。

### 2. 开启 GitHub Pages

仓库 → **Settings → Pages** → Source 选 **GitHub Actions**，保存。

第一次跑完后，Pages 地址是：

```
https://<你的用户名>.github.io/aihot-daily/
```

手机上把这个网址存成书签或加到主屏，就是一个随时可开的晨报。

### 3. 配邮件（可选，但不配就只有 Pages、没有主动提醒）

仓库 → **Settings → Secrets and variables → Actions → New repository secret**，加这 5 个：

| Secret | 说明 | 举例 |
|---|---|---|
| `SMTP_HOST` | SMTP 服务器 | QQ 邮箱 `smtp.qq.com`；163 `smtp.163.com`；Gmail `smtp.gmail.com` |
| `SMTP_PORT` | 端口 | `465`（SSL，推荐）或 `587`（STARTTLS） |
| `SMTP_USER` | 发件邮箱完整地址 | `565063858@qq.com` |
| `SMTP_PASS` | **授权码**，不是登录密码 | QQ/163 在邮箱设置里生成「SMTP 授权码」；Gmail 用 App Password |
| `MAIL_TO` | 收件地址，多个用逗号分隔 | `565063858@qq.com` |

没配齐时发信步骤会自动跳过，不影响 Pages 正常出刊。

#### 点击路径

仓库首页 → **Settings**（顶部标签栏最后一个）→ 左侧栏 **Secrets and variables → Actions**
→ 右上角 **New repository secret** → 填 Name 和 Secret → Add secret。各加一次。

#### QQ 邮箱的 SMTP_PASS 怎么拿

填的是**授权码，不是 QQ 登录密码**：

1. 网页登录 <https://mail.qq.com> → 顶部「设置」→「账号」
2. 往下找「POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务」
3. 「IMAP/SMTP服务」那一行点「开启」，按提示用手机发一条短信
4. 页面弹出 16 位英文字母的授权码

这个码**只显示一次**，关掉无法找回，复制后直接粘进来。丢了就重新生成，旧的会失效。

#### 加完后验证

Secrets 是运行时注入的，改完不会自动重跑。去 **Actions** → 「每日 AI 晨报」→ **Run workflow**
手动触发一次，确认邮箱能收到，再等第二天自动跑。

### 3b. 推送到微信（Server酱，可选）

想要每天把晨报**推到个人微信**，用 [Server酱（方糖）](https://sct.ftqq.com)：

1. 用微信扫码登录 sct.ftqq.com，拿到 **SendKey**（形如 `SCTxxxxxxxx`）。
2. 仓库 → **Settings → Secrets and variables → Actions → New repository secret**，加 1 个：

| Secret | 说明 | 举例 |
|---|---|---|
| `SERVERCHAN_SENDKEY` | Server酱 SendKey | `SCTabcd1234efgh` |

3. 微信里关注「方糖」「Server酱」服务号（或按官网绑定企业微信）， thereafter 推送会直接到你的微信。

**注意**：微信聊天里**不渲染完整 HTML 仪表盘**，所以推到微信的是一份 **Markdown 摘要**（今日要点 + 全部条目来源 + 完整仪表盘链接）。
点链接在微信内置浏览器里打开，就是完整的橙色仪表盘。免费版 Server酱 有每日推送额度（约 5 条/天），每天 1 条晨报完全够用。

`SERVERCHAN_SENDKEY` 没配时，微信步骤自动跳过，邮件与 Pages 不受影响。

### 4. 试跑一次

仓库 → **Actions** → 左侧选「每日 AI 晨报」→ 右上角 **Run workflow**。
跑完去 Pages 地址看一眼，确认能打开。

---

## 二、几点说明

**关于准点率**：GitHub Actions 的定时不保证精确，热门时段可能延迟几分钟到半小时，UTC 01:00 通常还算准时。
如果你对时间敏感，把 cron 往前调 15 分钟（`45 0 * * *`）会更稳。

**关于日报还没生成**：AI HOT 日报约在北京时间 08:00 生成。若抓取时当天日报尚未发布，
脚本会自动回退到最近一期，并在页面页脚明确标注「本期为最近一期」，不会拿旧内容冒充当天。

**关于归档**：每天的成品会存一份到 `archive/aihot-daily-YYYY-MM-DD.html`，commit 带 `[skip ci]`，不会重复触发流水线。
想省仓库体积就把 workflow 里的「归档历史」步骤删掉。

**关于费用**：公开仓库的 Actions 和 Pages 都免费，这个用量远低于额度。

---

## 三、本地也能跑

```bash
python3 scripts/generate_daily.py            # 今天
python3 scripts/generate_daily.py 2026-09-04 # 指定日期
python3 scripts/generate_daily.py -o out.html
```

只依赖 Python 标准库，无需 pip install。

---

数据来源：[AI HOT](https://aihot.virxact.com) 公开日报接口。内容版权归原作者所有，摘要为自动压缩改写，
引用具体数字或原话请回原文核对。
