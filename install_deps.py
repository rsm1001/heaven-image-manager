#!/usr/bin/env python3
"""
天堂图片管理器 - 依赖安装脚本
"""

import subprocess
import sys
import importlib
from pathlib import Path


def check_package(package_name):
    """检查包是否已安装"""
    try:
        importlib.import_module(package_name)
        return True
    except ImportError:
        return False


def install_packages():
    """安装所需的包"""
    required_packages = [
        ("PyQt5", "PyQt5"),
        ("PIL", "Pillow"), 
        ("requests", "requests"),
        ("urllib3", "urllib3")
    ]
    
    missing_packages = []
    
    print("检查依赖包...")
    for module_name, package_name in required_packages:
        if not check_package(module_name):
            missing_packages.append(package_name)
            print(f"缺少: {package_name}")
        else:
            print(f"已安装: {package_name}")
    
    if not missing_packages:
        print("\n所有依赖均已安装！")
        return True
    
    print(f"\n需要安装的包: {', '.join(missing_packages)}")
    
    try:
        # 尝试使用国内镜像源安装
        pip_args = [
            sys.executable, "-m", "pip", "install", 
            "--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple/"
        ] + missing_packages
        
        print("正在安装依赖...")
        subprocess.check_call(pip_args)
        
        print("\n依赖安装完成！")
        
        # 验证安装
        all_installed = True
        for module_name, _ in required_packages:
            if not check_package(module_name):
                print(f"安装失败: {module_name}")
                all_installed = False
        
        if all_installed:
            print("所有依赖安装成功！")
            return True
        else:
            print("部分依赖安装失败")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"安装失败: {e}")
        print("\n尝试不使用镜像源安装...")
        try:
            pip_args = [sys.executable, "-m", "pip", "install"] + missing_packages
            subprocess.check_call(pip_args)
            print("依赖安装完成！")
            return True
        except subprocess.CalledProcessError as e:
            print(f"安装失败: {e}")
            return False


def main():
    print("天堂图片管理器 - 依赖安装助手")
    print("="*40)
    
    success = install_packages()
    
    if success:
        print("\n" + "="*40)
        print("安装完成！现在可以运行主程序了:")
        print("python main.py")
    else:
        print("\n" + "="*40)
        print("安装失败，请手动安装以下依赖:")
        print("pip install PyQt5 Pillow requests urllib3")
        print("或者使用国内镜像:")
        print("pip install -i https://pypi.tuna.tsinghua.edu.cn/simple/ PyQt5 Pillow requests urllib3")


if __name__ == "__main__":
    main()