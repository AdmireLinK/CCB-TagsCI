import json
import os
import requests
import urllib.parse
import time
import shutil
from bs4 import BeautifulSoup
from tqdm import tqdm
from urllib3 import Retry
from requests.adapters import HTTPAdapter

from utils.network import safe_get, safe_soup, safe_download, DynamicCooldown, RateLimiter
from utils.file import save_json, chdir_project_root

chdir_project_root()

headers = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'User-Agent': 'Zzzyt/MoeRanker (https://github.com/Zzzzzzyt/MoeRanker)',
    # 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
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
rate_limiter = RateLimiter(max_requests_per_second=30)
TIMEOUT = 10

ses = requests.Session()
retry = Retry(total=10, backoff_factor=cooldown, backoff_max=10)
ses.mount('https', HTTPAdapter(max_retries=retry))


def crawl_index(count):
    ret = []
    bar = tqdm(range(count))
    try:
        for i in bar:
            soup = safe_soup(
                f'https://bgm.tv/character?orderby=collects&page={i+1}',
                bar,
                dynamic_cooldown=dynamic_cooldown,
                rate_limiter=rate_limiter,
                headers=headers,
            )
            chars = soup.find(id='columnCrtBrowserB').find_all('div')[1]  # type: ignore
            for char in chars.children:
                id = int(char.find('a')['href'].replace('/character/', ''))
                avatar = 'https:' + char.find('img')['src']
                name = char.find('h3').find('a').text.strip()
                # print(id, avatar, name)
                bar.write(f'{id} {avatar} {name}')
                ret.append(
                    {
                        'id': str(id),
                        'name': name,
                        'avatar': avatar,
                    }
                )
    except Exception as e:
        bar.write(str(e))
    return ret


def crawl_characters(index):
    bar = tqdm(index, total=len(index))
    ret = {}
    try:
        for i in bar:
            id = i['id']
            bar.set_description('{} {}'.format(i['name'], id))
            res = safe_get(
                f'https://api.bgm.tv/v0/characters/{id}',
                bar,
                headers=headers,
                dynamic_cooldown=dynamic_cooldown,
                rate_limiter=rate_limiter,
            )
            if res is None or res.status_code != 200:
                bar.write(f'Failed to get character data for {id}')
                continue
            try:
                data = json.loads(res.text)
            except Exception as e:
                bar.write(f'Failed to parse JSON for {id}: {str(e)}')
                continue
            ret[id] = data
    except BaseException as e:
        bar.write(str(e))
        return ret, e
    return ret, None


def crawl_bangumi_id(index, url, ret: dict = {}):
    bar = tqdm(index, total=len(index))
    try:
        for idx, i in enumerate(bar):
            bar.set_description('{} {}'.format(i, idx))
            if str(i) in ret:
                continue
            try:
                res = safe_get(
                    url.format(i),
                    bar,
                    headers=headers,
                    verbose=True,
                    dynamic_cooldown=dynamic_cooldown,
                    rate_limiter=rate_limiter,
                )
                if res is None or res.status_code != 200:
                    ret[i] = {}
                    continue
                try:
                    ret[i] = res.json()
                except Exception as e:
                    bar.write(f'Failed to parse JSON for {i}: {str(e)}')
                    ret[i] = {}
            except KeyboardInterrupt as e:
                raise e
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    ret[i] = {}
                else:
                    raise e
    except BaseException as e:
        bar.write(str(e))
        return ret, e
    return ret, None


def download_thumnail(index, chars):
    bar = tqdm(enumerate(index), total=len(index))
    for idx, i in bar:
        if idx >= len(chars):
            return
        id = i['id']
        if os.path.exists('bangumi/images/{}-avatar.jpg'.format(id)) and os.path.exists(
            'bangumi/images/{}-large.jpg'.format(id)
        ):
            bar.write('skip: ' + i['name'])
            continue
        # print(idx, id, i['name'])
        bar.set_description('{} {} {}'.format(idx, id, i['name']))
        try:
            images = chars[str(id)]['images']
            if images['large'] == '':
                continue
            avatar = images['large'].replace(
                'https://lain.bgm.tv/pic/crt/l/', 'https://lain.bgm.tv/pic/crt/g/'
            )
            safe_download(avatar, 'bangumi/images/{}-avatar.jpg'.format(id), bar, dynamic_cooldown=dynamic_cooldown, rate_limiter=rate_limiter)
            # safe_download(images['small'], 'images/{}-small.jpg'.format(id),bar)
            # safe_download(images['grid'], 'images/{}-grid.jpg'.format(id),bar)
            # safe_download(images['medium'], 'images/{}-medium.jpg'.format(id),bar)
            safe_download(
                images['large'], 'bangumi/images/{}-large.jpg'.format(id), bar, dynamic_cooldown=dynamic_cooldown, rate_limiter=rate_limiter
            )
        except Exception as e:
            bar.write(str(e))


# index = crawl_index(9999)
# save_json(index, 'bangumi/bgm_index_20k.json')
# index = json.load(open("bangumi/bgm_index_20k.json", encoding='utf-8'))
# # print(index)
# chars, e = crawl_characters(index)
# # print(chars, e)
# save_json(chars, 'bangumi/bgm_chars_20k.json')

# subjects, e = crawl_subjects(index)
# print(subjects, e)
# save_json(subjects, 'bangumi/bgm_subjects.json')

# chars = json.load(open('bangumi/bgm_chars_160k.json', encoding='utf-8'))
# download_thumnail(index[:10000], chars)

# set20k = set()
# for i in index:
#     id = i['id']
#     set20k.add(id)

for i in list(range(1, 175)):
    print(f'crawl: {(i-1)*1000+1} - {i*1000}')
    fname = f'bangumi/160k_chars/bgm_chars_160k_{i}.json'
    if os.path.exists(fname):
        crawled = json.load(open(fname, encoding='utf-8'))
    else:
        crawled = {}
    subjects, e = crawl_bangumi_id(
        range((i - 1) * 1000 + 1, i * 1000 + 1),
        'https://api.bgm.tv/v0/characters/{}',
        crawled,
    )
    save_json(subjects, fname)
    if type(e) == KeyboardInterrupt:
        break

# for i in range(1,169):
#     fname = f'bangumi/160k_subjects/bgm_subjects_160k_{i}.json'
#     if os.path.exists(fname):
#         crawled = json.load(open(fname, encoding='utf-8'))
#         for id in set20k:
#             if id in crawled:
#                 del crawled[id]
#         save_json(crawled, fname)


for i in list(range(1, 175)):
    print(f'crawl: {(i-1)*1000+1} - {i*1000}')
    fname = f'bangumi/160k_subjects/bgm_subjects_160k_{i}.json'
    if os.path.exists(fname):
        crawled = json.load(open(fname, encoding='utf-8'))
    else:
        crawled = {}
    subjects, e = crawl_bangumi_id(
        range((i - 1) * 1000 + 1, i * 1000 + 1),
        'https://api.bgm.tv/v0/characters/{}/subjects',
        crawled,
    )
    save_json(subjects, fname)
    if type(e) == KeyboardInterrupt:
        break
