"""Save NSE's official daily index closing file (ind_close_all_DDMMYYYY.csv) into daily/, unchanged.

Run by the GitHub Action every weekday evening. Checks the last 10 calendar days and fetches any file
that is not saved yet, so a missed day is picked up on the next run. The file is saved byte-for-byte as NSE
published it; nothing is edited. A response is accepted only if it is a CSV whose header starts with
"Index Name" and that contains a "Nifty 50" row for the expected date.
"""
import http.cookiejar, os, sys, time, urllib.request
from datetime import datetime, timedelta, timezone

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
SOURCES = [
    'https://nsearchives.nseindia.com/content/indices/ind_close_all_{f}.csv',
    'https://archives.nseindia.com/content/indices/ind_close_all_{f}.csv',
    'https://www.niftyindices.com/Daily_Snapshot/ind_close_all_{f}.csv',
]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'daily')

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.addheaders = [('User-Agent', UA), ('Accept', 'text/csv,text/plain,*/*'),
                     ('Accept-Language', 'en-US,en;q=0.9'), ('Referer', 'https://www.nseindia.com/')]


def warm_up():
    """NSE often wants its session cookies before it serves archive files."""
    for u in ('https://www.nseindia.com/', 'https://www.niftyindices.com/'):
        try:
            opener.open(u, timeout=30).read()
        except Exception as e:
            print('warm-up', u, '->', e)


def valid(body, d):
    try:
        text = body.decode('utf-8-sig')
    except UnicodeDecodeError:
        return False
    lines = text.strip().splitlines()
    if not lines or not lines[0].strip().lower().startswith('index name'):
        return False
    want = d.strftime('%d-%m-%Y')
    return any(l.split(',')[0].strip().lower() == 'nifty 50' and want in l for l in lines[1:])


def fetch(d):
    f = d.strftime('%d%m%Y')
    for tmpl in SOURCES:
        url = tmpl.format(f=f)
        for attempt in range(3):
            try:
                body = opener.open(url, timeout=30).read()
                if valid(body, d):
                    return body, url
                print(d, url, '-> not a valid file (', len(body), 'bytes )')
                break                     # a 200 with the wrong content will not change on retry
            except Exception as e:
                print(d, url, 'attempt', attempt + 1, '->', e)
                time.sleep(20)
    return None, None


def main():
    os.makedirs(OUT, exist_ok=True)
    today = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date()
    warm_up()
    saved = 0
    for back in range(0, 10):
        d = today - timedelta(days=back)
        if d.weekday() >= 5:
            continue
        path = os.path.join(OUT, f'ind_close_all_{d.strftime("%d%m%Y")}.csv')
        if os.path.exists(path):
            continue
        body, url = fetch(d)
        if body:
            open(path, 'wb').write(body)
            print('saved', path, 'from', url)
            saved += 1
        else:
            print(d, 'not available (holiday, not yet published, or blocked)')
    print('files saved this run:', saved)


if __name__ == '__main__':
    sys.exit(main())
