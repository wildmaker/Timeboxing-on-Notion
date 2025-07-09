# Notion 自动化工具

一个用于连接 Notion 工作区、选择特定数据库并对数据库中的任务进行批量操作的工具，特别是用于延迟当天的任务。

## 安装

1. 克隆仓库
```
git clone [repository-url]
cd notion_automation
```

2. 创建虚拟环境并安装依赖
```
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

3. 配置环境变量
创建一个 `.env` 文件在项目根目录，内容如下:
```
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your_secret_key
```

4. 初始化数据库
```
flask db init
flask db migrate
flask db upgrade
```

5. 运行应用
```
flask run
```