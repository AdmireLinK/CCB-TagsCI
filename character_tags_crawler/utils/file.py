import json
import os


def chdir_project_root():
    root_dir = os.path.normcase(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    cur_dir = os.path.normcase(os.path.abspath(os.getcwd()))
    if cur_dir != root_dir:
        print(f'Changing working directory to project root: {root_dir}')
        os.chdir(root_dir)


def save_json(data: object, path: str, verbose: bool = True):
    if verbose:
        print(f'saving to {path}')
    json.dump(
        data,
        open(path, 'w', encoding='utf-8'),
        ensure_ascii=False,
        separators=(',', ':'),
    )


def save_json_pretty(data: object, path: str, verbose: bool = True):
    if verbose:
        print(f'saving to {path}')
    json.dump(
        data,
        open(path, 'w', encoding='utf-8'),
        ensure_ascii=False,
        separators=(',', ':'),
        indent=2,
    )


def load_json(path: str):
    return json.load(open(path, encoding='utf8'))


def load_json_or_none(path: str):
    if not os.path.exists(path):
        return None
    return json.load(open(path, encoding='utf8'))


def merge_and_save_extra_tags(subject_id: str, new_tags: dict, out_json_file_path: str, guesser_workspace_path: str, verbose: bool = True):
    from pathlib import Path
    
    out_json_file = Path(out_json_file_path)
    guesser_workspace = Path(guesser_workspace_path)
    
    final_tags = {}
    
    # 1. 尝试从 outputs 加载
    if out_json_file.exists():
        try:
            with open(out_json_file, "r", encoding="utf-8") as f:
                final_tags = json.load(f)
            if verbose:
                print(f"[{subject_id}] 已载入本地输出的 {len(final_tags)} 个已有角色属性。")
        except Exception as e:
            print(f"警告: 无法载入已有的输出 JSON: {e}")
    else:
        # 2. 尝试从 guesser 目录加载
        guesser_json = guesser_workspace / "client" / "public" / "data" / "extra_tags" / out_json_file.name
        if guesser_json.exists():
            try:
                with open(guesser_json, "r", encoding="utf-8") as f:
                    final_tags = json.load(f)
                if verbose:
                    print(f"[{subject_id}] 已载入主仓库已有的 {len(final_tags)} 个角色属性进行合并。")
            except Exception as e:
                print(f"警告: 无法载入主仓库已有的 JSON: {e}")
                
    # 3. 合并新抓取的数据 (深度合并，防止覆盖历史手动录入的标签)
    for cid, tags in new_tags.items():
        if cid not in final_tags:
            final_tags[cid] = tags
        else:
            for section, section_data in tags.items():
                if section not in final_tags[cid]:
                    final_tags[cid][section] = section_data
                else:
                    if isinstance(final_tags[cid][section], dict) and isinstance(section_data, dict):
                        for tag_key, tag_val in section_data.items():
                            final_tags[cid][section][tag_key] = tag_val
                    else:
                        final_tags[cid][section] = section_data
        
    # 4. 统一图片资产路径替换 (把 /assets/tag/ 转换为 /assets/extra_tags/)
    reverse_map = {
        'lol': '18011',
        'ow': 'ow',
        'r6s': '105651',
        'bandori': '208415',
        'bh3': '172168',
        'wzry': '194792',
        'dota2': '20810',
        'al': '208559',
        'arknights': '225878',
        'ba': '300648',
        'fgo': '109378',
        'pns': '293554',
        'umamusume': '175552',
        'zzz': '380974',
        'ys': '284157',
        'id5': '228217',
        'cbjq': '378389',
        'pcr': '219588',
        'mc': '385208',
        '1999': '365720',
        'hsr': '360097'
    }
    
    final_str = json.dumps(final_tags, ensure_ascii=False)
    for code, sid in reverse_map.items():
        final_str = final_str.replace(f'/assets/tag/{code}/', f'/assets/extra_tags/{sid}/')
        final_str = final_str.replace(f'/assets/extra_tags/{code}/', f'/assets/extra_tags/{sid}/')
        
    final_tags = json.loads(final_str)
    
    # 5. 保存 JSON 文件
    save_json_pretty(final_tags, str(out_json_file), verbose=verbose)
