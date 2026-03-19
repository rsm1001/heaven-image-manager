# 天堂图片管理器 - PyQt版本

基于PyQt5开发的图片管理工具，支持图片预览、分类管理和批量下载功能。

## 功能特性

1. **图片预览**
   - 浏览comic目录中的图片
   - 支持上下翻页、随机显示
   - 图片缩放和居中显示
   - 移动图片到101子目录或删除图片

2. **图片管理**
   - 批量提取图片名称并删除原图（支持追加/覆盖模式）
   - 随机读取JSON数据
   - 删除JSON中的指定项目
   - 清空JSON文件
   - 数据统计和表格显示

3. **批量下载**
   - 从指定URL批量下载缩略图
   - 支持设置起始ID和下载数量
   - 实时进度显示
   - 失败重试机制

## 安装方法

### 方法一：使用批处理文件（推荐，Windows用户）

双击运行 `run.bat` 文件，它会自动检查并安装所需依赖。

### 方法二：手动安装

1. 确保已安装Python 3.6+
2. 安装依赖包：
```bash
pip install -r requirements.txt
```

或直接安装：
```bash
pip install PyQt5 Pillow requests urllib3
```

## 运行方法

```bash
python main.py
```

或者双击运行 `run.bat` 文件。

## 项目结构

```
天堂_PyQt/
├── main.py                 # 主入口
├── run.bat                 # Windows运行脚本
├── install_deps.py         # 依赖安装脚本
├── requirements.txt        # 依赖清单
├── README.md               # 项目说明
├── core/                   # 核心业务逻辑
│   ├── file_manager.py     # 文件管理
│   ├── image_processor.py  # 图像处理
│   └── downloader.py       # 下载管理
├── ui/                     # 界面模块
│   ├── main_window.py      # 主窗口
│   ├── preview_widget.py   # 预览组件
│   ├── manager_widget.py   # 管理组件
│   └── download_widget.py  # 下载组件
├── utils/                  # 工具类
│   ├── config.py           # 配置管理
│   └── logger.py           # 日志系统
└── resources/              # 资源文件（预留）
```

## 注意事项

- 确保comic目录存在以存放图片文件
- 批量下载功能会根据配置下载指定ID范围的图片
- JSON文件用于存储图片名称等元数据
- 应用支持中文界面显示

## 开发说明

本项目是对原tkinter版本的重构，使用PyQt5提供了更现代化的界面和更好的用户体验。