# 一键部署当前浏览器页面到博客(NotionNext blog)

## 整体流程

1. 浏览器端安装 singlefile 插件，然后点击插件，选择 “Save as HTML”，保存为 HTML 文件

2. 使用 singlefile 插件，将当前页面保存为 HTML 文件,并通过 restful api 上传到 web-clipper 服务

3. web-clipper 将 HTML 文件上传到 GitHub Pages。GitHub API 接受上传后，Pages 部署在后台继续，不阻塞后续处理。

4. web-clipper 直接从本地 HTML 文件提取可见文本，移除脚本和样式后交给 AI 生成摘要和标签。

5. 通过 notion api 将 github pages 的 html 链接 及 摘要 和 标签 插入到 notion 数据库中。

6. 配置 NotionNext blog 的 数据库，将 notion 数据库中的数据同步到 blog 中。
