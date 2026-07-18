# AI Sing / 妙唱

AI Sing（妙唱）是一个唱歌跟随与 AI 歌声处理软件系统，包含 Windows 桌面客户端、FastAPI 后端服务和 Vue 管理后台。系统支持用户登录、音频上传、任务队列、歌声分离、RVC 声音训练、AI 翻唱处理、结果下载、积分消耗和后台运营管理。

B站视频介绍 
https://www.bilibili.com/video/BV1UDj16XEoh

## 子系统

```text
ai-sing-client/   Windows 桌面客户端，负责登录、上传音频、查看任务、播放和下载结果
ai-sing-server/   FastAPI 后端，负责账号、任务队列、积分、OSS 上传、RVC/Demucs 处理
ai-sing-admin/    Vue 管理后台，负责用户、积分、客服信息、价格和处理记录管理
```

## 系统流程

1. 用户在客户端登录或注册。
2. 客户端向后端申请 OSS 预签名上传地址。
3. 客户端将训练音频、待处理歌曲和歌词上传到对象存储。
4. 后端创建训练或歌曲处理任务，并写入数据库队列。
5. 后端 Worker 下载输入文件，执行 Demucs 分离、RVC 训练或 RVC 推理。
6. Worker 将模型、AI 人声、伴奏和歌词等结果上传到 OSS。
7. 客户端轮询任务状态，展示并下载处理结果。
8. 管理后台用于查看用户、积分流水、任务价格和客服配置。

## 开源配置说明

仓库中的数据库、对象存储、线上域名、AccessKey、Secret、管理员默认密码等隐私配置均应使用 `xxxx` 占位。部署前请在本地或服务器环境中替换为自己的真实配置，不要把真实密钥提交到公开仓库。

重点配置文件：

```text
ai-sing-server/.env
ai-sing-server/app/core/config.py
ai-sing-client/aising_client/api.py
ai-sing-admin/src/App.vue
```

建议公开发布前再次执行敏感信息扫描：

```bash
rg -n --hidden -g '!.git/**' -g '!node_modules/**' -g '!dist/**' \
  "password|secret|access_key|token|aliyun|oss-|mysql|jdbc|数据库真实地址|线上域名"
```

## 后端配置与启动

进入后端目录：

```bash
cd ai-sing-server
```

准备 `.env`，将 `xxxx` 替换为你的实际配置：

```env
AIS_DB_HOST=xxxx
AIS_DB_PORT=3306
AIS_DB_NAME=xxxx
AIS_DB_USER=xxxx
AIS_DB_PASSWORD=xxxx

AIS_ADMIN_USERNAME=admin
AIS_ADMIN_PASSWORD=xxxx

AIS_OSS_ENABLED=true
AIS_OSS_ENDPOINT=https://xxxx
AIS_OSS_INTERNAL_ENDPOINT=https://xxxx
AIS_OSS_BUCKET=xxxx
AIS_OSS_ACCESS_KEY_ID=xxxx
AIS_OSS_ACCESS_KEY_SECRET=xxxx
AIS_OSS_PUBLIC_BASE_URL=https://xxxx
AIS_OSS_KEY_PREFIX=ai-sing
```

Docker 启动：

```bash
docker build -t ai-sing-server:local .
docker compose up -d
docker compose logs -f ai-sing-server
```

本地开发启动：

```bash
python -m pip install -r requirements.txt
python start.py
```

GPU 训练和推理依赖 RVC CLI、Demucs、CUDA PyTorch 和 NVIDIA Container Toolkit。详细部署说明见 [ai-sing-server/README.md](ai-sing-server/README.md)。

## 客户端配置与启动

进入客户端目录：

```powershell
cd ai-sing-client
conda env create -f environment.yml
conda activate ai-sing-client
python -m pip install -r requirements-gpu.txt
python -m pip install -r requirements.txt
python -m aising_client.main
```

默认后端地址在 `aising_client/api.py` 中配置，开源版本使用 `https://xxxx/sing-api` 占位。部署时请改成自己的后端 API 地址。

Windows 打包：

```powershell
.\build_windows.ps1
```

更多说明见 [ai-sing-client/README.md](ai-sing-client/README.md)。

## 管理后台配置与启动

进入管理后台目录：

```bash
cd ai-sing-admin
npm install
```

创建 `.env` 并配置后端地址：

```env
VITE_API_BASE_URL=https://xxxx/sing-api
```

启动开发服务：

```bash
npm run dev
```

生产构建：

```bash
npm run build
```

更多说明见 [ai-sing-admin/README.md](ai-sing-admin/README.md)。

## 发布前检查清单

- 确认三个子系统都切换到用于开源的脱敏分支。
- 确认 `.env`、默认配置、README、前端默认 API 地址中没有真实域名和密钥。
- 确认 `.git/config` 中的私有远程地址不会被公开发布。
- 确认训练模型、用户上传音频、日志、数据库备份、构建产物未被提交。
- 为公开仓库配置新的远程地址后再推送。

## License

没有协议，随便商用



## 交流与赞助

如果有对本项目及FastAPI感兴趣的朋友，欢迎加入微信群学习交流。如果你觉得这个项目帮助到了你，你可以请作者喝杯咖啡表示鼓励☕。扫描下面微信二维码添加微信即可进群。
<table>
    <tr>
        <td><img alt="zsxq" src="https://github.com/user-attachments/assets/2fb5871b-5e60-4062-a539-f4af0b0d3f76"></td>
        <td><img alt="zanzhu" src="https://github.com/user-attachments/assets/2da30ef6-ec5d-408d-ae2f-467be117097c"></td>
    </tr>
</table>

