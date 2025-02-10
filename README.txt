先简单写一个 readme 

##服务端操作

1. 先安装 requirements.txt 里面的依赖
2. 根据config.py里面的注释，配置自己的参数和信息
3. 执行 python main.py 启动服务

##本地操作
1. 浏览器安装 singlefile 插件 https://chromewebstore.google.com/detail/singlefile/mpiodijhokgodhhofbcjdecpffjipkle
2. 配置插件（只需要配置一次，支持云端同步）： 
	1. 文件名-模版： {url-host}{url-pathname-flat}.{filename-extension}   
	2. 文件名-最大长度：   384字符
	3. 文件名-替换字符：$
	4. 保存位置-保存到 REST 表单 API-网址: 你的服务器 ip，自行解决端口访问问题
	5. 保存位置-保存到 REST 表单 API-授权令牌： 第二步里面配置的 Bearer Key
	6. 保存位置-保存到 REST 表单 API-文件字段名称： singlehtmlfile
	7. 保存位置-保存到 REST 表单 API-网址字段名称： url
3. 保存


打开一个网页进行，点右上角蓝色插件图标进行测试，观察 log 输出。