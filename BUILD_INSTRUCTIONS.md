
打包说明：
==========

方法1 - 使用PyInstaller（推荐）：
1. 安装PyInstaller：pip install pyinstaller
2. 进入天堂_PyQt目录
3. 运行：pyinstaller heaven_comic.spec
   或者双击 build_app.bat

方法2 - 使用cx_Freeze（备用）：
1. 安装cx_Freeze：pip install cx_Freeze
2. 将上述setup.py保存为setup.py
3. 运行：python setup.py build

注意事项：
- 打包过程可能需要几分钟时间
- 最终的可执行文件会放在dist/目录下
- 可以添加--onefile参数生成单个exe文件，但这会增加启动时间
- 如果需要图标，可以将.ico文件放在项目中并在spec文件中指定icon路径
