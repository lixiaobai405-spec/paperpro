# PaperPro Linux / Docker 部署与交付

本方案用于由 **root 管理 Docker 的多项目服务器**。建议项目目录为 `/opt/MT-jianlizengqiangzhinengti`，Compose 项目名为 `paperpro`。主机不需要新建用户；容器使用镜像已有的 `65534:65534` 身份运行应用和转换程序。镜像包含 React 构建结果、FastAPI、LibreOffice Writer、OCR 运行库和中文字体；不需要额外的数据库。

本次本地开发不会自动部署服务器、修改已有项目、提交或推送 Git。GitHub 克隆部署需要先由仓库维护者合并并推送本次改动；也可以直接交付本文所述源码 ZIP。

## 1. 功能和边界

- Linux 旧版 `.doc`：LibreOffice 转为 DOCX 后复用现有表格、正文和图片 OCR 解析，返回转换核对提醒。原始上传文件不被覆盖。
- Linux PDF：由同一份固定模板 DOCX 经 LibreOffice 转为 PDF。默认 `PAPERPRO_PDF_ENGINE=libreoffice`，失败会报错，不会静默改成另一套排版。
- Windows 默认仍使用 Word。`auto` 模式允许现有 ReportLab 备用引擎；`reportlab` 明确选择备用引擎。备用引擎对无法保证的罕见汉字拒绝导出。
- 模板默认 Linux 字体为 `Noto Sans CJK SC`，镜像已安装；Linux 备用 PDF 使用内嵌文泉驿字体。与 Microsoft Word 逐像素一致不在保证范围内。
- 每个转换使用独立临时目录和配置，禁止宏/活动嵌入内容并禁止自动更新链接，转换子进程不继承 AI 密钥。每个应用进程最多同时转换两份文档，排队上限 5 秒、运行超时 45 秒；Linux 超时终止该转换的整个进程组。
- 容器根文件系统只读，仅 `/tmp` 为 256 MiB 临时内存文件系统；停止/重建后临时文件消失。容器日志轮换为 3 份、每份 10 MiB。不要在访问日志中记录请求正文、密钥或完整简历。
- PDF 提取、版式提示及转换输出校验共用进程内锁，避免不受支持的 PyMuPDF 多线程访问。上传解析在工作线程中执行，转换期间健康接口仍可响应。配置禁用宏不等于通过全面恶意文档安全评测，外链阻断验收只覆盖合成图片链接。
- 镜像将 OCR/OpenCV/数值库线程限制为 2，并串行复用 OCR 引擎，避免按宿主机核数自动开线程触及容器进程上限。Windows 原有 OCR 默认配置保留。
- 服务没有用户登录和调用配额系统。配置共用 AI Key 前，公网入口必须增加访问认证或来源 IP 限制并启用 HTTPS。页面勾选同意不是服务访问鉴权。
- `/api/health` 中的 `local_only` 是历史固定字段，不是公网访问隔离的证明。应检查端口绑定、Nginx、服务器防火墙和阿里云安全组。

## 2. 部署前只读检查（服务器 root 终端）

以下均在 **Linux 服务器**执行；先记录现状，再修改 PaperPro 自身配置。不要重装 Docker/Nginx、关闭 SELinux/防火墙，或重启其他项目来解决新项目问题。

```bash
cat /etc/os-release
free -h
df -h /
docker version
docker compose version
docker compose ls
docker ps --format 'table {{.Names}}\t{{.Ports}}'
ss -lntp
ls -ld /opt/MT-* /opt/apps /www/dk_project/wwwroot 2>/dev/null
readlink -f /proc/$(pgrep -o nginx)/exe
```

确认：

1. 新项目目录不存在，或属于本项目且已备份；不要覆盖同名已有项目。
2. 宿主机 `8766` 未占用。被占用时在本项目 `.env` 中调整 `PAPERPRO_PORT`，并同步新站点的反向代理。
3. 现有 Nginx 的 80/443 继续由现有服务管理，PaperPro 不创建第二个主机 Nginx。
4. 宝塔管理的站点应在宝塔中新增独立站点/反向代理。检查实际启用的 `include` 和站点路由，不根据配置目录名称推断配置已生效。
5. 可访问镜像仓库、Debian 软件源、Python/npm 包源；使用 AI 时服务器还需能访问对应服务商。拉取失败先定位 DNS、代理和源，不修改全局 Docker 源影响其他项目。

## 3. 本地生成交付包（Windows PowerShell）

在本地项目根目录执行：

```powershell
uv run --locked --python 3.12 python -m scripts.package_deployment
```

默认输出 `output/delivery/paperpro-linux-deployment.zip`。文件已存在时程序拒绝覆盖，可通过 `--output` 选择新文件名。ZIP 根目录直接包含源码与部署文件，并附 `DELIVERY_MANIFEST.json` 文件清单和逐文件校验值。命令最后打印压缩包 SHA-256，交付时一并提供。

公共源码在 ZIP 内明确标记为 `0644`，避免 Linux `unzip` 将源码还原为仅 root 可读，导致容器内的非特权进程无法启动。Dockerfile 使用 Docker 内置解析器，不额外下载可选的 `docker/dockerfile` 前端镜像。

采用源码白名单，在读取文件前排除 `.env`、`settings.local.json`、凭据目录、私钥、本地虚拟环境、依赖目录、Git 历史、测试产物和真实简历。公共 `settings.json` 存在非空密钥时拒绝打包。不要直接压缩整个工作目录。

## 4. 首次部署（服务器 root 终端）

将 ZIP 上传到服务器，例如 `/root/paperpro-linux-deployment.zip`，并校验交付方提供的 SHA-256：

```bash
sha256sum /root/paperpro-linux-deployment.zip
```

确认目标为空后解压：

```bash
PAPERPRO_DIR=/opt/MT-jianlizengqiangzhinengti
umask 022
install -d -m 0755 "$PAPERPRO_DIR"
test -z "$(ls -A "$PAPERPRO_DIR")" || { echo '目标目录非空，请停止并检查'; exit 1; }
unzip /root/paperpro-linux-deployment.zip -d "$PAPERPRO_DIR"
cd "$PAPERPRO_DIR"
cp -n .env.example .env
chmod 600 .env
```

用服务器编辑器填写 `.env`。仅填写需要的服务商；不使用服务器共用密钥时保持为空，由用户在网页中填写。不要使用 `source .env`、打印文件内容、将真实密钥放到命令参数或聊天中。`settings.local.json` 不会装入镜像，Docker 部署统一通过 Compose 中声明的环境变量注入配置。

`.env` 关键变量：

| 变量 | 默认值/用途 |
|---|---|
| `PAPERPRO_PORT` | `8766`，只绑定宿主机 `127.0.0.1` |
| `PAPERPRO_IMAGE_TAG` | `local`；正式发布建议改为本次发布标识 |
| `PAPERPRO_PDF_ENGINE` | `libreoffice`，严格转换 |
| `PAPERPRO_RESUME_FONT` | `Noto Sans CJK SC`，模板字体 |
| `PAPERPRO_DEEPSEEK_API_KEY` | 可选，服务器专用 DeepSeek Key |
| `PAPERPRO_OPENAI_API_KEY` | 可选，自定义兼容服务的 Key |
| `PAPERPRO_OPENAI_BASE_URL` / `PAPERPRO_OPENAI_MODEL` | 自定义兼容服务的地址和模型 |

检查配置、构建并启动，仅操作 `paperpro` 项目：

```bash
docker compose --env-file .env config --quiet
docker compose --env-file .env build app
docker compose --env-file .env up -d --wait --wait-timeout 120
docker compose ps
curl --noproxy '*' --fail http://127.0.0.1:8766/api/health
```

预期应用容器处于 healthy，健康接口返回 `status=ok`。本机浏览器访问自己电脑的 `127.0.0.1` 不等于访问服务器，远程网页入口需下一步配置。首次镜像构建需要下载 LibreOffice、字体和 Python 依赖，耗时及镜像大小高于原纯 Python 服务。

`cpus: 1.5`、`mem_limit: 2g`、`pids_limit: 256` 是初始运行限制，可根据实际压测调整本项目配置。首次转换需要初始化字体缓存；不要据此声称已验证任意并发规模。

## 5. 接入已有 Nginx / 宝塔

由部署方选择独立域名，并配置 HTTPS 和访问认证/IP 限制。下面是**新站点的 location 示例**，不是覆盖现有 nginx.conf 的完整文件：

```nginx
client_max_body_size 15m;

location / {
    proxy_pass http://127.0.0.1:8766;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 10s;
    proxy_read_timeout 180s;
    proxy_cache off;
}
```

宿主机 Nginx 可访问上述 loopback 端口；若反向代理本身运行在容器中，需另行确认其网络路径，不能照抄其容器内的 `127.0.0.1`。先备份将修改的新站点配置，用当前正在运行的 Nginx 可执行程序和实际配置路径执行 `nginx -t`，通过后使用既有服务/宝塔管理方式重载。不要统一重启整个 Docker 或已有站点。

安全组不需要开放 8766；对外使用既有 80/443。测试时先只允许自己的来源 IP，HTTP 阶段只用合成资料，真实简历和密钥在 HTTPS 入口验收后使用。

## 6. 验收与日志

先运行无付费调用、无真实个人信息的镜像内验收：

```bash
docker compose exec -T app python -m scripts.smoke_linux_documents
```

脚本验证真实 DOC/DOCX 转换、表格及内嵌图片 OCR、中文单页/多页 PDF、罕见汉字、并发隔离、超时子进程清理、两条上传 API、DOCX/PDF HTTP 导出和前端静态页面。报告及样例位于容器 `/tmp/paperpro-linux-smoke`，重建前可导出：

```bash
docker compose exec -T app tar -C /tmp -czf - paperpro-linux-smoke > /root/paperpro-linux-smoke.tar.gz
docker compose logs --tail 100 app
```

`/tmp` 是 tmpfs 挂载，使用上述容器内 `tar` 导出，不依赖 `docker cp` 对挂载文件系统的支持。

还需从目标网页域名人工验证：首页五步流程、`/classic`、上传测试 PDF/DOCX/DOC/图片、诊断、下载和中文分页。该脚本不验证真实简历识别准确率、Microsoft Word 逐像素一致性或真实 HR 标注。真实 AI 调用另外取得授权后再做；本次离线验收不消耗 AI 额度。

转换失败应查看服务日志中的错误类型；程序不会打印转换文档的 stdout/stderr。严格 PDF 模式返回失败时，先检查 `docker compose exec app libreoffice --version`、字体、资源限制和文档是否损坏/加密。

修改 `.env` 后执行 `docker compose up -d --force-recreate --wait`，重建容器使新环境变量生效；`docker compose restart` 不会加载新的环境变量。

## 7. 更新前备份（服务器 root 终端）

每次更新都先保存旧镜像、源码与私密配置。以下备份目录只允许 root 访问，不上传或分享：

```bash
cd /opt/MT-jianlizengqiangzhinengti
PAPERPRO_STAMP=$(date +%Y%m%d-%H%M%S)
PAPERPRO_BACKUP=/opt/backups/paperpro/$PAPERPRO_STAMP
install -d -m 0700 "$PAPERPRO_BACKUP"
cp -p .env compose.yaml Dockerfile .dockerignore "$PAPERPRO_BACKUP/"
docker compose images -q app > "$PAPERPRO_BACKUP/image.id"
PAPERPRO_OLD_IMAGE=$(cat "$PAPERPRO_BACKUP/image.id")
test -n "$PAPERPRO_OLD_IMAGE" || { echo '没有找到旧镜像，请停止检查'; exit 1; }
docker image tag "$PAPERPRO_OLD_IMAGE" "paperpro:rollback-$PAPERPRO_STAMP"
tar --exclude=.git --exclude=.venv --exclude=node_modules --exclude=output --exclude=artifacts \
    -czf "$PAPERPRO_BACKUP/source.tar.gz" .
chmod 600 "$PAPERPRO_BACKUP/source.tar.gz" "$PAPERPRO_BACKUP/.env"
```

备份后保留终端中的时间标识和备份路径，回退时会使用。不要执行全局 `docker system prune` 或删除其他项目的镜像/卷。

## 8. ZIP 更新和回退

确认前述备份完成，把新 ZIP 上传至 `/root/paperpro-linux-deployment-new.zip`。先在同级临时发布目录完整解压、检查并构建，避免覆盖解压遗留旧源码：

```bash
PAPERPRO_DIR=/opt/MT-jianlizengqiangzhinengti
PAPERPRO_NEXT=$PAPERPRO_DIR.next-$PAPERPRO_STAMP
PAPERPRO_PREVIOUS=$PAPERPRO_DIR.previous-$PAPERPRO_STAMP
test ! -e "$PAPERPRO_NEXT" && test ! -e "$PAPERPRO_PREVIOUS" || exit 1
install -d -m 0755 "$PAPERPRO_NEXT"
unzip /root/paperpro-linux-deployment-new.zip -d "$PAPERPRO_NEXT"
cp -p "$PAPERPRO_DIR/.env" "$PAPERPRO_NEXT/.env"
cd "$PAPERPRO_NEXT"
docker compose config --quiet
PAPERPRO_IMAGE_TAG=$PAPERPRO_STAMP docker compose build app
```

构建成功后，核实下面三个绝对路径都是本项目专用目录，再进行短暂切换：

```bash
printf '%s\n' "$PAPERPRO_DIR" "$PAPERPRO_NEXT" "$PAPERPRO_PREVIOUS"
cd /opt
mv "$PAPERPRO_DIR" "$PAPERPRO_PREVIOUS"
mv "$PAPERPRO_NEXT" "$PAPERPRO_DIR"
cd "$PAPERPRO_DIR"
PAPERPRO_IMAGE_TAG=$PAPERPRO_STAMP docker compose up -d --no-build --wait --wait-timeout 120
curl --noproxy '*' --fail http://127.0.0.1:8766/api/health
```

成功后把 `.env` 中的 `PAPERPRO_IMAGE_TAG` 更新为本次时间标识，防止下次普通 `up` 又使用旧标签，并完成第 6 节验收。若前述命令失败或验收不通过，保留失败版本并恢复旧目录、旧镜像：

```bash
PAPERPRO_FAILED=$PAPERPRO_DIR.failed-$PAPERPRO_STAMP
test ! -e "$PAPERPRO_FAILED" || exit 1
cd /opt
mv "$PAPERPRO_DIR" "$PAPERPRO_FAILED"
mv "$PAPERPRO_PREVIOUS" "$PAPERPRO_DIR"
cd "$PAPERPRO_DIR"
PAPERPRO_IMAGE_TAG=rollback-$PAPERPRO_STAMP docker compose up -d --no-build --wait --wait-timeout 120
curl --noproxy '*' --fail http://127.0.0.1:8766/api/health
```

回退后将 `.env` 的镜像标签同步为 `rollback-时间标识`。应用更新通常不需要重载 Nginx；只有站点配置发生变化时才检查并重载对应配置。

## 9. Git 更新（仅用于 Git 克隆安装）

先完成第 7 节备份，并确认工作区没有未保存的修改：

```bash
git status --short
git rev-parse HEAD > "$PAPERPRO_BACKUP/revision.txt"
git fetch origin main
git log --oneline HEAD..origin/main
git diff --stat HEAD..origin/main
git pull --ff-only origin main
docker compose build app
docker compose up -d --wait --wait-timeout 120
curl --noproxy '*' --fail http://127.0.0.1:8766/api/health
```

失败时先用第 7 节保存的旧镜像启动，并恢复对应的旧 Compose、`.env` 和源码。不要使用 `git reset --hard` 清掉服务器本地配置或临时修改；回退源码可在另一个干净目录检出备份提交后重建。

## 10. 管理命令

所有命令先进入本项目目录；Compose 项目名始终是 `paperpro`：

```bash
docker compose ps
docker compose logs --tail 100 app
docker compose restart app
docker compose stop app
docker compose start app
```

`stop/start` 用于保持现有配置的临时停启。更新代码需构建镜像，更新环境变量需重建容器。保留旧镜像和备份至新版本验收完成，再仅针对本项目明确选定的历史产物清理。
