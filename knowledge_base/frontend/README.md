# 知识库管理前端

独立的 Vue 3、TypeScript、Element Plus 工作台。只使用知识库管理员登录，管理 JWT 保存在当前标签页的 `sessionStorage`，退出登录即清除。服务凭证和模型配置由后端管理。

## 运行

需要 Node.js 22 或更新版本及 pnpm。

```powershell
pnpm install --frozen-lockfile
pnpm dev
```

开发服务使用端口 5174，将 `/api` 转发到本机知识库后端。通过环境变量 `KB_API_TARGET` 指定开发代理目标；此变量只供 Vite 开发服务器使用，不包含在浏览器构建中。生产构建的 `/api` 由部署服务器转发到知识库后端。

```powershell
pnpm run lint
pnpm run format:check
pnpm run build
```

在浏览器验证登录、上传、索引任务、检索和正文定位。

## 界面约定

- 文档列表的标题搜索、状态与格式筛选和分页由服务端提供。
- 文档正文中的偏移按 Unicode 码点解释，兼容中文和 emoji。
- Markdown 禁用原始 HTML、图片和危险链接协议，避免预览执行脚本或加载远程跟踪图片。
- 新索引就绪前展示旧的生效索引；旧修订检索来源不在新正文中错误高亮，应核对对应索引的分块。
- 任务轮询在离开页面、退出登录或标签页隐藏时停止；重新可见后恢复，处理中请求支持取消。
- 管理入口使用 hash 路由，静态托管无需额外配置页面回退。
