"""Oxford Learner's Dictionary definitions; pronunciation is handled separately."""
import html
import re
from urllib.parse import quote, urljoin, urlsplit
from bs4 import BeautifulSoup
from lexin_scraper import normalize_headword


def render_entry(word, soup, limit):
    entry = soup.select_one('.entry')
    headword = entry.select_one('.headword') if entry else None
    if not headword or normalize_headword(headword.get_text(' ', strip=True)) != normalize_headword(word):
        raise ValueError('No exact Oxford headword')
    pieces = ['<p><strong>' + html.escape(headword.get_text(' ', strip=True)) + '</strong></p>']
    pos = entry.select_one('.pos')
    if pos:
        pieces.append('<div class="part-of-speech">' + html.escape(pos.get_text(' ', strip=True)) + '</div>')
    seen = set()
    # Main senses only: exclude idiom/related-entry definitions and site panels.
    for sense in entry.select('.sense'):
        if sense.find_parent(class_=['idioms', 'phrasal_verb', 'unbox']):
            continue
        definition = sense.select_one(':scope > .def, :scope > .sensetop .def')
        if not definition:
            continue
        text = definition.get_text(' ', strip=True)
        if not text or text in seen:
            continue
        seen.add(text)
        pieces.append('<div class="definition-group"><p><strong>' + html.escape(text) + '</strong></p>')
        examples = sense.find(class_='examples', recursive=False)
        if examples:
            for example in examples.select('.x')[:limit]:
                pieces.append('<div class="example" dir="ltr">' + html.escape(example.get_text(' ', strip=True)) + '</div>')
        pieces.append('</div>')
    if not seen:
        raise ValueError('Oxford definitions not found (site may have changed)')
    return ''.join(pieces)


def oxford_content(word, ctx):
    root = 'https://www.oxfordlearnersdictionaries.com'
    base = '/definition/english/' + quote(word.strip().lower(), safe='')
    pending, visited, rendered = [root + base], set(), set()
    pieces = []
    limit = ctx.config.section('sources')['oxford'].get('examples_per_definition', 3)
    while pending:
        url = pending.pop(0)
        path = urlsplit(url).path
        if path in visited:
            continue
        visited.add(path)
        try:
            response = ctx.fetch(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            content = render_entry(word, soup, limit)
        except Exception as exc:
            if not pieces:
                raise
            ctx.issue(word, 'oxford', exc)
            continue
        canonical = soup.select_one('link[rel="canonical"][href]')
        if canonical:
            visited.add(urlsplit(canonical['href']).path)
        response_url = getattr(response, 'url', None)
        if isinstance(response_url, str):
            visited.add(urlsplit(response_url).path)
        if content not in rendered:
            rendered.add(content)
            pieces.append('<div class="oxford-entry">' + content + '</div>')
        for link in soup.select('a[href]'):
            target = urlsplit(urljoin(root, link['href']))
            # Only the same spelling and numbered entry variants, never compounds.
            if target.netloc != 'www.oxfordlearnersdictionaries.com':
                continue
            if re.fullmatch(re.escape(base) + r'(?:_\d+)?', target.path) and target.path not in visited:
                target_url = root + target.path
                if target_url not in pending:
                    pending.append(target_url)
    return ''.join(pieces)
