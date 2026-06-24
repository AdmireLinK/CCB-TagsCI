import shutil
import time
import random
from tqdm import tqdm
import requests
import urllib.parse
from bs4 import BeautifulSoup
from urllib3 import Retry
from requests.adapters import HTTPAdapter

requests.adapters.DEFAULT_RETRIES = 3  # type: ignore

global_session = requests.Session()
retry = Retry(total=10, backoff_factor=3, backoff_max=10, status_forcelist=[500, 502, 503, 504])
global_session.mount('https', HTTPAdapter(max_retries=retry))
global_session.mount('http', HTTPAdapter(max_retries=retry))


def safe_get(
    url: str,
    bar: tqdm | None = None,
    headers={},
    cookies={},
    timeout: float = 30,
    cooldown: float = 3,
    jitter: float = 0.5,
    verbose: bool = True,
    session: requests.Session | None = None,
) -> requests.Response:
    if jitter > 0:
        cooldown *= random.uniform(1 - jitter, 1 + jitter)

    if not session:
        global global_session
        session = global_session
    url_readable = urllib.parse.unquote(url)
    if verbose:
        if bar:
            bar.write('GET: {} '.format(url_readable), end='')
        else:
            print('GET: {} '.format(url_readable), end='')
    r = session.get(url, headers=headers, cookies=cookies, timeout=timeout)
    r.encoding = 'utf-8'
    elapsed = r.elapsed.total_seconds()
    if verbose:
        if bar:
            bar.write('{} in {:.3f}s'.format(r.status_code, elapsed))
        else:
            print('{} in {:.3f}s'.format(r.status_code, elapsed))
    if r.status_code != 200:
        if elapsed < cooldown:
            time.sleep(cooldown - elapsed)
        raise requests.HTTPError(request=r.request, response=r)
    if elapsed < cooldown:
        time.sleep(cooldown - elapsed)
    return r


def safe_download(
    url: str,
    path: str,
    bar: tqdm | None = None,
    headers={},
    cookies={},
    timeout: float = 30,
    cooldown: float = 3,
    jitter: float = 0.5,
    verbose: bool = True,
    session: requests.Session | None = None,
):
    if jitter > 0:
        cooldown *= random.uniform(1 - jitter, 1 + jitter)

    if not session:
        global global_session
        session = global_session
    url_readable = urllib.parse.unquote(url)
    r = session.get(url, stream=True, headers=headers, cookies=cookies, timeout=timeout)
    if verbose:
        if bar:
            bar.write('Download {} '.format(url_readable), end='')
        else:
            print('Download {} '.format(url_readable), end='')
    if r.status_code != 200:
        if verbose:
            if bar:
                bar.write('ERROR: {}'.format(r.status_code))
            else:
                print('ERROR: {}'.format(r.status_code))
    else:
        with open(path, 'wb') as f:
            r.raw.decode_content = True
            shutil.copyfileobj(r.raw, f)
    elapsed = r.elapsed.total_seconds()
    if verbose:
        if bar:
            bar.write('{:.3f}s'.format(elapsed))
        else:
            print('{:.3f}s'.format(elapsed))
    if elapsed < cooldown:
        time.sleep(cooldown - elapsed)
    return r


def safe_soup(
    url: str,
    bar: tqdm | None = None,
    headers={},
    cookies={},
    timeout: float = 30,
    cooldown: float = 3,
    verbose: bool = True,
    session: requests.Session | None = None,
) -> BeautifulSoup:
    return BeautifulSoup(
        safe_get(
            url,
            bar=bar,
            headers=headers,
            cookies=cookies,
            timeout=timeout,
            cooldown=cooldown,
            verbose=verbose,
            session=session,
        ).text,
        'html.parser',
    )


def quote_all(url):
    return urllib.parse.quote(url.lstrip('/'), safe="")


def title_to_url(title):
    return quote_all(title.replace(' ', '_'))


def clean_title(title):
    import re
    cleaned = re.sub(r'^(File|文件|Image|图像):', '', title, flags=re.IGNORECASE).strip()
    return cleaned.replace('_', ' ')


def resolve_bwiki_image_url(api_url, titles, headers=None):
    if not titles:
        return {}
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    
    from urllib3 import Retry
    from requests.adapters import HTTPAdapter
    import requests
    s = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    s.mount('https://', HTTPAdapter(max_retries=retries))
    s.mount('http://', HTTPAdapter(max_retries=retries))
    
    resolved = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i+50]
        params = {
            "action": "query",
            "titles": "|".join(batch),
            "prop": "imageinfo",
            "iiprop": "url",
            "format": "json"
        }
        try:
            r = s.get(api_url, params=params, headers=headers, timeout=10)
            data = r.json()
            pages = data.get("query", {}).get("pages", {})
            for pid, pinfo in pages.items():
                title = pinfo.get("title")
                ii = pinfo.get("imageinfo")
                if ii:
                    resolved[clean_title(title)] = ii[0]["url"]
        except Exception as e:
            print(f"警告: 批量查询 Bwiki 图片 URL 失败: {e}")
    return resolved


def download_bwiki_missing_assets(api_url, missing_assets, dest_dir, headers=None):
    """
    missing_assets: dict of {local_filename: [bwiki_file_title1, bwiki_file_title2, ...]}
    dest_dir: Path object where files should be saved
    """
    if not missing_assets:
        return
        
    from pathlib import Path
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    actually_missing = {}
    for filename, titles in missing_assets.items():
        if not (dest_dir / filename).exists():
            actually_missing[filename] = titles
            
    if not actually_missing:
        return
        
    print(f"[Bwiki] 发现 {len(actually_missing)} 个需要下载的素材。")
    
    all_titles = []
    for titles in actually_missing.values():
        all_titles.extend(titles)
    all_titles = list(set(all_titles))
    
    resolved = resolve_bwiki_image_url(api_url, all_titles, headers)
    
    for filename, titles in actually_missing.items():
        dest_path = dest_dir / filename
        downloaded = False
        for title in titles:
            img_url = resolved.get(clean_title(title))
            if img_url:
                try:
                    print(f"正在下载 {filename} (自 {title})...")
                    safe_download(img_url, str(dest_path), headers=headers, cooldown=0.5, verbose=True)
                    downloaded = True
                    break
                except Exception as e:
                    print(f"警告: 从 {title} 下载 {filename} 失败: {e}")
        if not downloaded:
            print(f"错误: 无法下载 {filename} (尝试过的标题: {titles})")

