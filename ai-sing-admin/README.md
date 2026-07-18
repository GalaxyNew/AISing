# 妙唱管理后台

Vue 3 + Element Plus 管理后台，用于管理用户、积分、客服信息和产品积分配置。

## 默认管理员

```text
账号：admin
密码：xxxx
```

登录后请在“修改密码”页面修改默认密码。

## 安装依赖

建议使用国内 npm 镜像：

```bash
npm install --registry=https://registry.npmmirror.com
```

## 开发启动

默认连接后端地址：

```text
https://xxxx/sing-api
```

启动开发服务：

```bash
npm run dev
```

启动后浏览器打开终端显示的地址，通常是：

```text
http://localhost:5173
```

## 修改后端 API 地址

如果后端地址不是默认值，可以创建 `.env`：

```bash
VITE_API_BASE_URL=https://xxxx/sing-api
```

然后重新启动：

```bash
npm run dev
```

## 生产构建

```bash
npm run build
```

构建产物在：

```text
dist/
```

可以把 `dist/` 部署到 Nginx、1Panel 静态网站或其他前端托管服务。

## 功能

- 管理员登录
- 修改管理员密码
- 用户管理
- 手机号搜索用户
- 新建用户
- 修改用户信息
- 重置用户密码
- 给用户添加积分
- 客服信息配置
- 客服二维码上传
- 积分充值价格配置
- 干声训练和歌曲处理积分消耗配置
- 积分消耗记录和充值记录查看
