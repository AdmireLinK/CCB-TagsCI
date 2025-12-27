import shutil
import time
import random
from tqdm import tqdm
import requests
import urllib.parse
from bs4 import BeautifulSoup
from urllib3 import Retry
from requests.adapters import HTTPAdapter
from threading import Lock

requests.adapters.DEFAULT_RETRIES = 3  # type: ignore

global_session = requests.Session()
retry = Retry(total=10, backoff_factor=3, backoff_max=10)
global_session.mount('https', HTTPAdapter(max_retries=retry))
global_session.mount('http', HTTPAdapter(max_retries=retry))


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

    def reset(self):
        self.current = self.min_cooldown
        self.slow_response_count = 0
        self.fast_response_count = 0


default_dynamic_cooldown = DynamicCooldown()


class RateLimiter:
    def __init__(self, max_requests_per_second=30):
        self.max_requests_per_second = max_requests_per_second
        self.min_interval = 1.0 / max_requests_per_second
        self.last_request_time = 0
        self.lock = Lock()

    def acquire(self):
        with self.lock:
            current_time = time.time()
            elapsed = current_time - self.last_request_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_request_time = time.time()

    def reset(self):
        with self.lock:
            self.last_request_time = 0


default_rate_limiter = RateLimiter()


def safe_get(
    url: str,
    bar: tqdm | None = None,
    headers={},
    cookies={},
    timeout: float = 10,
    cooldown: float = 3,
    jitter: float = 0.5,
    verbose: bool = True,
    session: requests.Session | None = None,
    dynamic_cooldown: DynamicCooldown | None = None,
    rate_limiter: RateLimiter | None = None,
) -> requests.Response:
    if dynamic_cooldown:
        actual_cooldown = dynamic_cooldown.get()
    elif jitter > 0:
        actual_cooldown = cooldown * random.uniform(1 - jitter, 1 + jitter)
    else:
        actual_cooldown = cooldown

    if rate_limiter:
        rate_limiter.acquire()

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
    
    if dynamic_cooldown:
        dynamic_cooldown.update(elapsed)
        if verbose:
            if bar:
                bar.write('{} in {:.3f}s (cooldown: {:.2f}s)'.format(r.status_code, elapsed, actual_cooldown))
            else:
                print('{} in {:.3f}s (cooldown: {:.2f}s)'.format(r.status_code, elapsed, actual_cooldown))
    else:
        if verbose:
            if bar:
                bar.write('{} in {:.3f}s'.format(r.status_code, elapsed))
            else:
                print('{} in {:.3f}s'.format(r.status_code, elapsed))
    
    if r.status_code != 200:
        if elapsed < actual_cooldown:
            time.sleep(actual_cooldown - elapsed)
        raise requests.HTTPError(request=r.request, response=r)
    if elapsed < actual_cooldown:
        time.sleep(actual_cooldown - elapsed)
    return r


def safe_download(
    url: str,
    path: str,
    bar: tqdm | None = None,
    headers={},
    cookies={},
    timeout: float = 10,
    cooldown: float = 3,
    jitter: float = 0.5,
    verbose: bool = True,
    session: requests.Session | None = None,
    dynamic_cooldown: DynamicCooldown | None = None,
    rate_limiter: RateLimiter | None = None,
):
    if dynamic_cooldown:
        actual_cooldown = dynamic_cooldown.get()
    elif jitter > 0:
        actual_cooldown = cooldown * random.uniform(1 - jitter, 1 + jitter)
    else:
        actual_cooldown = cooldown

    if rate_limiter:
        rate_limiter.acquire()

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
    
    if dynamic_cooldown:
        dynamic_cooldown.update(elapsed)
        if verbose:
            if bar:
                bar.write('{:.3f}s (cooldown: {:.2f}s)'.format(elapsed, actual_cooldown))
            else:
                print('{:.3f}s (cooldown: {:.2f}s)'.format(elapsed, actual_cooldown))
    else:
        if verbose:
            if bar:
                bar.write('{:.3f}s'.format(elapsed))
            else:
                print('{:.3f}s'.format(elapsed))
    
    if elapsed < actual_cooldown:
        time.sleep(actual_cooldown - elapsed)
    return r


def safe_soup(
    url: str,
    bar: tqdm | None = None,
    headers={},
    cookies={},
    timeout: float = 10,
    cooldown: float = 3,
    verbose: bool = True,
    session: requests.Session | None = None,
    dynamic_cooldown: DynamicCooldown | None = None,
    rate_limiter: RateLimiter | None = None,
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
            dynamic_cooldown=dynamic_cooldown,
            rate_limiter=rate_limiter,
        ).text,
        'html.parser',
    )


def quote_all(url):
    return urllib.parse.quote(url.lstrip('/'), safe="")


def title_to_url(title):
    return quote_all(title.replace(' ', '_'))
