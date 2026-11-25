"""启动测试用的新版 ComfyUI 副本（devtest\\comfy_new）。
便携版 Python 的 python313._pth 把原来的 ComfyUI 文件夹放在搜索路径最前面、也不认 PYTHONPATH，直接跑副本的 main.py 会载入旧的 comfy 包；
这里只在这个进程里把副本和新版 comfy-kitchen（comfy_new_pydeps）放到最前面，不改原来的 Python。"""
import os, runpy, sys
HERE = os.path.dirname(os.path.abspath(__file__))
NEW = os.path.join(HERE, 'comfy_new')
sys.path[:0] = [os.path.join(HERE, 'comfy_new_pydeps'), NEW]
os.chdir(NEW)
sys.argv = [os.path.join(NEW, 'main.py')] + sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
