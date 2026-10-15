"""
Updates dark_mode.svg / light_mode.svg with live GitHub stats.

Adapted from the approach in Andrew6rant/Andrew6rant (2022-2025).

Environment:
    ACCESS_TOKEN  GitHub PAT. Classic token with `repo` + `read:user`, or a
                  fine-grained token with All Repositories access
                  (Contents, Metadata: read; Followers, Starring: read).
    USER_NAME     GitHub username (Asmit-Dhakal)
    BIRTHDAY      YYYY-MM-DD, used for the "Uptime" line
"""
import datetime
import hashlib
import os
import time

import requests
from dateutil import relativedelta
from lxml import etree

ACCESS_TOKEN = os.environ.get('ACCESS_TOKEN')
if not ACCESS_TOKEN:
    raise RuntimeError(
        "Missing required environment variable 'ACCESS_TOKEN'. "
        "Please add a GitHub Personal Access Token (PAT) as a repository secret."
    )
HEADERS = {'authorization': 'token ' + ACCESS_TOKEN}
USER_NAME = os.environ.get('USER_NAME') or 'Asmit-Dhakal'

birthday_raw = os.environ.get('BIRTHDAY')
if not birthday_raw:
    raise RuntimeError(
        "Missing required environment variable 'BIRTHDAY' (expected format: YYYY-MM-DD). "
        "Please add this as a repository secret."
    )
BIRTHDAY = datetime.datetime.strptime(birthday_raw, '%Y-%m-%d')
CACHE_FILE = 'cache/' + hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest() + '.txt'
AFFILIATIONS = ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER']
QUERY_COUNT = {'user_getter': 0, 'follower_getter': 0, 'graph_repos_stars': 0,
               'recursive_loc': 0, 'loc_query': 0}
OWNER_ID = None  # set in __main__


# ------------------------------------------------------------------ helpers --
def plural(n):
    return '' if n == 1 else 's'


def daily_readme(birthday):
    """'25 years, 3 months, 2 days'"""
    d = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    out = f"{d.years} year{plural(d.years)}, {d.months} month{plural(d.months)}, {d.days} day{plural(d.days)}"
    return out + (' 🎂' if d.months == 0 and d.days == 0 else '')


def graphql(name, query, variables, retries=3):
    """POST to the GraphQL API, retrying on 502/503/504 (GitHub times out on big queries)."""
    QUERY_COUNT[name] = QUERY_COUNT.get(name, 0) + 1
    for attempt in range(retries):
        r = requests.post('https://api.github.com/graphql',
                          json={'query': query, 'variables': variables},
                          headers=HEADERS, timeout=60)
        if r.status_code in (502, 503, 504) and attempt < retries - 1:
            time.sleep(2 ** attempt)
            continue
        break
    if r.status_code == 403:
        raise RuntimeError(f'{name}: 403 (rate/abuse limit?) {r.text}')
    if r.status_code != 200:
        raise RuntimeError(f'{name}: HTTP {r.status_code} {r.text}')
    body = r.json()
    if 'errors' in body:
        raise RuntimeError(f'{name}: GraphQL errors {body["errors"]}')
    return body['data']


# ------------------------------------------------------------- API queries --
def user_getter(username):
    data = graphql('user_getter', 'query($login: String!){ user(login: $login){ id } }',
                   {'login': username})
    return data['user']['id']


def follower_getter(username):
    data = graphql('follower_getter',
                   'query($login: String!){ user(login: $login){ followers{ totalCount } } }',
                   {'login': username})
    return int(data['user']['followers']['totalCount'])


def graph_repos_stars(count_type, owner_affiliation):
    """'repos' -> repo count, 'stars' -> total stars across owned repos. Paginates."""
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
      user(login: $login) {
        repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
          totalCount
          edges { node { ... on Repository { stargazers { totalCount } } } }
          pageInfo { endCursor hasNextPage }
        }
      }
    }'''
    cursor, stars = None, 0
    while True:
        data = graphql('graph_repos_stars', query,
                       {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor})
        repos = data['user']['repositories']
        if count_type == 'repos':
            return repos['totalCount']
        stars += sum(e['node']['stargazers']['totalCount'] for e in repos['edges'])
        if not repos['pageInfo']['hasNextPage']:
            return stars
        cursor = repos['pageInfo']['endCursor']


def recursive_loc(owner, repo_name):
    """Walk a repo's default-branch history 100 commits at a time.
    Returns (additions, deletions, my_commits) counting only commits authored by me."""
    query = '''
    query ($repo_name: String!, $owner: String!, $cursor: String) {
      repository(name: $repo_name, owner: $owner) {
        defaultBranchRef { target { ... on Commit {
          history(first: 100, after: $cursor) {
            edges { node { ... on Commit { additions deletions author { user { id } } } } }
            pageInfo { endCursor hasNextPage }
          } } } }
      }
    }'''
    add = dele = mine = 0
    cursor = None
    while True:
        data = graphql('recursive_loc', query,
                       {'repo_name': repo_name, 'owner': owner, 'cursor': cursor})
        ref = data['repository']['defaultBranchRef']
        if ref is None:  # empty repo
            return 0, 0, 0
        history = ref['target']['history']
        for e in history['edges']:
            author = e['node']['author']['user']
            if author and author['id'] == OWNER_ID:
                mine += 1
                add += e['node']['additions']
                dele += e['node']['deletions']
        if not history['pageInfo']['hasNextPage']:
            return add, dele, mine
        cursor = history['pageInfo']['endCursor']


def list_repos():
    """All repos I can see, as [{'nameWithOwner', 'commits'}]. 60 per page: larger pages 502."""
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
      user(login: $login) {
        repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
          edges { node { ... on Repository {
            nameWithOwner
            defaultBranchRef { target { ... on Commit { history { totalCount } } } }
          } } }
          pageInfo { endCursor hasNextPage }
        }
      }
    }'''
    repos, cursor = [], None
    while True:
        data = graphql('loc_query', query,
                       {'owner_affiliation': AFFILIATIONS, 'login': USER_NAME, 'cursor': cursor})
        page = data['user']['repositories']
        for e in page['edges']:
            n = e['node']
            ref = n['defaultBranchRef']
            repos.append({'name': n['nameWithOwner'],
                          'commits': ref['target']['history']['totalCount'] if ref else 0})
        if not page['pageInfo']['hasNextPage']:
            return repos
        cursor = page['pageInfo']['endCursor']


# ------------------------------------------------------------------ cache ---
# One line per repo: "<sha256(nameWithOwner)> <total_commits> <my_commits> <additions> <deletions>"
# A repo is only re-walked when its total commit count changed since the last run.
def load_cache():
    cache = {}
    try:
        with open(CACHE_FILE) as f:
            for line in f:
                parts = line.split()
                if len(parts) == 5:
                    cache[parts[0]] = [int(p) for p in parts[1:]]
    except FileNotFoundError:
        pass
    return cache


def save_cache(cache):
    os.makedirs('cache', exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        for h, (total, mine, a, d) in cache.items():
            f.write(f'{h} {total} {mine} {a} {d}\n')


def loc_totals():
    """Returns (additions, deletions, my_commits, fully_cached)."""
    repos = list_repos()
    cache = load_cache()
    fresh, cached_all = {}, True
    try:
        for r in repos:
            h = hashlib.sha256(r['name'].encode('utf-8')).hexdigest()
            old = cache.get(h)
            if old and old[0] == r['commits']:
                fresh[h] = old
                continue
            cached_all = False
            if r['commits'] == 0:
                fresh[h] = [0, 0, 0, 0]
                continue
            owner, name = r['name'].split('/')
            a, d, mine = recursive_loc(owner, name)
            fresh[h] = [r['commits'], mine, a, d]
    finally:
        # Persist partial progress even if we crash/hit a rate limit mid-run.
        # Repos that vanished (deleted/lost access) are kept so lifetime totals don't drop.
        merged = {**cache, **fresh}
        save_cache(merged)
    add = sum(v[2] for v in merged.values())
    dele = sum(v[3] for v in merged.values())
    commits = sum(v[1] for v in merged.values())
    return add, dele, commits, cached_all


# -------------------------------------------------------------------- SVG ---
def find(root, element_id):
    return root.find(f".//*[@id='{element_id}']")


def set_text(root, element_id, text):
    el = find(root, element_id)
    if el is not None:
        el.text = str(text)


def dot_string(n):
    return {0: '', 1: ' ', 2: '. '}[n] if n <= 2 else ' ' + '.' * n + ' '


def justify(root, element_id, text):
    """Set text, then size the preceding dot leader so the line keeps a fixed width.
    The budget comes from the element's data-width, minus the text length of any
    elements listed in data-minus."""
    el = find(root, element_id)
    if el is None:
        return
    if isinstance(text, int):
        text = f'{text:,}'
    text = str(text)
    el.text = text
    width = int(el.get('data-width', 0))
    for other in filter(None, (el.get('data-minus') or '').split(',')):
        o = find(root, other)
        width -= len(o.text or '')
    set_text(root, f'{element_id}_dots', dot_string(max(0, width - len(text))))


def svg_overwrite(filename, age, commits, stars, repos, contrib, followers, loc):
    tree = etree.parse(filename)
    root = tree.getroot()
    # plain fields first: justified fields read their lengths
    set_text(root, 'contrib_data', f'{contrib:,}')
    set_text(root, 'loc_add', loc[0])
    set_text(root, 'loc_del', loc[1])
    justify(root, 'age_data', age)
    justify(root, 'repo_data', repos)
    justify(root, 'star_data', stars)
    justify(root, 'commit_data', commits)
    justify(root, 'follower_data', followers)
    justify(root, 'loc_data', loc[2])
    tree.write(filename, encoding='utf-8', xml_declaration=True)


# ------------------------------------------------------------------- main ---
def timed(label, fn, *args):
    t = time.perf_counter()
    result = fn(*args)
    dt = time.perf_counter() - t
    print(f'{label:<22}{dt:>9.3f} s')
    return result


if __name__ == '__main__':
    OWNER_ID = timed('account data', user_getter, USER_NAME)
    age = timed('age', daily_readme, BIRTHDAY)
    add, dele, commits, cached = timed('LOC', loc_totals)
    stars = timed('stars', graph_repos_stars, 'stars', ['OWNER'])
    repos = timed('repos', graph_repos_stars, 'repos', ['OWNER'])
    contrib = timed('contributed repos', graph_repos_stars, 'repos', AFFILIATIONS)
    followers = timed('followers', follower_getter, USER_NAME)

    loc = [f'{add:,}', f'{dele:,}', f'{add - dele:,}']
    for svg in ('dark_mode.svg', 'light_mode.svg'):
        svg_overwrite(svg, age, commits, stars, repos, contrib, followers, loc)

    print('API calls:', sum(QUERY_COUNT.values()), QUERY_COUNT)
