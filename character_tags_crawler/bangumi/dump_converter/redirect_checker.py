from tqdm import tqdm
from utils.file import load_json, save_json, chdir_project_root
from utils.network import safe_get, safe_soup, safe_download, DynamicCooldown
import requests

chdir_project_root()

headers = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'User-Agent': 'Zzzyt/MoeRanker (https://github.com/Zzzzzzyt/MoeRanker)',
}

dynamic_cooldown = DynamicCooldown(
    initial=0.2,
    min_cooldown=0.1,
    max_cooldown=5.0,
    slow_threshold=1.0,
    fast_threshold=0.3,
    increase_factor=1.5,
    decrease_factor=0.95,
    jitter=0.3
)


def get_id(id, bar, chars):
    url = f"https://api.bgm.tv/v0/characters/{id}"
    try:
        response = safe_get(url, headers=headers, dynamic_cooldown=dynamic_cooldown, bar=bar, verbose=False)
        if response is None:
            bar.write(f'{id} {chars[id]["name"]} -> No response')
            return None
        try:
            data = response.json()
        except Exception as e:
            content_preview = response.text[:100] if response.text else '(empty)'
            bar.write(f'{id} {chars[id]["name"]} -> JSON parse error: {str(e)} | Response: {content_preview}')
            return None
        if 'id' not in data:
            bar.write(f'{id} {chars[id]["name"]} -> Invalid response format')
            return None
        return data['id']
    except requests.HTTPError as e:
        status_code = e.response.status_code if e.response else 'Unknown'
        content_preview = e.response.text[:100] if e.response and e.response.text else '(empty)'
        bar.write(f'{id} {chars[id]["name"]} -> HTTP {status_code} | Response: {content_preview}')
        return None
    except Exception as e:
        bar.write(f'{id} {chars[id]["name"]} -> Error: {str(e)}')
        return None


index = load_json('bangumi/bgm_index_full.json')
chars = load_json('bangumi/bgm_chars_full.json')
subjects = load_json('bangumi/bgm_subjects_full.json')

redirects = load_json('bangumi/bgm_redirects_full.json')
# for k in redirects.keys():
#     redirects[k] = str(redirects[k])

sus = []

for k, v in subjects.items():
    if len(v) == 0:
        if int(k) > 174000 and k not in redirects:
            sus.append(k)

try:
    bar = tqdm(sus)
    for k in bar:
        bar.set_description(f'{k} {chars[k]["name"]}')
        realid = get_id(k, bar, chars)
        if realid is not None and realid != k:
            if realid in chars:
                redirects[k] = realid
                bar.write(f'{k} {chars[k]["name"]} -> {realid} {chars[realid]["name"]}')
            else:
                bar.write(f'{k} {chars[k]["name"]} -> {realid} (not in chars)')
except KeyboardInterrupt:
    pass

save_json(redirects, 'bangumi/bgm_redirects_full.json')

for k in redirects.keys():
    if k in chars:
        del chars[k]
    if k in subjects:
        del subjects[k]

index2 = []
for i in index:
    if i['id'] not in redirects:
        i['rank'] = len(index2) + 1
        index2.append(i)

save_json(index2, 'bangumi/bgm_index_full.json')
save_json(chars, 'bangumi/bgm_chars_full.json')
save_json(subjects, 'bangumi/bgm_subjects_full.json')
