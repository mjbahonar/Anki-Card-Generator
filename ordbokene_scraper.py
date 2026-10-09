"""Exact Bokmål/Nynorsk articles with expanded inflection and original emphasis."""
import html
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup
from lexin_scraper import normalize_headword


def exact_article(markup, word):
    soup = BeautifulSoup(markup, 'html.parser')
    heading = soup.select_one('.article-title h3')
    if not heading:
        return False
    for node in heading.select('sup, .hgno, .sr-only'):
        node.decompose()
    return normalize_headword(heading.get_text(' ', strip=True)) == normalize_headword(word)


def render_article(markup):
    soup = BeautifulSoup(markup, 'html.parser')
    for node in soup.select('button, [role="toolbar"], svg, script, style, img, .sr-only'):
        node.decompose()
    for node in soup.select('a'):
        if node.get_text(strip=True) == 'Article page':
            node.decompose()
        elif node.get('href'):
            node['href'] = urljoin('https://ordbokene.no', node['href'])
    for node in soup.select('.subheader'):
        node['class'] = ['part-of-speech']
    for table in soup.select('table'):
        wrapper = soup.new_tag('div', attrs={'class': 'inflection-wrapper'})
        table.wrap(wrapper)
    return '<div class="ordbokene-entry">' + str(soup) + '</div>'


def ordbokene_content(word, dictionary, ctx):
    if dictionary not in ('bm', 'nn'):
        raise ValueError('Unsupported Ordbøkene dictionary')
    parts = []
    source = 'bokmalsordboka' if dictionary == 'bm' else 'nynorskordboka'
    with ctx.page() as page:
        page.goto('https://ordbokene.no/eng/' + dictionary + '/' + quote(word, safe=''),
                  wait_until='networkidle', timeout=ctx.timeout * 1000)
        page.locator('.article .article-title h3').first.wait_for(timeout=ctx.timeout * 1000)
        articles = page.locator('.article')
        for index in range(articles.count()):
            ctx.check_budget()
            article = articles.nth(index)
            if not exact_article(article.inner_html(), word):
                continue
            buttons = article.get_by_role('button', name='Inflection', exact=True)
            for number in range(buttons.count()):
                try:
                    button = buttons.nth(number)
                    if button.get_attribute('aria-expanded') != 'true':
                        button.click(timeout=ctx.timeout * 1000)
                    article.locator('table.infl-table').first.wait_for(timeout=ctx.timeout * 1000)
                except Exception as exc:
                    ctx.issue(word, source + '_inflection', exc)
            parts.append(render_article(article.inner_html()))
    if not parts:
        raise ValueError('No exact ' + source + ' entry')
    credit = ('<div class="image-credit">Bokmålsordboka/Nynorskordboka, Universitetet i Bergen og Språkrådet, '
              'ordbøkene.no · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>. '
              'Layout adapted; controls removed. Inflection: Norsk ordbank.</div>')
    return '<div class="ordbokene-content">' + ''.join(parts) + credit + '</div>'
