"""Save NSE's official daily files into this repo, byte-for-byte as NSE published them.

  daily/ind_close_all_DDMMYYYY.csv      index closing values (Nifty 50, Bank, Midcap 150, ...)
  bhav/sec_bhavdata_full_DDMMYYYY.csv   full stock bhavcopy (every NSE security: close, prev close, volume ...)

Run by the GitHub Action every weekday evening. Each run looks back LOOKBACK_DAYS calendar days (10 by default,
or the number given when the workflow is started by hand) and fetches any file not saved yet, so a missed day is
picked up on the next run. Nothing is edited. A file is accepted only if its header and the date written inside it
match the day requested, so NSE error pages, holiday placeholders and wrong-day files are never saved.
"""
import csv, http.cookiejar, io, os, sys, time, urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
LOOKBACK_DAYS = int(os.environ.get('LOOKBACK_DAYS') or 10)
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

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


def text_of(body):
    try:
        return body.decode('utf-8-sig')
    except UnicodeDecodeError:
        return None


def valid_index(body, d):
    t = text_of(body)
    if not t: return False
    lines = t.strip().splitlines()
    if not lines or not lines[0].strip().lower().startswith('index name'): return False
    want = d.strftime('%d-%m-%Y')
    return any(l.split(',')[0].strip().lower() == 'nifty 50' and want in l for l in lines[1:])


def valid_bhav(body, d):
    """Header must have SYMBOL, SERIES, DATE1, PREV_CLOSE, CLOSE_PRICE; every row's DATE1 must equal d; >1000 EQ rows."""
    t = text_of(body)
    if not t: return False
    rows = list(csv.reader(io.StringIO(t)))
    if len(rows) < 1000: return False
    head = [h.strip().upper() for h in rows[0]]
    need = ('SYMBOL', 'SERIES', 'DATE1', 'PREV_CLOSE', 'CLOSE_PRICE')
    if not all(n in head for n in need): return False
    i_date, i_ser = head.index('DATE1'), head.index('SERIES')
    want = d.strftime('%d-%b-%Y').lower()
    eq = 0
    for r in rows[1:]:
        if len(r) < len(head): continue
        if r[i_date].strip().lower() != want: return False      # a file for another day: never save it
        eq += r[i_ser].strip() == 'EQ'
    return eq > 1000


KINDS = [
    # (folder, file name pattern, source URLs, validator)
    ('daily', 'ind_close_all_{f}.csv', [
        'https://nsearchives.nseindia.com/content/indices/ind_close_all_{f}.csv',
        'https://archives.nseindia.com/content/indices/ind_close_all_{f}.csv',
        'https://www.niftyindices.com/Daily_Snapshot/ind_close_all_{f}.csv'], valid_index),
    ('bhav', 'sec_bhavdata_full_{f}.csv', [
        'https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{f}.csv',
        'https://archives.nseindia.com/products/content/sec_bhavdata_full_{f}.csv'], valid_bhav),
]


def fetch(d, sources, ok, attempts):
    f = d.strftime('%d%m%Y')
    for tmpl in sources:
        url = tmpl.format(f=f)
        for attempt in range(attempts):
            try:
                body = opener.open(url, timeout=60).read()
                if ok(body, d): return body, url
                print(d, url, '-> not a valid file for this date (', len(body), 'bytes )')
                break                          # a 200 with the wrong content will not change on retry
            except Exception as e:
                print(d, url, 'attempt', attempt + 1, '->', e)
                if attempt + 1 < attempts: time.sleep(20)
    return None, None


def main():
    today = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date()
    warm_up()
    saved = 0
    for back in range(0, LOOKBACK_DAYS):
        d = today - timedelta(days=back)
        weekend = d.weekday() >= 5
        for folder, pattern, sources, ok in KINDS:
            os.makedirs(os.path.join(ROOT, folder), exist_ok=True)
            path = os.path.join(ROOT, folder, pattern.format(f=d.strftime('%d%m%Y')))
            if os.path.exists(path): continue
            # Weekends: one quick try only (NSE sometimes trades on a weekend, e.g. Diwali Muhurat session).
            body, url = fetch(d, sources, ok, 1 if weekend else 3)
            if body:
                open(path, 'wb').write(body)
                print('saved', path, 'from', url)
                saved += 1
            elif not weekend:
                print(d, folder, 'not available (holiday, not yet published, or blocked)')
        if LOOKBACK_DAYS > 15: time.sleep(1)     # be gentle during a long backfill
    print('files saved this run:', saved)


if __name__ == '__main__':
    sys.exit(main())
