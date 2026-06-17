import os
import sys
import subprocess
from pathlib import Path

def main():
    print("=== 开始执行所有 Extra Tags 爬虫程序 ===")
    
    script_dir = Path(__file__).resolve().parent
    crawlers = []
    
    # 扫描子目录下的 crawler.py 文件
    for root, dirs, files in os.walk(script_dir):
        for file in files:
            if file == "crawler.py":
                crawlers.append(Path(root) / file)
                
    crawlers = sorted(crawlers)
    print(f"共发现 {len(crawlers)} 个爬虫程序:")
    for c in crawlers:
        print(f"  - {c.relative_to(script_dir.parent)}")
        
    failed = []
    for crawler in crawlers:
        relative_path = crawler.relative_to(script_dir.parent)
        print(f"\n[运行] {relative_path}...")
        
        try:
            # 运行爬虫脚本，继承环境变量 PYTHONPATH
            env = os.environ.copy()
            # 将项目根目录添加到 PYTHONPATH 中
            project_root = script_dir.parent
            if "PYTHONPATH" in env:
                env["PYTHONPATH"] = f"{project_root}{os.pathsep}{env['PYTHONPATH']}"
            else:
                env["PYTHONPATH"] = str(project_root)
                
            res = subprocess.run([sys.executable, str(crawler)], env=env)
            if res.returncode != 0:
                print(f"[错误] {relative_path} 运行失败，退出码: {res.returncode}")
                failed.append(relative_path)
            else:
                print(f"[成功] {relative_path} 顺利执行完成。")
        except Exception as e:
            print(f"[错误] 执行 {relative_path} 时发生异常: {e}")
            failed.append(relative_path)
            
    print("\n=== 执行报告 ===")
    print(f"总计: {len(crawlers)} | 成功: {len(crawlers) - len(failed)} | 失败: {len(failed)}")
    if failed:
        print("以下爬虫运行失败:")
        for f in failed:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("所有爬虫顺利执行成功！")
        sys.exit(0)

if __name__ == "__main__":
    main()
