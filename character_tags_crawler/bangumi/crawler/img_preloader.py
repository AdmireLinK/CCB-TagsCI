import json
import os
import requests
import urllib.parse
import time
import random

from utils.file import save_json, chdir_project_root

chdir_project_root()

class DynamicCooldown:
    def __init__(self, initial=0.2, min_cooldown=0.1, max_cooldown=5.0, 
                slow_threshold=1.0, fast_threshold=0.3, 
                increase_factor=1.5, decrease_factor=0.95, jitter=0.3):
        self.current = initial
        self.min_cooldown = min_cooldown
        self.max_cooldown = max_cooldown
        self.slow_threshold = slow_threshold
        self.fast_threshold = fast_threshold
        self.increase_factor = increase_factor
        self.decrease_factor = decrease_factor
        self.jitter = jitter
        self.slow_response_count = 0
        self.fast_response_count = 0

    def get(self):
        jittered = self.current * random.uniform(1 - self.jitter, 1 + self.jitter)
        return max(self.min_cooldown, min(self.max_cooldown, jittered))

    def update(self, response_time):
        if response_time > self.slow_threshold:
            self.slow_response_count += 1
            self.fast_response_count = 0
            if self.slow_response_count >= 2:
                self.current = min(self.max_cooldown, self.current * self.increase_factor)
                self.slow_response_count = 0
        elif response_time < self.fast_threshold:
            self.fast_response_count += 1
            self.slow_response_count = 0
            if self.fast_response_count >= 5:
                self.current = max(self.min_cooldown, self.current * self.decrease_factor)
                self.fast_response_count = 0
        else:
            self.slow_response_count = 0
            self.fast_response_count = 0

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

headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "User-Agent": "Zzzyt/MoeRanker (https://github.com/Zzzzzzyt/MoeRanker)",
}
cooldown = 2


def safe_get302(url, bar=None, verbose=True):
    url = urllib.parse.unquote(url)
    if verbose:
        if bar is not None:
            bar.write("GET: {} ".format(url), end="")
        else:
            print("GET: {} ".format(url), end="")
    r = requests.get(url, headers=headers, allow_redirects=False)
    elapsed = r.elapsed.total_seconds()
    if verbose:
        if bar is not None:
            bar.write("{} in {:.3f}s".format(r.status_code, elapsed))
        else:
            print("{} in {:.3f}s".format(r.status_code, elapsed))
    if r.status_code != 302:
        if verbose:
            print("ERROR: {}".format(r.status_code))
        raise RuntimeError(r.status_code)
    cooldown_time = dynamic_cooldown.get()
    if elapsed < cooldown_time:
        time.sleep(cooldown_time - elapsed)
    dynamic_cooldown.update(elapsed)
    return r.headers["Location"]


subset = []
for i in os.listdir("moegirl/subset/subset/"):
    subset += json.load(open("moegirl/subset/subset/" + i, encoding="utf-8"))
subset += json.load(open("bangumi/subset/bgm200_subset.json", encoding="utf-8"))
subset += json.load(open("bangumi/subset/bgm2000_subset.json", encoding="utf-8"))
subset = set(subset)
print("subset len={}".format(len(subset)))

mapping = json.load(open("bangumi/moegirl2bgm.json", encoding="utf-8"))
print("mapping len={}".format(len(mapping)))

chars = json.load(open("bangumi/bgm_chars_full.json", encoding="utf-8"))
res = {}
for i in subset:
    if i in mapping:
        for j in mapping[i]:
            if j in res:
                continue
            if chars[j]['images'] is None:
                print("no images:", chars[j]['name'])
                continue
            if chars[j]["images"]["medium"] == "":
                print("no image:", chars[j]["name"])
                continue
            # small = char['images']['small'].replace('https://lain.bgm.tv/r/100/pic/crt/l/', '')
            # grid = char['images']['grid'].replace('https://lain.bgm.tv/r/200/pic/crt/l/', '')
            # large = char['images']['large'].replace('https://lain.bgm.tv/pic/crt/l/', '')
            medium = chars[j]["images"]["medium"].replace(
                "https://lain.bgm.tv/r/400/pic/crt/l/", ""
            )
            # res[i] = [small, grid, large, medium]
            res[j] = medium

print("res len={}".format(len(res)))
save_json(res, "bangumi/bgm_images_medium_mapped.json")
